"""Estimation agent: draft mitigation line items for a room PlanTrust trusted.

Quantities come from the floor plan (code). Which items to include comes from history and the technician's
scope notes (the agent). Prices come only from get_price(): Xactimate in production, a mock in this demo.
Same framework and the same loop as src/agent.py: create_agent, a few tools, submit_draft ends the loop.
"""
import hashlib
import json
import random
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field

from . import llm
from .common import DATA, SEED, TRACES, dims, load, save
from .history import DB, draw_job, quantities, scope_notes, true_items
from .prices import CATALOG, MockPriceSource

MAX_MODEL_STEPS = 8
PROMPT_VERSION = "e1"
FREQ_RULE = 0.5      # baseline: include items seen in at least half of similar past jobs
OFTEN_MISSED_HINT = 0.25
PRICES = MockPriceSource()
Code = Literal[tuple(sorted(CATALOG))]

SYSTEM_PROMPT = """You draft the mitigation line items for one water-damaged room.
Decide WHICH catalog items belong in this job. Do not compute quantities or prices: code does that from the
floor plan and the price source.

Evidence, in order of strength:
1. The technician's scope notes for this room (what is actually there: floor type, wet cabinets, windows,
   registers, furniture, how high the drywall is wet, the water category).
2. What similar past jobs included (item_frequency, find_similar_jobs).
Include an item when the notes or a strong history pattern support it, and say which in the reason.
Small items that estimators often miss (window screens, registers, door casing, moving contents, cleaning
the toilet) belong in the draft when the notes show the thing exists.
Leave out items for things the notes rule out (for example carpet removal on a tile floor).
Use only catalog codes. Call submit_draft once with the final list."""


class RoomArgs(BaseModel):
    room_id: str


class HistoryArgs(BaseModel):
    room_type: str
    loss_category: int | None = Field(default=None, description="1, 2 or 3; leave empty for all categories")


class PriceArgs(BaseModel):
    item_code: str
    region: str
    month: str = Field(description="YYYY-MM")


class DraftItem(BaseModel):
    code: Code
    reason: str = Field(description="Why: the note or the history pattern behind it")


class DraftArgs(BaseModel):
    room_id: str
    items: list[DraftItem]


class History:
    """Read-only view of the history database, without the held-out jobs."""

    def __init__(self, exclude=()):
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        self.jobs = {r["id"]: dict(r) for r in con.execute("SELECT * FROM jobs") if r["id"] not in set(exclude)}
        self.items = {}
        for r in con.execute("SELECT job_id, item_code FROM job_items WHERE item_code IS NOT NULL"):
            if r["job_id"] in self.jobs:
                self.items.setdefault(r["job_id"], set()).add(r["item_code"])
        con.close()

    def similar(self, room_type, loss_category=None):
        same = [j for j in self.jobs.values() if j["room_type"] == room_type]
        if loss_category:
            narrowed = [j for j in same if j["loss_category"] == loss_category]
            if len(narrowed) >= 5:
                same = narrowed
        return same

    def frequency(self, room_type, loss_category=None):
        jobs = self.similar(room_type, loss_category)
        n = len(jobs)
        counts = {}
        for j in jobs:
            for c in self.items.get(j["id"], ()):
                counts[c] = counts.get(c, 0) + 1
        return n, {c: k / n for c, k in counts.items()} if n else {}, counts


def make_tools(target, hist, box):
    from langchain_core.tools import StructuredTool

    q = quantities(target)

    def get_room_quantities(room_id: str) -> str:
        if room_id != target["id"]:
            return f"Unknown room {room_id}."
        return json.dumps({"room_type": target["room_type"], "width_ft": target["width"], "depth_ft": target["depth"],
                           "ceiling_ft": target["ceiling"], "quantities": q})

    def find_similar_jobs(room_type: str, loss_category: int | None = None) -> str:
        jobs = hist.similar(room_type, loss_category)[:12]
        return json.dumps([{"job": j["id"], "category": j["loss_category"], "notes": j["notes"],
                            "items": sorted(hist.items.get(j["id"], ()))} for j in jobs])

    def item_frequency(room_type: str, loss_category: int | None = None) -> str:
        n, freq, counts = hist.frequency(room_type, loss_category)
        rows = [{"code": c, "description": CATALOG[c][0], "share_of_jobs": round(f, 2), "jobs": counts[c],
                 "often_missed": CATALOG[c][4]} for c, f in sorted(freq.items(), key=lambda x: -x[1])]
        return json.dumps({"similar_jobs": n, "items": rows})

    def get_price(item_code: str, region: str, month: str) -> str:
        if item_code not in CATALOG:
            return f"Unknown code {item_code}."
        return json.dumps({"item_code": item_code, "unit": CATALOG[item_code][1],
                           "unit_price_usd": PRICES.get_price(item_code, region, month), "source": "mock"})

    def submit_draft(room_id: str, items: list[DraftItem]) -> str:
        if room_id != target["id"]:
            return f"Draft ignored: this job is room {target['id']}."
        box["items"] = [{"code": i.code, "reason": i.reason} for i in items]
        return "Draft recorded."

    mk = StructuredTool.from_function
    return [
        mk(get_room_quantities, name="get_room_quantities", args_schema=RoomArgs,
           description="Room size and every quantity basis (floor SF, perimeter LF, flood-cut LF, fan days...)."),
        mk(find_similar_jobs, name="find_similar_jobs", args_schema=HistoryArgs,
           description="Up to 12 past jobs of this room type (and water category): their notes and item codes."),
        mk(item_frequency, name="item_frequency", args_schema=HistoryArgs,
           description="How often each catalog item appears in similar past jobs, with job counts."),
        mk(get_price, name="get_price", args_schema=PriceArgs,
           description="Unit price for an item in a region and month (Xactimate in production; mock here)."),
        mk(submit_draft, name="submit_draft", args_schema=DraftArgs, return_direct=True,
           description="Final list of catalog codes for this room, each with a short reason."),
    ]


def run_agent(target, hist, model):
    from langchain.agents import create_agent
    from .agent import _trace

    box = {"items": None}
    agent = create_agent(model, make_tools(target, hist, box), system_prompt=SYSTEM_PROMPT)
    ask = (f"Draft the line items for room {target['id']}: a {target['room_type']}, {target['width']:g} x "
           f"{target['depth']:g} ft, ceiling {target['ceiling']:g} ft, region {target['region']}, month "
           f"{target['month']}.\nTechnician scope notes: {target['notes']}")
    messages, error = [], None
    try:
        out = agent.invoke({"messages": [{"role": "user", "content": ask}]},
                           config={"recursion_limit": 2 * MAX_MODEL_STEPS + 1})
        messages = out["messages"]
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
    return {"items": box["items"], "error": error, "steps": _trace(messages), "usage": llm.usage(messages)}


def baseline(target, hist):
    _n, freq, _c = hist.frequency(target["room_type"], target["loss_category"])
    return [{"code": c, "reason": f"In {f:.0%} of similar past jobs"} for c, f in sorted(freq.items())
            if f >= FREQ_RULE]


def price_lines(target, items, hist):
    """Code fills in quantity (from the plan), price (from the price source) and the history evidence."""
    q = quantities(target)
    n, freq, counts = hist.frequency(target["room_type"], target["loss_category"])
    lines = []
    for it in items:
        d, unit, basis, _p, missed = CATALOG[it["code"]]
        price = PRICES.get_price(it["code"], target["region"], target["month"])
        lines.append({"code": it["code"], "description": d, "quantity": q[basis], "unit": unit,
                      "unit_price_usd": price, "total_usd": round(q[basis] * price, 2),
                      "share_of_similar": round(freq.get(it["code"], 0), 2), "source_jobs": counts.get(it["code"], 0),
                      "similar_jobs": n, "often_missed": missed, "reason": it["reason"]})
    included = {it["code"] for it in items}
    check = [{"code": c, "description": CATALOG[c][0], "share_of_similar": round(f, 2)}
             for c, f in sorted(freq.items(), key=lambda x: -x[1])
             if CATALOG[c][4] and c not in included and f >= OFTEN_MISSED_HINT]
    return lines, check


def cached_agent(target, hist, model_box):
    h = hashlib.sha256(json.dumps([llm.MODEL, PROMPT_VERSION, SYSTEM_PROMPT, target,
                                   sorted(hist.jobs)], sort_keys=True).encode()).hexdigest()[:16]
    path = TRACES / "estimate" / f"{target['id']}.json"
    if path.exists() and load(path).get("input_hash") == h:
        return load(path)
    if not llm.has_key() or llm.over_budget():
        return None
    if model_box[0] is None:
        model_box[0] = llm.get_model()
    res = run_agent(target, hist, model_box[0])
    if res["error"] and "rate" in res["error"].lower():
        print(f"  {target['id']}: provider limit hit; rerun later to continue.")
        return None
    res["input_hash"] = h
    save(path, res)
    llm.record(res["usage"])
    print(f"  {target['id']}: {len(res['items'] or [])} items", flush=True)
    return res


def score(drafts, truth_sets):
    tp = fn = fp = om_total = om_hit = 0
    for jid, true in truth_sets.items():
        got = {i["code"] for i in drafts[jid]}
        tp += len(got & true)
        fn += len(true - got)
        fp += len(got - true)
        om = {c for c in true if CATALOG[c][4]}
        om_total += len(om)
        om_hit += len(om & got)
    return {"found": tp, "missed": fn, "extra": fp, "true_items": tp + fn,
            "often_missed_caught": om_hit, "often_missed_total": om_total, "jobs": len(truth_sets)}


def demo_rooms():
    """Rooms PlanTrust accepted on the page, given synthetic scope notes so the agent has something to read."""
    res = load(DATA.parent / "site" / "data" / "results.json")
    picked, seen = [], set()
    for h in res["houses"]:
        for r in h["rooms"]:
            if r["verdict"] == "accept" and r["affected"] and r["label"] in ("kitchen", "bathroom", "bedroom", "living") \
                    and r["label"] not in seen:
                seen.add(r["label"])
                picked.append(r)
    rooms = []
    for r in picked:
        rng = random.Random(f"{SEED}-{r['id']}")
        job = draw_job(rng, r["id"], room=r["label"])
        w, d = dims(r["polygon"])
        job.update({"room_type": r["label"], "width": round(w, 1), "depth": round(d, 1), "ceiling": r["ceiling"],
                    "doors": r["numbers"]["plan_doors"], "region": "FL-TAMPA", "month": "2026-10"})
        job["notes"] = scope_notes(rng, job, true_items(rng, job))
        rooms.append(job)
    return rooms


def main():
    hold = load(DATA / "history_holdout.json")["estimate_jobs"]
    truth = load(DATA / "history_truth.json")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    jobs = {r["id"]: dict(r) for r in con.execute("SELECT * FROM jobs")}
    true_sets = {j: set() for j in hold}
    for r in con.execute("SELECT id, job_id FROM job_items"):
        if r["job_id"] in true_sets:
            true_sets[r["job_id"]].add(truth[str(r["id"])])
    con.close()

    hist = History(exclude=hold)
    model_box = [None]
    base = {j: baseline(jobs[j], hist) for j in hold}
    agent = {}
    for j in hold:
        res = cached_agent(jobs[j], hist, model_box)
        if res is not None:
            agent[j] = res["items"] or []
    scores = {"frequency_rule": score(base, true_sets), "agent": score(agent, {j: true_sets[j] for j in agent}),
              "agent_complete": len(agent) == len(hold), "agent_jobs_run": len(agent), "holdout_jobs": len(hold),
              "freq_rule_threshold": FREQ_RULE}

    full_hist = History()
    demos = []
    for target in demo_rooms():
        res = cached_agent(target, full_hist, model_box)
        items = (res["items"] or []) if res else baseline(target, full_hist)
        lines, check = price_lines(target, items, full_hist)
        demos.append({"room_id": target["id"], "room_type": target["room_type"], "notes": target["notes"],
                      "size": f"{target['width']:g} x {target['depth']:g} ft, ceiling {target['ceiling']:g} ft",
                      "region": target["region"], "month": target["month"],
                      "drafted_by": "agent" if res else "frequency rule (agent not run yet)",
                      "lines": lines, "check_often_missed": check,
                      "total_usd": round(sum(l["total_usd"] for l in lines), 2),
                      "steps": res["steps"] if res else []})
    save(DATA / "estimate_results.json", {"scores": scores, "demos": demos})
    for name in ("frequency_rule", "agent"):
        s = scores[name]
        print(f"{name:15s} found {s['found']}/{s['true_items']}  extra {s['extra']}  "
              f"often-missed {s['often_missed_caught']}/{s['often_missed_total']}  ({s['jobs']} jobs)")


if __name__ == "__main__":
    main()
