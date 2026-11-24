"""v2 step 8: site/data/results.json holds only script numbers, consistent with data/scores.json."""
from src.common import DATA, SITE_DATA, load

R = load(SITE_DATA / "results.json")
SCORES = load(DATA / "scores.json")


def test_page_scores_are_the_script_scores():
    for k in ("rows", "row_names", "hard", "ladder", "triage", "run_report"):
        assert R["scores"][k] == SCORES[k]


def test_honest_comparisons_come_from_the_numbers():
    c, d = SCORES["rows"]["C"], SCORES["rows"]["D"]
    cmp = R["agent_vs_baseline"]
    for m in ("fixed", "missed", "harmful_edits", "manual_items", "false_alarm_rooms", "usd_open"):
        assert cmp[m] == {"agent": d[m], "baseline": c[m], "agent_better": d[m] > c[m] if m == "fixed" else d[m] < c[m]}
    assert R["harmful_goal_met"] == (d["harmful_edits"] == 0)


def test_who_does_what_covers_every_error():
    rows = R["who_does_what"]
    assert sum(r["count"] for r in rows) == SCORES["rows"]["D"]["errors"]
    for r in rows:
        assert r["who"] in ("code", "agent", "drafter") and r["why"]
        assert r["approved"] <= r["edits"]


def test_open_questions_carry_dollars():
    # A wet question left to the drafter still puts dollars at risk: the cost if the room is wet.
    plans = {r["id"]: r for h in load(DATA / "ai_plan.json").values() for r in h["rooms"]}
    for p in load(DATA / "proposals.json")["agent"]:
        if p["action"] == "ask_drafter" and p["kind"] == "wet":
            assert p["est_cost_at_risk_usd"] > 0, p["room_id"]


def test_viewer_shows_failures_too():
    items = [i for h in R["houses"] for r in h["rooms"] for i in r["items"]]
    assert any(i["by"] == "agent" and i.get("decision") == "reject" for i in items)
    assert any(i["action"] == "ask_drafter" for i in items)
    assert all(h["triage"]["status"] in ("ready", "quick review", "full review") for h in R["houses"])


def test_part2_precision_column():
    s = R["part2"]["estimate"]["scores"]
    for name in ("frequency_rule", "agent"):
        v = s[name]
        assert v["precision"] == round(v["found"] / (v["found"] + v["extra"]), 3)
    assert all(d["drafted_by"] == "agent" for d in R["part2"]["estimate"]["demos"])
