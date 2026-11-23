"""Write site/data/results.json: everything the page shows, computed by the scripts (no hand-typed numbers)."""
from .common import DATA, N_HOUSES, SITE_DATA, TRACES, load, save
from .evaluate import actual_cost_at_risk, final_verdicts
from .plant import ERRORS
from .agent import MODEL

N_VIEWER = 10


def pick_houses(answers, checks):
    """10 houses for the viewer: cover every error type and agent-decided rooms, plus one clean house."""
    chosen, seen = [], set()
    for hid in sorted(answers):
        codes = {e["code"] for e in answers[hid]}
        if codes - seen:
            chosen.append(hid)
            seen |= codes
    for hid in sorted(answers):
        if len(chosen) >= N_VIEWER - 1:
            break
        unclear = any(c["status"] == "unclear" for c in checks[hid].values())
        if hid not in chosen and answers[hid] and unclear:
            chosen.append(hid)
    clean = [h for h in sorted(answers) if not answers[h]]
    if clean:
        chosen.append(clean[0])
    return sorted(chosen[:N_VIEWER])


def main():
    truth, plans, tours = load(DATA / "truth.json"), load(DATA / "ai_plan.json"), load(DATA / "tour.json")
    answers, checks, scores = load(DATA / "answers.json"), load(DATA / "checks.json"), load(DATA / "scores.json")
    agent_path = DATA / "agent_verdicts.json"
    agent = load(agent_path) if agent_path.exists() else {}
    verdicts = final_verdicts(checks, agent, True)
    fix_path = DATA / "failure_fix.json"

    houses = []
    for hid in pick_houses(answers, checks):
        err = {e["room_id"]: e for e in answers[hid]}
        plan_rooms = {r["id"]: r for r in plans[hid]["rooms"]}
        rooms = []
        for t in truth[hid]["rooms"]:
            rid = t["id"]
            chk = checks[hid][rid]
            p = plan_rooms.get(rid)
            trace_path = TRACES / f"{rid}.json"
            steps = load(trace_path)["steps"] if (rid in agent and trace_path.exists()) else []
            verdict, by = verdicts[rid]
            rooms.append({
                "id": rid,
                "label": (p or t)["label"],
                "polygon": (p or t)["polygon"],
                "missing_from_plan": p is None,
                "ceiling": p["ceiling"] if p else None,
                "affected": (p or t)["affected"],
                "check_status": chk["status"],
                "check_reasons": chk["reasons"],
                "numbers": chk["numbers"],
                "est_cost_at_risk_usd": chk["est_cost_at_risk_usd"],
                "verdict": verdict,
                "decided_by": by,
                "agent_reason": agent.get(rid, {}).get("reason"),
                "agent_steps": steps,
                "answer_key": ({"code": err[rid]["code"], "name": ERRORS[err[rid]["code"]],
                                "detail": err[rid]["detail"],
                                "actual_cost_at_risk_usd": actual_cost_at_risk(t, p)} if rid in err else None),
            })
        houses.append({"id": hid, "rooms": rooms, "n_errors": len(err)})

    totals = {
        "houses": N_HOUSES,
        "rooms": sum(len(h["rooms"]) for h in truth.values()),
        "errors": sum(len(v) for v in answers.values()),
        "clean_houses": sum(1 for v in answers.values() if not v),
        "check_counts": {s: sum(1 for h in checks.values() for c in h.values() if c["status"] == s)
                         for s in ("pass", "fail", "unclear")},
    }
    save(SITE_DATA / "results.json", {
        "model": MODEL,
        "totals": totals,
        "scores": scores,
        "error_types": ERRORS,
        "failure_fix": load(fix_path) if fix_path.exists() else None,
        "houses": houses,
    })
    print(f"export: {len(houses)} houses -> site/data/results.json")


if __name__ == "__main__":
    main()
