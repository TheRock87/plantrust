"""Score the verdicts against answers.json: catch rate, false alarms, drafter load, cost at risk caught."""
from .common import DATA, N_HOUSES, load, save
from .cost import room_cost
from .plant import ERRORS


def actual_cost_at_risk(truth_room, plan_room):
    """|cost from the AI plan - cost from the truth| for one room (whole truth cost if the room is missing)."""
    truth_usd = room_cost(truth_room)["usd"]
    plan_usd = room_cost(plan_room)["usd"] if plan_room else 0.0
    return round(abs(plan_usd - truth_usd), 2)


def final_verdicts(checks, agent, use_agent):
    """room_id -> (verdict, decided_by) for every room in every house."""
    out = {}
    for house in checks.values():
        for rid, chk in house.items():
            if chk["status"] == "pass":
                out[rid] = ("accept", "code")
            elif chk["status"] == "fail":
                out[rid] = ("send_to_drafter", "code")
            elif not use_agent:
                out[rid] = ("send_to_drafter", "code (unclear)")
            elif rid in agent:
                out[rid] = (agent[rid]["verdict"], "agent")
            else:
                out[rid] = ("send_to_drafter", "agent not run")
    return out


def score(verdicts, truth, plans, answers):
    err = {e["room_id"]: e["code"] for v in answers.values() for e in v}
    per_type = {c: {"caught": 0, "total": 0} for c in ERRORS}
    caught = total_err = false_alarm = clean = sent = 0
    usd_caught = usd_total = 0.0
    for hid, house in truth.items():
        plan_rooms = {r["id"]: r for r in plans[hid]["rooms"]}
        for r in house["rooms"]:
            to_drafter = verdicts[r["id"]][0] == "send_to_drafter"
            sent += to_drafter
            if r["id"] in err:
                code = err[r["id"]]
                usd = actual_cost_at_risk(r, plan_rooms.get(r["id"]))
                total_err += 1
                usd_total += usd
                per_type[code]["total"] += 1
                if to_drafter:
                    caught += 1
                    usd_caught += usd
                    per_type[code]["caught"] += 1
            else:
                clean += 1
                false_alarm += to_drafter
    return {
        "caught": caught, "errors": total_err,
        "false_alarms": false_alarm, "clean_rooms": clean,
        "sent_to_drafter": sent, "rooms": clean + total_err,
        "usd_at_risk_caught": round(usd_caught, 2), "usd_at_risk_total": round(usd_total, 2),
        "per_type": per_type,
    }


def main():
    truth, plans = load(DATA / "truth.json"), load(DATA / "ai_plan.json")
    answers, checks = load(DATA / "answers.json"), load(DATA / "checks.json")
    agent_path = DATA / "agent_verdicts.json"
    agent = load(agent_path) if agent_path.exists() else {}
    n_unclear = sum(1 for h in checks.values() for c in h.values() if c["status"] == "unclear")

    code_only = score(final_verdicts(checks, agent, False), truth, plans, answers)
    with_agent = score(final_verdicts(checks, agent, True), truth, plans, answers)
    llm_usd = sum(v["usage"]["usd"] for v in agent.values())
    code_only["llm_usd_per_house"] = 0.0
    with_agent["llm_usd_per_house"] = round(llm_usd / N_HOUSES, 5)
    with_agent["agent_rooms_run"] = len(agent)
    with_agent["agent_rooms_needed"] = n_unclear
    out = {"code_only": code_only, "code_plus_agent": with_agent,
           "agent_complete": len(agent) == n_unclear, "llm_usd_total": round(llm_usd, 4)}
    save(DATA / "scores.json", out)
    for name in ("code_only", "code_plus_agent"):
        s = out[name]
        print(f"{name:16s} caught {s['caught']}/{s['errors']}  false alarms {s['false_alarms']}/{s['clean_rooms']}  "
              f"to drafter {s['sent_to_drafter']}/{s['rooms']}  $ caught {s['usd_at_risk_caught']}/{s['usd_at_risk_total']}")
    if not out["agent_complete"]:
        print(f"evaluate: agent ran on {len(agent)} of {n_unclear} unclear rooms; the agent row is incomplete.")


if __name__ == "__main__":
    main()
