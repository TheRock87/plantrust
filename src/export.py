"""Write site/data/results.json: everything the page shows, computed by the scripts (no hand-typed numbers).

Comparisons the page states in words (agent against baseline, the harmful-edit goal) are computed here too,
so a rerun that moves the numbers also moves the sentences.
"""
from .agent import ALLOWED, MAX_MODEL_STEPS, MODEL
from .checks import CEIL_TOL, WALL_TOL
from .common import DATA, N_HOUSES, SITE_DATA, TRACES, dims, load, save
from .evaluate import LADDER_MIN_N, LADDER_RATE, actual_cost_at_risk, d_items
from .fixes import EDITS
from .plant import ERRORS

N_VIEWER = 10
WHO = {  # who fixes each error type in row D, and why (words by hand; the thresholds come from the code)
    "E1": ("code", f"A wall more than {WALL_TOL:.0%} off the tour is a rule: set it to the tour."),
    "E2": ("code", f"A ceiling more than {CEIL_TOL:g} ft off the tour is a rule: set it to the tour."),
    "E3": ("agent", "Only the note can tell a missing door from a tour that counted an archway."),
    "E4": ("drafter", "A whole room must be drawn; code asks a drafter, with the size the tour measured."),
    "E5": ("code", "The room whose walls disagree with its tour gets the wall fix, which removes the overlap."),
    "E6": ("agent", "Only the note says the room is wet; the tour cannot see water."),
}


def pick_houses(answers, items):
    """10 houses for the viewer: every error type, then houses with a rejected agent edit or an agent question left
    to the drafter (failures, not only successes), then one clean house."""
    chosen, seen = [], set()
    for hid in sorted(answers):
        codes = {e["code"] for e in answers[hid]}
        if codes - seen:
            chosen.append(hid)
            seen |= codes
    hard = sorted({i["room_id"].split("-")[0] for i in items
                   if i["by"] == "agent" and (i.get("decision") == "reject" or i["action"] == "ask_drafter")})
    for hid in hard:
        if len(chosen) >= N_VIEWER - 1:
            break
        if hid not in chosen and answers[hid]:
            chosen.append(hid)
    clean = [h for h in sorted(answers) if not answers[h]]
    if clean:
        chosen.append(clean[0])
    return sorted(chosen[:N_VIEWER])


def before_after(item, room):
    """The change an item proposes, in the drafter's words."""
    a = item["args"]
    if item["action"] == "set_room_size":
        w, d = dims(room["polygon"])
        return f"{w:g} x {d:g} ft", f"{a['width']:g} x {a['depth']:g} ft"
    if item["action"] == "set_ceiling":
        return f"ceiling {room['ceiling']:g} ft", f"ceiling {a['ceiling']:g} ft"
    if item["action"] == "add_door":
        n = len(room["doors"])
        return f"{n} door{'s' if n != 1 else ''}", f"{n + 1} doors"
    if item["action"] == "mark_wet":
        return "not wet", "wet"
    if item["action"] == "no_change":
        return "keep the plan", "keep the plan"
    return "", a.get("question", "")


def room_status(p, items):
    if p is None:
        return "missing"
    if any(i.get("decision") == "approve" for i in items):
        return "fixed"
    if any(i["action"] == "ask_drafter" or i.get("decision") == "reject" for i in items):
        return "drafter"
    return "clear"


def who_does_what(answers, truth, plans, items):
    t = {r["id"]: r for h in truth.values() for r in h["rooms"]}
    p = {r["id"]: r for h in plans.values() for r in h["rooms"]}
    out = []
    for code, name in ERRORS.items():
        rids = {e["room_id"] for v in answers.values() for e in v if e["code"] == code}
        edits = [i for i in items if i["room_id"] in rids and i["action"] in EDITS]
        who, why = WHO[code]
        out.append({"code": code, "name": name, "count": len(rids), "who": who, "why": why,
                    "usd_at_risk": round(sum(actual_cost_at_risk(t[r], p.get(r)) for r in rids), 2),
                    "edits": len(edits), "approved": sum(i["decision"] == "approve" for i in edits)})
    return out


def main():
    truth, plans, tours = load(DATA / "truth.json"), load(DATA / "ai_plan.json"), load(DATA / "tour.json")
    answers, checks, scores = load(DATA / "answers.json"), load(DATA / "checks.json"), load(DATA / "scores.json")
    notes, proposals = load(DATA / "notes.json"), load(DATA / "proposals.json")
    items, _ = d_items(proposals, checks, plans)
    triage = {h["house"]: h for h in scores["triage"]}

    houses = []
    for hid in pick_houses(answers, items):
        err = {e["room_id"]: e for e in answers[hid]}
        plan_rooms = {r["id"]: r for r in plans[hid]["rooms"]}
        rooms = []
        for t in truth[hid]["rooms"]:
            rid, p = t["id"], plan_rooms.get(t["id"])
            mine = [i for i in items if i["room_id"] == rid]
            shown = []
            for i in mine:
                before, after = before_after(i, p or t)
                trace = TRACES / f"{rid}.{i['kind']}.json"
                shown.append({"by": i["by"], "kind": i["kind"], "action": i["action"], "before": before,
                              "after": after, "evidence": i.get("quote_or_evidence", ""),
                              "usd": i.get("est_cost_at_risk_usd", 0.0), "decision": i.get("decision"),
                              "steps": load(trace)["steps"] if i["by"] == "agent" and trace.exists() else []})
            n = checks[hid][rid].get("numbers", {})
            rooms.append({
                "id": rid, "label": (p or t)["label"], "polygon": (p or t)["polygon"],
                "missing_from_plan": p is None, "affected": (p or t)["affected"],
                "status": room_status(p, mine), "note": notes.get(rid, ""), "numbers": n, "items": shown,
                "answer_key": ({"code": err[rid]["code"], "name": ERRORS[err[rid]["code"]], "detail": err[rid]["detail"],
                                "actual_cost_at_risk_usd": actual_cost_at_risk(t, p)} if rid in err else None),
            })
        houses.append({"id": hid, "rooms": rooms, "n_errors": len(err), "triage": triage[hid]})

    c, d = scores["rows"]["C"], scores["rows"]["D"]
    better = lambda m, a, b: a > b if m == "fixed" else a < b
    est_path = DATA / "estimate_results.json"
    estimate = load(est_path) if est_path.exists() else None
    if estimate:
        for v in (estimate["scores"]["frequency_rule"], estimate["scores"]["agent"]):
            v["precision"] = round(v["found"] / (v["found"] + v["extra"]), 3)
    save(SITE_DATA / "results.json", {
        "model": MODEL,
        "constants": {"max_model_steps": MAX_MODEL_STEPS, "tools_per_question": 3 + len(ALLOWED["wet"]),
                      "wall_tol": WALL_TOL, "ceil_tol": CEIL_TOL, "ladder_rate": LADDER_RATE,
                      "ladder_min_n": LADDER_MIN_N},
        "totals": {"houses": N_HOUSES, "rooms": sum(len(h["rooms"]) for h in truth.values()),
                   "errors": sum(len(v) for v in answers.values()),
                   "clean_houses": sum(1 for v in answers.values() if not v),
                   "questions": sum(scores["notes_questions"].values()), "notes_questions": scores["notes_questions"]},
        "scores": scores,
        "agent_vs_baseline": {m: {"agent": d[m], "baseline": c[m], "agent_better": better(m, d[m], c[m])}
                              for m in ("fixed", "missed", "harmful_edits", "manual_items", "false_alarm_rooms",
                                        "usd_open")},
        "harmful_goal_met": d["harmful_edits"] == 0,
        "who_does_what": who_does_what(answers, truth, plans, items),
        "error_types": ERRORS,
        "failure_fix": load(DATA / "failure_fix.json") if (DATA / "failure_fix.json").exists() else None,
        "houses": houses,
        "part2": {
            "ingest": load(DATA / "ingest_scores.json") if (DATA / "ingest_scores.json").exists() else None,
            "estimate": estimate,
        },
    })
    print(f"export: {len(houses)} houses -> site/data/results.json")


if __name__ == "__main__":
    main()
