"""v2 step 6: checks on what the live run wrote (proposals, hard set, scores). No model call here."""
from src.checks import notes_questions
from src.common import DATA, load
from src.evaluate import ladder_status

SCORES = load(DATA / "scores.json")


def test_ladder_rule():
    assert ladder_status(20, 20) == "auto-apply"
    assert ladder_status(19, 20) == "auto-apply"            # 95 % is enough
    assert ladder_status(18, 20) == "keep the drafter check"
    assert ladder_status(10, 10) == "not enough cases yet"  # N < 20


def test_every_question_has_one_agent_answer_and_edits_were_decided():
    questions = sorted((rid, i["kind"]) for rid, i in notes_questions(load(DATA / "checks.json")))
    agent = load(DATA / "proposals.json")["agent"]
    assert sorted((p["room_id"], p["kind"]) for p in agent) == questions
    for p in agent:
        assert p["by"] == "agent"
        if p["action"] in ("add_door", "mark_wet"):
            assert p["decision"] in ("approve", "reject") and "field_was_right" in p
            assert not (p["decision"] == "approve" and p["field_was_right"])  # the drafter never lets harm through


def test_rows_hard_set_and_report():
    assert set(SCORES["rows"]) == {"v1", "B", "C", "D"}
    hard = load(DATA / "notes_hard.json")
    assert SCORES["hard"]["D"]["cases"] == SCORES["hard"]["C"]["cases"] == len(hard)
    rep = SCORES["run_report"]
    assert rep["questions"] == rep["answered"] + rep["not_run"] and rep["usd"] == 0
    for step in SCORES["ladder"]:
        assert step["status"] == ladder_status(step["approved"], step["n"])
    for h in SCORES["triage"]:
        assert h["status"] == ("full review" if h["manual"] else "quick review" if h["edits"] else "ready")
    usd = [h["usd_at_risk"] for h in SCORES["triage"]]
    assert usd == sorted(usd, reverse=True)
