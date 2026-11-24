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


def test_dashboard_is_plain_and_stateless():
    # Brief 7.1: no chart library, no build step, no browser storage; state lives in memory and resets on reload.
    from src.common import ROOT
    js, html = (ROOT / "site" / "app.js").read_text(encoding="utf-8"), (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert 'id="dashboard"' in html and html.count("<script") == 1 and 'type="range"' in html
    assert not any(w in js for w in ("localStorage", "sessionStorage", "indexedDB", "document.cookie"))
    assert "Goal not met" not in js and "harmful_goal_met" not in js  # removed at the author's request


def test_triage_is_sorted_for_the_review_budget_slider():
    # The slider walks the houses in triage order; the dollars must fall, and every house must be there.
    tri = R["scores"]["triage"]
    assert len(tri) == R["totals"]["houses"]
    assert [h["usd_at_risk"] for h in tri] == sorted((h["usd_at_risk"] for h in tri), reverse=True)


def test_part2_precision_column():
    s = R["part2"]["estimate"]["scores"]
    for name in ("frequency_rule", "agent"):
        v = s[name]
        assert v["precision"] == round(v["found"] / (v["found"] + v["extra"]), 3)
    assert all(d["drafted_by"] == "agent" for d in R["part2"]["estimate"]["demos"])
