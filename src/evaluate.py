"""Score against answers.json.

v1 functions (final_verdicts, score) stay for estimate.py and export.py.
v2 rows (score_row): v1 reference, B (code checks + code fixes), C (B + keyword baseline); D comes in step 6.
"""
from collections import Counter

from . import llm
from .baseline import answer as baseline_answer
from .checks import notes_questions
from .common import DATA, load, save
from .cost import room_cost
from .fixes import EDITS
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


def ask(rid, kind, why, by):
    return {"room_id": rid, "kind": kind, "action": "ask_drafter", "args": {"question": f"check: {why}"}, "by": by}


def v1_items(checks):
    """v1 reference: every room that does not pass goes to a drafter; no edits."""
    return [ask(rid, "v1", "; ".join(c["reasons"]), "code") for h in checks.values() for rid, c in h.items()
            if c["status"] != "pass"]


def score_row(items, truth, plans, answers):
    """Outcome of each planted error: fixed (an approved edit), to_drafter (manual item or rejected edit), or missed.

    Units: manual items and harmful edits are counted per item; false alarms per clean room (as in v1).
    """
    err = {e["room_id"]: e["code"] for v in answers.values() for e in v}
    by_room = {}
    for it in items:
        by_room.setdefault(it["room_id"], []).append(it)
    edits = [i for i in items if i["action"] in EDITS]
    per_type = {c: {"fixed": 0, "to_drafter": 0, "missed": 0, "total": 0} for c in ERRORS}
    false_alarms = clean = 0
    usd_open = usd_total = 0.0
    for hid, house in truth.items():
        plan_rooms = {r["id"]: r for r in plans[hid]["rooms"]}
        for r in house["rooms"]:
            its = by_room.get(r["id"], [])
            if r["id"] not in err:
                clean += 1
                false_alarms += any(i["action"] != "no_change" for i in its)
                continue
            usd = actual_cost_at_risk(r, plan_rooms.get(r["id"]))
            usd_total += usd
            if any(i.get("decision") == "approve" and not i["field_was_right"] for i in its):
                outcome = "fixed"
            elif any(i["action"] == "ask_drafter" or i.get("decision") == "reject" for i in its):
                outcome = "to_drafter"
            else:
                outcome = "missed"
                usd_open += usd
            per_type[err[r["id"]]][outcome] += 1
            per_type[err[r["id"]]]["total"] += 1
    total = {k: sum(t[k] for t in per_type.values()) for k in ("fixed", "to_drafter", "missed", "total")}
    return {
        "errors": total["total"], "fixed": total["fixed"], "to_drafter": total["to_drafter"], "missed": total["missed"],
        "harmful_edits": sum(i["field_was_right"] for i in edits),
        "approved_edits": sum(i["decision"] == "approve" for i in edits),
        "rejected_edits": sum(i["decision"] == "reject" for i in edits),
        "manual_items": sum(i["action"] == "ask_drafter" for i in items) + sum(i["decision"] == "reject" for i in edits),
        "false_alarm_rooms": false_alarms, "clean_rooms": clean,
        "usd_open": round(usd_open, 2), "usd_total": round(usd_total, 2),
        "per_type": per_type,
    }


def hard_score(cases, decide):
    """Hand-written hard notes: how often `decide(case)` gives the expected action."""
    per = [{"id": c["id"], "expected": c["expected"], "got": decide(c)} for c in cases]
    return {"right": sum(p["got"] == p["expected"] for p in per), "cases": len(per), "per_case": per}


ROW_NAMES = {"v1": "v1: code checks only, every doubt to a drafter",
             "B": "B: code checks + code fixes; door and wet questions to a drafter",
             "C": "C: B + keyword baseline on the notes",
             "D": "D: B + agent on the notes"}
HARD_KIND = {"wet": "wet", "door": "doors"}  # hard-set question -> route kind
LADDER_RATE, LADDER_MIN_N = 0.95, 20


def ladder_status(approved, n):
    if n < LADDER_MIN_N:
        return "not enough cases yet"
    return "auto-apply" if approved / n >= LADDER_RATE else "keep the drafter check"


def ladder(items):
    """Per fix type (who + action) in one row: approved X of N, and whether it may skip the drafter."""
    out = {}
    for i in items:
        if i["action"] in EDITS:
            s = out.setdefault((i["by"], i["action"]), {"by": i["by"], "action": i["action"], "approved": 0, "n": 0})
            s["n"] += 1
            s["approved"] += i["decision"] == "approve"
    return [dict(s, status=ladder_status(s["approved"], s["n"])) for s in out.values()]


def triage(items, house_ids):
    """Per house, what a drafter faces: ready (nothing open), quick review (only edits), full review (manual items)."""
    houses = {hid: {"edits": 0, "manual": 0, "usd_at_risk": 0.0} for hid in house_ids}
    for i in items:
        if i["action"] == "no_change":
            continue
        h = houses[i["room_id"].split("-")[0]]
        h["edits" if i["action"] in EDITS else "manual"] += 1
        h["usd_at_risk"] = round(h["usd_at_risk"] + i.get("est_cost_at_risk_usd", 0.0), 2)
    return sorted(({"house": hid, **h, "status": "full review" if h["manual"] else "quick review" if h["edits"]
                    else "ready"} for hid, h in houses.items()), key=lambda h: (-h["usd_at_risk"], h["house"]))


def run_report(questions, runs):
    """Model called for N of M questions, failures, fallback uses, tokens, seconds per question."""
    fallback = llm.FALLBACK.split(":")[-1].replace("-latest", "")
    data = {k: r for k, r in runs.items() if not k.startswith("hard/")}
    used = [r for r in data.values() if r["model_calls"]]
    return {"questions": len(questions), "answered": len(data), "not_run": len(questions) - len(data),
            "model_called": len(used), "failures": sum(bool(r["error"]) for r in data.values()),
            "fallback_uses": sum(any(fallback in m for m in r["usage"]["models"]) for r in data.values()),
            "tokens": sum(r["usage"]["input_tokens"] + r["usage"]["output_tokens"] for r in data.values()),
            "usd": round(sum(r["usage"]["usd"] for r in data.values()), 6),
            "avg_seconds": round(sum(r["seconds"] for r in used) / max(len(used), 1), 1),
            "ask_drafter_by_reason": dict(Counter(
                "error" if r["error"] else "more than one answer" if "more than one" in (r["reason"] or "")
                else "no valid answer" if "no valid answer" in (r["reason"] or "") else "agent chose it"
                for r in data.values() if r["action"] == "ask_drafter"))}


def main():
    truth, plans = load(DATA / "truth.json"), load(DATA / "ai_plan.json")
    answers, checks = load(DATA / "answers.json"), load(DATA / "checks.json")
    proposals, hard = load(DATA / "proposals.json"), load(DATA / "notes_hard.json")
    questions = notes_questions(checks)
    unread = [ask(rid, i["kind"], i["why"], "code (note not read)") for rid, i in questions]
    answered = {(p["room_id"], p["kind"]) for p in proposals.get("agent", [])}
    not_run = [ask(rid, i["kind"], i["why"], "agent not run") for rid, i in questions
               if (rid, i["kind"]) not in answered]
    agent_items = proposals["code"] + proposals.get("agent", []) + not_run
    rows = {"v1": score_row(v1_items(checks), truth, plans, answers),
            "B": score_row(proposals["code"] + unread, truth, plans, answers),
            "C": score_row(proposals["code"] + proposals["baseline"], truth, plans, answers),
            "D": score_row(agent_items, truth, plans, answers)}
    agent_hard = load(DATA / "agent_hard.json") if (DATA / "agent_hard.json").exists() else {}
    hard_rows = {"C": hard_score(hard, lambda c: baseline_answer(HARD_KIND[c["question"]], c["note"])[0]),
                 "D": hard_score(hard, lambda c: agent_hard.get(c["id"], "not run"))}
    runs = load(DATA / "agent_runs.json") if (DATA / "agent_runs.json").exists() else {}
    out = {"rows": rows, "row_names": ROW_NAMES, "hard": hard_rows,
           "notes_questions": dict(Counter(i["kind"] for _, i in questions)),
           "ladder": ladder(agent_items), "triage": triage(agent_items, truth), "run_report": run_report(questions, runs)}
    save(DATA / "scores.json", out)
    rep = out["run_report"]
    if not_run:
        print(f"evaluate: the agent has not answered {len(not_run)} of {len(questions)} questions; row D is incomplete.")
    print(f"run report: model called for {rep['model_called']} of {rep['questions']} questions, "
          f"{rep['failures']} failures, {rep['fallback_uses']} fallback uses, {rep['tokens']} tokens, "
          f"{rep['usd']} USD, {rep['avg_seconds']} s per question; ask_drafter: {rep['ask_drafter_by_reason']}")
    for s in out["ladder"]:
        print(f"ladder: {s['by']:5} {s['action']:14} approved {s['approved']} of {s['n']}: {s['status']}")
    print("triage (row D):", dict(Counter(h["status"] for h in out["triage"])))
    print(f"{'row':4} {'fixed':>9} {'to drafter':>11} {'missed':>9} {'harmful':>8} {'manual':>7} "
          f"{'false alarms':>13} {'$ open':>18}")
    for name, s in rows.items():
        n = s["errors"]
        print(f"{name:4} {s['fixed']:>4} of {n:<2} {s['to_drafter']:>5} of {n:<2} {s['missed']:>4} of {n:<2} "
              f"{s['harmful_edits']:>8} {s['manual_items']:>7} {s['false_alarm_rooms']:>6} of {s['clean_rooms']:<4} "
              f"{s['usd_open']:>8.0f} of {s['usd_total']:<7.0f}")
    for name, s in rows.items():
        print(f"{name} per type (fixed/to drafter/missed of N): " + "  ".join(
            f"{c} {t['fixed']}/{t['to_drafter']}/{t['missed']} of {t['total']}" for c, t in s["per_type"].items()))
    for name, h in hard_rows.items():
        wrong = [f"{p['id']} {p['got']} (expected {p['expected']})" for p in h["per_case"] if p["got"] != p["expected"]]
        print(f"{name} on the hard set: {h['right']} of {h['cases']} right; wrong: " + "; ".join(wrong))


if __name__ == "__main__":
    main()
