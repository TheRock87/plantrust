"""The small review agent, used only for rooms the code checks marked `unclear`.

What `create_agent` does under the hood (the whole loop, nothing hidden):
 1. Send the model the system prompt, the question about one room, and the JSON schema of each tool.
 2. The model replies with text or with a tool call: a tool name plus JSON arguments.
 3. The framework validates the arguments against the tool's pydantic schema and runs the Python function.
 4. The tool's result goes back to the model as a new message in the conversation.
 5. Steps 2 to 4 repeat until the model calls `submit_verdict`, which is marked return_direct,
    so the loop ends right there, or until the step limit (recursion_limit) stops it.
 6. Our wrapper reads the verdict. No verdict, a bad verdict, an API error or the step limit
    all mean "send to drafter": the agent can never auto-accept by failing.
 Every message in the loop is saved to traces/<house>_<room>.json and reused on the next run.
"""
import hashlib
import json
import os
import sys
from typing import Literal

from pydantic import BaseModel, Field

from .common import DATA, ROOT, TRACES, load, save

MODEL = "claude-haiku-5-5"
PRICE_PER_M = {"input": 0.10, "output": 0.50}  # USD per million tokens, Claude Haiku 5.5
BUDGET_USD = 4.50                               # hard cap for the whole project (brief: about 5 USD)
MAX_MODEL_STEPS = 6
PROMPT_VERSION = "v2"

SYSTEM_PROMPT = """You review one room of a preliminary floor plan drawn by a scanner (the AI plan).
A drafter's time is expensive, so only rooms that need a human should go to a drafter.
A missed error costs more than a false alarm: it puts a wrong quantity into the repair estimate.

Use the tools to read the room as drawn in the plan, the 360-degree tour measurements of the same room,
and what the code checks found. Then call submit_verdict exactly once:
- accept: the plan agrees with the tour within normal measurement noise, and you can say why.
- send_to_drafter: anything a drafter must look at, or anything you are unsure about.

Facts about the inputs:
- Tour wall lengths carry about 2 % noise; tour ceilings about 0.3 ft.
- Tour door counts are usually right but sometimes off by one; tour room labels are usually right.
- Stairwells, tall ceilings and glass walls are known weak spots for scanners.
- If two rooms overlap, usually only one of them was drawn wrong; the one whose walls disagree with its tour is the suspect.
Give the reason in one or two sentences with the numbers."""


class RoomArgs(BaseModel):
    room_id: str = Field(description="The room id, for example h03-r2")


class VerdictArgs(BaseModel):
    room_id: str
    verdict: Literal["accept", "send_to_drafter"]
    reason: str = Field(description="One or two sentences with the numbers that decided it")


def make_tools(room_id, plan_room, tour_room, check, box):
    """The 4 tools, bound to one room. `box` receives the verdict."""
    from langchain_core.tools import StructuredTool

    def _only(rid):
        return None if rid == room_id else f"Unknown room {rid}; this review is about {room_id}."

    def get_room(room_id: str) -> str:
        return _only(room_id) or json.dumps(plan_room)

    def get_tour(room_id: str) -> str:
        return _only(room_id) or json.dumps(tour_room)

    def get_check_results(room_id: str) -> str:
        return _only(room_id) or json.dumps({"status": check["status"], "reasons": check["reasons"],
                                             "numbers": check["numbers"],
                                             "estimated_cost_at_risk_usd": check["est_cost_at_risk_usd"]})

    def submit_verdict(room_id: str, verdict: str, reason: str) -> str:
        if room_id != box["room_id"]:
            return f"Verdict ignored: this review is about {box['room_id']}."
        box["verdict"], box["reason"] = verdict, reason
        return "Verdict recorded."

    mk = StructuredTool.from_function
    return [
        mk(get_room, name="get_room", args_schema=RoomArgs,
           description="The AI plan's version of the room: polygon in feet, ceiling, doors, flags."),
        mk(get_tour, name="get_tour", args_schema=RoomArgs,
           description="The 360-degree tour measurements of the room: walls, ceiling, door count, label."),
        mk(get_check_results, name="get_check_results", args_schema=RoomArgs,
           description="What the plain-code checks found for this room, with the numbers."),
        mk(submit_verdict, name="submit_verdict", args_schema=VerdictArgs, return_direct=True,
           description="Final answer for this room: accept or send_to_drafter, with the reason."),
    ]


def _trace(messages):
    steps = []
    for m in messages:
        kind = m.__class__.__name__
        if kind == "AIMessage":
            text = m.content if isinstance(m.content, str) else " ".join(
                b.get("text", "") for b in m.content if isinstance(b, dict) and b.get("type") == "text")
            if text.strip():
                steps.append({"type": "model_text", "text": text.strip()[:600]})
            for tc in m.tool_calls:
                steps.append({"type": "tool_call", "name": tc["name"], "args": tc["args"]})
        elif kind == "ToolMessage":
            steps.append({"type": "tool_result", "name": m.name, "text": str(m.content)[:600]})
    return steps


def _usage(messages):
    tin = sum((getattr(m, "usage_metadata", None) or {}).get("input_tokens", 0) for m in messages)
    tout = sum((getattr(m, "usage_metadata", None) or {}).get("output_tokens", 0) for m in messages)
    usd = tin / 1e6 * PRICE_PER_M["input"] + tout / 1e6 * PRICE_PER_M["output"]
    return {"input_tokens": tin, "output_tokens": tout, "usd": round(usd, 6)}


def review_room(room_id, plan_room, tour_room, check, model):
    """Run the agent on one room. Never raises; any failure becomes send_to_drafter."""
    from langchain.agents import create_agent

    box = {"room_id": room_id, "verdict": None, "reason": None}
    agent = create_agent(model, make_tools(room_id, plan_room, tour_room, check, box), system_prompt=SYSTEM_PROMPT)
    messages, error = [], None
    try:
        out = agent.invoke({"messages": [{"role": "user", "content": f"Review room {room_id}."}]},
                           config={"recursion_limit": 2 * MAX_MODEL_STEPS + 1})
        messages = out["messages"]
    except Exception as e:  # step limit, API error, invalid tool output: all go to a drafter
        error = f"{type(e).__name__}: {str(e)[:200]}"
    verdict, reason = box["verdict"], box["reason"]
    if verdict not in ("accept", "send_to_drafter"):
        verdict = "send_to_drafter"
        reason = "Agent could not decide" + (f" ({error})" if error else "") + "; a drafter checks it."
    return {"verdict": verdict, "reason": reason, "error": error,
            "steps": _trace(messages), "usage": _usage(messages)}


def input_hash(plan_room, tour_room, check):
    blob = json.dumps([MODEL, PROMPT_VERSION, SYSTEM_PROMPT, plan_room, tour_room, check], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _load_env_key():
    """Read ANTHROPIC_API_KEY from a local .env file if it is not already set."""
    env = ROOT / ".env"
    if not os.environ.get("ANTHROPIC_API_KEY") and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip('"')


def main():
    plans, tours, checks = load(DATA / "ai_plan.json"), load(DATA / "tour.json"), load(DATA / "checks.json")
    jobs = []
    for hid in sorted(checks):
        rooms = {r["id"]: r for r in plans[hid]["rooms"]}
        for rid, chk in sorted(checks[hid].items()):
            if chk["status"] == "unclear":
                jobs.append((hid, rid, rooms[rid], tours[hid][rid], chk))

    ledger_path = TRACES / "_spend.json"
    ledger = load(ledger_path) if ledger_path.exists() else {"usd": 0.0, "calls": 0}
    model = None
    verdicts, cached, new, skipped = {}, 0, 0, 0
    for hid, rid, plan_room, tour_room, chk in jobs:
        path = TRACES / f"{rid}.json"
        h = input_hash(plan_room, tour_room, chk)
        if path.exists() and load(path).get("input_hash") == h:
            verdicts[rid] = load(path)
            cached += 1
            continue
        if model is None:
            _load_env_key()
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("agent: no ANTHROPIC_API_KEY (environment or .env); unclear rooms without a cached "
                      "trace are left for the drafter and marked 'agent not run'.")
                skipped = len(jobs) - cached - new
                break
            from langchain_anthropic import ChatAnthropic
            model = ChatAnthropic(model=MODEL, max_tokens=4096, max_retries=2)
        if ledger["usd"] >= BUDGET_USD:
            print(f"agent: budget cap {BUDGET_USD} USD reached; remaining rooms go to the drafter.")
            skipped = len(jobs) - cached - new
            break
        res = review_room(rid, plan_room, tour_room, chk, model)
        res.update({"room_id": rid, "house": hid, "input_hash": h, "model": MODEL})
        save(path, res)
        ledger["usd"] = round(ledger["usd"] + res["usage"]["usd"], 6)
        ledger["calls"] += 1
        save(ledger_path, ledger)
        verdicts[rid] = res
        new += 1
        print(f"  {rid}: {res['verdict']}  ({res['usage']['usd']:.4f} USD)", flush=True)

    save(DATA / "agent_verdicts.json", {rid: {k: v[k] for k in ("verdict", "reason", "usage", "error")}
                                        for rid, v in verdicts.items()})
    print(f"agent: {len(jobs)} unclear rooms, {cached} from cache, {new} new, {skipped} not run; "
          f"total spend so far {ledger['usd']:.4f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
