"""v2 step 4: the keyword baseline (row C). These tests pin its naive behaviour; it is not meant to be clever."""
from src.baseline import answer
from src.checks import notes_questions
from src.common import DATA, load


def test_wet_keywords():
    assert answer("wet", "Took photos. Hall carpet is soaked.") == ("mark_wet", "Hall carpet is soaked.")
    assert answer("wet", "No water in the closet.") == ("mark_wet", "No water in the closet.")  # the negation trap
    assert answer("wet", "Took photos of every wall.") == ("no_change", "")


def test_door_keywords():
    assert answer("doors", "One opening is an archway, no door.") == ("no_change", "One opening is an archway, no door.")
    assert answer("doors", "No archway here, both openings have doors.")[0] == "no_change"  # the negation trap
    assert answer("doors", "Counted 2 doors in the bedroom.") == ("ask_drafter", "")


def test_every_notes_question_has_a_baseline_answer():
    questions = {(rid, i["kind"]) for rid, i in notes_questions(load(DATA / "checks.json"))}
    answered = {(p["room_id"], p["kind"]) for p in load(DATA / "proposals.json")["baseline"]}
    assert answered == questions
    scores = load(DATA / "scores.json")
    assert "C" in scores["rows"] and scores["hard"]["C"]["cases"] == len(load(DATA / "notes_hard.json"))
