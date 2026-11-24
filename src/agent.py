"""The small drafting agent: it answers door and wet questions that only the technician's note can settle.

One run per question (room + `wet` or `doors`), one checkpointer thread per question.
What `create_agent` does under the hood (the whole loop, nothing hidden):
 1. Send the model the system prompt, the question, and the JSON schema of each tool.
 2. The model replies with text or with tool calls: a tool name plus JSON arguments.
 3. Before an edit tool (add_door, mark_wet) runs, HumanInTheLoopMiddleware pauses the run (a LangGraph
    interrupt) when the call is valid. Our runner shows the proposed edit to the drafter (`decide`):
    approve -> resume with Command(resume=...), the tool edits a draft copy of the room;
    reject  -> stop; no retry, the room is counted and goes to the drafter.
    An invalid call (quote not in the note, wrong room, bad wall) does not pause: the tool returns
    the error to the model, which may try again. The drafter never sees an invalid edit.
 4. Other tool results go back to the model as new messages; steps 2 to 4 repeat.
 5. The run ends when the model replies with text. If that text is a tool call written out (a weak-model habit),
    the runner sends one reminder to call the tool. ModelCallLimitMiddleware stops it after 6 model calls.
 6. Our wrapper reads the answer. Exactly one valid answer counts. No answer, two answers, an error or
    the step limit all mean ask_drafter: the agent can never change the final plan by failing.
 Every message is saved to traces/<room id>.<question>.json and reused on the next run.
"""
import hashlib
import json
import time

from pydantic import BaseModel, Field

from . import llm
from .common import DATA, TRACES, load, save
from .cost import room_cost
from .fixes import apply

MODEL = llm.MODEL
MAX_MODEL_STEPS = 6
RECURSION_LIMIT = 60  # graph steps; a backstop only, the model-call limit stops the loop first
# v5: each question gets only its own tools and prompt (step 7 fix).
# v6: one reminder when the model writes a tool call as text. Part of the cache key, so the next live run uses it.
PROMPT_VERSION = "v6"
REMINDER = "You wrote the tool call as text. Call the tool itself; do not write it."
EDIT_TOOLS = ("add_door", "mark_wet")
ANSWER_TOOLS = EDIT_TOOLS + ("no_change", "ask_drafter")
ALLOWED = {"doors": ("add_door", "no_change", "ask_drafter"), "wet": ("mark_wet", "no_change", "ask_drafter")}

PROMPT = """You answer one question about one room of a floor plan drawn by a scanner (the AI plan).
Code has already checked the measurements. Your question can be settled only by the technician's note.
Read the note with get_notes (get_room and get_tour if useful), then answer with exactly one tool call:
{tools}
`quote` must be copied exactly from this room's note, at least 3 words. A drafter approves or rejects every edit.
A sentence about another room is not evidence for this room.
{rules}
Examples:
{examples}
After a tool says your answer is recorded, reply with one short sentence and stop."""
PROMPT_PARTS = {
    "wet": {
        "tools": """- mark_wet(room_id, quote): the note says THIS room is wet.
- no_change(room_id, quote): the note says this room is dry.
- ask_drafter(room_id, question): the note does not say whether this room is wet.""",
        "rules": '"No water", "dry" and "nothing wet" mean dry.',
        "examples": """- The hall. Note "Hall carpet is soaked." -> mark_wet, quote "Hall carpet is soaked."
- The closet. Note "No water in the closet." -> no_change, quote "No water in the closet.\"""",
    },
    "doors": {
        "tools": """- add_door(room_id, wall, quote): the note says this room has a door the plan does not show (wall 0 to 3).
- no_change(room_id, quote): the note shows the plan's door count is right.
- ask_drafter(room_id, question): the note says nothing that settles this room's doors.""",
        "rules": """A tour that counted an archway or opening counted a door that is not there.
If the tour counted fewer doors than the plan, the plan already has the door the tour missed: never add_door.""",
        "examples": """- Plan 1, tour 2. Note "One opening is an archway, no door." -> no_change, quote "One opening is an archway, no door.\"""",
    },
}


def system_prompt(kind):
    return PROMPT.format(**PROMPT_PARTS[kind])


class RoomArgs(BaseModel):
    room_id: str = Field(description="The room id, for example h03-r2")


class QuoteArgs(RoomArgs):
    quote: str = Field(description="Exact words copied from this room's note")


class DoorArgs(QuoteArgs):
    wall: int = Field(description="Wall of the new door: 0 bottom, 1 right, 2 top, 3 left")


class AskArgs(RoomArgs):
    question: str = Field(description="What the drafter should check")


def invalid(name, args, room_id, note, tour_has_more_doors, kind):
    """The error text for an answer call, or None if it is valid.

    Pure (call arguments and fixed facts of the question only): HumanInTheLoopMiddleware runs it again on resume
    as its `when` predicate, and the tool runs it as its guard, so both always agree.
    `tour_has_more_doors`: add_door can be right only if the tour counted more doors than the plan (a rule, so code).
    `kind`: only the tools of this question count (a door question cannot be answered with mark_wet).
    """
    if name not in ALLOWED[kind]:
        return f"Not recorded: this is a {kind} question; answer with {', '.join(ALLOWED[kind])}."
    if name == "add_door" and not tour_has_more_doors:
        return "Not recorded: the tour counted fewer doors than the plan, so the plan has no missing door."
    if args.get("room_id") != room_id:
        return f"Unknown room {args.get('room_id')}; this question is about {room_id}."
    if name in ("add_door", "mark_wet", "no_change"):
        q = str(args.get("quote") or "").strip()
        if len(q.split()) < 3 or q not in note:
            return "Not recorded: the quote must be copied exactly from this room's note (at least 3 words)."
    if name == "add_door" and str(args.get("wall")) not in {"0", "1", "2", "3"}:
        return "Not recorded: wall must be 0, 1, 2 or 3."
    if name == "ask_drafter" and not str(args.get("question") or "").strip():
        return "Not recorded: write the question for the drafter."
    return None


def make_tools(room_id, kind, plan_room, tour_room, note, box):
    """The tools for one question: 3 read tools and the 3 answer tools of its kind (ALLOWED), bound to one room.

    Edits act on box['draft'], a copy; `box['answers']` collects answers.
    """
    from langchain_core.tools import StructuredTool

    more = tour_room["doors"] > len(plan_room["doors"])

    def invalid_here(name, args):
        return invalid(name, args, room_id, note, more, kind)

    def _only(rid):
        return None if rid == room_id else f"Unknown room {rid}; this question is about {room_id}."

    def get_room(room_id: str) -> str:
        return _only(room_id) or json.dumps(plan_room)

    def get_tour(room_id: str) -> str:
        return _only(room_id) or json.dumps(tour_room)

    def get_notes(room_id: str) -> str:
        return _only(room_id) or note

    def _edit(name, args):
        if err := invalid_here(name, args):
            return err
        if not box["approved"]:  # cannot happen through the HITL gate; refuse rather than edit unreviewed
            return "Not applied: an edit needs the drafter's approval."
        box["approved"] = False
        edit_args = {"wall": int(args["wall"])} if name == "add_door" else {}
        box["draft"] = apply(box["draft"], {"action": name, "args": edit_args})
        box["answers"].append({"action": name, "args": edit_args, "quote": args["quote"]})
        return "The drafter approved; the edit is on the draft. Answer recorded: reply with one short sentence."

    def add_door(room_id: str, wall: int, quote: str) -> str:
        return _edit("add_door", {"room_id": room_id, "wall": wall, "quote": quote})

    def mark_wet(room_id: str, quote: str) -> str:
        return _edit("mark_wet", {"room_id": room_id, "quote": quote})

    def no_change(room_id: str, quote: str) -> str:
        if err := invalid_here("no_change", {"room_id": room_id, "quote": quote}):
            return err
        box["answers"].append({"action": "no_change", "args": {}, "quote": quote})
        return "Answer recorded: no change. Reply with one short sentence."

    def ask_drafter(room_id: str, question: str) -> str:
        if err := invalid_here("ask_drafter", {"room_id": room_id, "question": question}):
            return err
        box["answers"].append({"action": "ask_drafter", "args": {"question": question}, "quote": ""})
        return "Answer recorded: a drafter will check. Reply with one short sentence."

    mk = StructuredTool.from_function
    tools = [
        mk(get_room, name="get_room", args_schema=RoomArgs,
           description="The AI plan's version of the room: polygon in feet, ceiling, doors, wet status (affected)."),
        mk(get_tour, name="get_tour", args_schema=RoomArgs,
           description="The 360-degree tour measurements of the room: walls, ceiling, door count, label."),
        mk(get_notes, name="get_notes", args_schema=RoomArgs, description="The technician's note for the room."),
        mk(add_door, name="add_door", args_schema=DoorArgs,
           description="Propose adding a door the plan misses. A drafter approves or rejects it."),
        mk(mark_wet, name="mark_wet", args_schema=QuoteArgs,
           description="Propose marking the room as wet. A drafter approves or rejects it."),
        mk(no_change, name="no_change", args_schema=QuoteArgs, description="Final answer: the plan is right."),
        mk(ask_drafter, name="ask_drafter", args_schema=AskArgs,
           description="Final answer: the note does not settle it; a drafter checks."),
    ]
    return [t for t in tools if t.name not in ANSWER_TOOLS or t.name in ALLOWED[kind]]


def _text(m):
    """The text part of a model message (content can be a string or a list of blocks)."""
    return m.content if isinstance(m.content, str) else " ".join(
        b.get("text", "") for b in m.content if isinstance(b, dict) and b.get("type") == "text")


def trace_steps(messages):
    """The conversation as a short list of steps for the page: model text, tool calls, tool results."""
    steps = []
    for m in messages:
        kind = m.__class__.__name__
        if kind == "AIMessage":
            text = _text(m)
            if text.strip():
                steps.append({"type": "model_text", "text": text.strip()[:600]})
            for tc in m.tool_calls:
                steps.append({"type": "tool_call", "name": tc["name"], "args": tc["args"]})
        elif kind == "ToolMessage":
            steps.append({"type": "tool_result", "name": m.name, "text": str(m.content)[:600]})
    return steps


def question_text(room_id, kind, plan_room, tour_room):
    if kind == "wet":
        return f"Room {room_id} ({plan_room['label']}). The plan says this room is not wet. Is it wet?"
    return (f"Room {room_id} ({plan_room['label']}). The plan shows {len(plan_room['doors'])} door(s); "
            f"the tour counted {tour_room['doors']}. Is the plan missing a door?")


def answer_question(room_id, kind, plan_room, tour_room, note, model, decide, fallbacks=()):
    """Run the agent on one question. Never raises. `decide(proposal)` is the drafter: 'approve' or 'reject'.

    Returns action, args, quote, decision (edits only), reason, error, draft, steps, usage, model_calls.
    """
    from langchain.agents import create_agent
    from langchain.agents.middleware import HumanInTheLoopMiddleware, ModelCallLimitMiddleware
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    box = {"draft": json.loads(json.dumps(plan_room)), "answers": [], "approved": False}
    more = tour_room["doors"] > len(plan_room["doors"])
    gate = {"allowed_decisions": ["approve", "reject"],
            "when": lambda req: invalid(req.tool_call["name"], req.tool_call["args"], room_id, note, more,
                                        kind) is None}
    middleware = [ModelCallLimitMiddleware(thread_limit=MAX_MODEL_STEPS, exit_behavior="error"),
                  HumanInTheLoopMiddleware(interrupt_on={t: gate for t in EDIT_TOOLS},
                                           description_prefix="Drafter: approve or reject this edit"),
                  *llm.agent_middleware(fallbacks)]
    agent = create_agent(model, make_tools(room_id, kind, plan_room, tour_room, note, box),
                         system_prompt=system_prompt(kind), middleware=middleware, checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": f"{room_id}.{kind}"}, "recursion_limit": RECURSION_LIMIT}
    proposal, decision, stop, error = None, None, None, None

    def run(inp):
        """One graph run. Only the agent's own failures are caught; a bug in our code below still crashes."""
        nonlocal error
        try:
            return agent.invoke(inp, config)
        except Exception as e:  # step limit, API error, bad tool output: all go to a drafter
            error = f"{type(e).__name__}: {str(e)[:200]}"
            return {}

    def wrote_call_as_text():
        """True if the run ended with a tool call written as text (a weak-model habit), not a real call."""
        msgs = agent.get_state(config).values.get("messages", [])
        last = msgs[-1] if msgs else None
        return (last is not None and last.__class__.__name__ == "AIMessage" and not last.tool_calls
                and _text(last).lstrip().startswith(("[{", '{"name"')))

    out = run({"messages": [{"role": "user", "content": question_text(room_id, kind, plan_room, tour_room)}]})
    for reminded in (False, True):
        while out.get("__interrupt__"):
            last = [m for m in agent.get_state(config).values["messages"] if m.__class__.__name__ == "AIMessage"][-1]
            answers_in_turn = [c for c in last.tool_calls if c["name"] in ANSWER_TOOLS]
            requests = out["__interrupt__"][0].value["action_requests"]
            if proposal is not None:
                stop = "more than one answer (a second edit after the drafter's decision)"
                break
            if len(requests) != 1 or len(answers_in_turn) != 1:
                stop = "more than one answer in one turn"
                break
            name, args = requests[0]["name"], requests[0]["args"]
            edit_args = {"wall": int(args["wall"])} if name == "add_door" else {}
            proposal = {"room_id": room_id, "kind": kind, "action": name, "args": edit_args, "by": "agent",
                        "quote_or_evidence": args["quote"]}
            proposal["est_cost_at_risk_usd"] = round(
                abs(room_cost(apply(plan_room, proposal))["usd"] - room_cost(plan_room)["usd"]), 2)
            decision = decide(proposal)
            if decision != "approve":
                break  # no retry after a reject
            box["approved"] = True
            out = run(Command(resume={"decisions": [{"type": "approve"}]}))
        if reminded or error or stop or proposal or box["answers"] or not wrote_call_as_text():
            break
        out = run({"messages": [{"role": "user", "content": REMINDER}]})  # one reminder, same 6-call limit
    messages = agent.get_state(config).values.get("messages", [])

    res = {"action": "ask_drafter", "args": {}, "quote": "", "decision": None, "reason": None}
    if error:
        res["reason"] = f"agent error ({error}); a drafter checks"
    elif decision == "reject":
        res.update(action=proposal["action"], args=proposal["args"], quote=proposal["quote_or_evidence"],
                   decision="reject", reason="the drafter rejected the edit")
    elif stop:
        res["reason"] = stop + "; a drafter checks"
    elif len(box["answers"]) == 1:
        a = box["answers"][0]
        res.update(action=a["action"], args=a["args"], quote=a["quote"],
                   decision="approve" if a["action"] in EDIT_TOOLS else None,
                   reason=a["args"].get("question") if a["action"] == "ask_drafter" else None)
    else:
        res["reason"] = ("no valid answer" if not box["answers"] else "more than one answer") + "; a drafter checks"
    edited = res["action"] in EDIT_TOOLS and res["decision"] == "approve"
    res.update(error=error, draft=box["draft"] if edited else json.loads(json.dumps(plan_room)),
               steps=trace_steps(messages), usage=llm.usage(messages),
               model_calls=sum(m.__class__.__name__ == "AIMessage" for m in messages))
    return res


def input_hash(kind, plan_room, tour_room, note):
    blob = json.dumps([MODEL, PROMPT_VERSION, system_prompt(kind), ALLOWED[kind], kind, plan_room, tour_room, note],
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def hard_rooms(case):
    """A hand-made plan room and tour room for a hard-set case: only the fields the question needs matter."""
    plan = {"id": case["id"], "label": case["label"], "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
            "ceiling": 8.0, "doors": [{"wall": 0, "width": 3.0}] * case["plan_doors"],
            "affected": case["plan_affected"], "flags": []}
    tour = {"walls": [10.0] * 4, "ceiling": 8.0, "doors": case["tour_doors"], "label": case["label"]}
    return plan, tour


def jobs():
    """(trace key, room id, kind, plan room, tour room, note, decide) for every notes question, then the hard set."""
    from .checks import notes_questions
    from .drafter import simulated_drafter

    plans = {r["id"]: r for h in load(DATA / "ai_plan.json").values() for r in h["rooms"]}
    truth = {r["id"]: r for h in load(DATA / "truth.json").values() for r in h["rooms"]}
    tours = {rid: t for h in load(DATA / "tour.json").values() for rid, t in h.items()}
    notes = load(DATA / "notes.json")
    out = []
    for rid, item in sorted(notes_questions(load(DATA / "checks.json")), key=lambda x: (x[0], x[1]["kind"])):
        decide = lambda p, pr=plans[rid], tr=truth[rid]: simulated_drafter(p, pr, tr)  # the drafter knows the house
        out.append((f"{rid}.{item['kind']}", rid, item["kind"], plans[rid], tours[rid], notes[rid], decide))
    for case in load(DATA / "notes_hard.json"):
        plan, tour = hard_rooms(case)
        kind = {"wet": "wet", "door": "doors"}[case["question"]]
        out.append((f"hard/{case['id']}", case["id"], kind, plan, tour, case["note"], lambda p: "approve"))
    return out


def main():
    model, fallbacks = None, []
    agent_items, hard, runs = [], {}, {}
    cached = new = 0
    todo = jobs()
    for n, (key, rid, kind, plan_room, tour_room, note, decide) in enumerate(todo):
        path = TRACES / f"{key}.json"
        h = input_hash(kind, plan_room, tour_room, note)
        if path.exists() and load(path).get("input_hash") == h:
            res = load(path)
            cached += 1
        else:
            if model is None:
                if not llm.has_key():
                    raise SystemExit(f"agent: no {llm.key_names()} (environment or .env); {len(todo) - n} "
                                     "questions have no cached answer.")
                model, fallbacks = llm.get_model(), llm.get_fallbacks()
            if llm.over_budget():
                print(f"agent: budget cap {llm.BUDGET_USD} USD reached; stopping, rerun later.")
                break
            t0 = time.perf_counter()
            res = answer_question(rid, kind, plan_room, tour_room, note, model, decide, fallbacks)
            res["seconds"] = round(time.perf_counter() - t0, 1)
            if llm.is_rate_limit(res["error"]):
                print(f"  {key}: provider limit hit ({res['error'][:80]}); stopping, rerun later to continue.")
                break
            res.update(input_hash=h, model=MODEL, key=key)
            save(path, res)
            llm.record(res["usage"])
            new += 1
            print(f"  {key}: {res['action']} {res['decision'] or ''} ({res['model_calls']} calls, "
                  f"{res['seconds']} s)", flush=True)
        runs[key] = {k: res[k] for k in ("action", "decision", "reason", "error", "usage", "model_calls", "seconds")}
        if key.startswith("hard/"):
            hard[rid] = res["action"]
            continue
        p = {"room_id": rid, "kind": kind, "action": res["action"], "args": res["args"], "by": "agent",
             "quote_or_evidence": res["quote"] or res["reason"] or "", "est_cost_at_risk_usd": 0.0}
        if res["action"] in EDIT_TOOLS:
            p["decision"] = res["decision"]
            p["est_cost_at_risk_usd"] = round(abs(room_cost(apply(plan_room, p))["usd"] - room_cost(plan_room)["usd"]), 2)
        elif res["action"] == "ask_drafter":
            p["args"] = {"question": res["args"].get("question") or res["reason"]}
        agent_items.append(p)

    proposals = load(DATA / "proposals.json")
    proposals["agent"] = agent_items
    save(DATA / "proposals.json", proposals)
    save(DATA / "agent_hard.json", hard)
    save(DATA / "agent_runs.json", runs)
    print(f"agent: {len(todo)} questions, {cached} from cache, {new} new, {len(todo) - len(runs)} not run; "
          f"total spend so far {llm.ledger()['usd']:.4f} USD")


if __name__ == "__main__":
    main()
