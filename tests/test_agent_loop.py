"""v2 step 5: the drafting agent with a scripted fake model (offline, no key, no cost).

Covers: drafter approves, drafter rejects, bad quote / wrong room / bad wall (never reach the drafter),
two answers, step limit, errors, model fallback.
"""
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.agent import MAX_MODEL_STEPS, answer_question

NOTE = "Took photos of every wall. Hall carpet is soaked."
ROOM = {"id": "h99-r0", "label": "hallway", "polygon": [[0, 0], [10, 0], [10, 4], [0, 4]], "ceiling": 8.0,
        "doors": [{"wall": 0, "width": 3.0}], "affected": False, "flags": []}
TOUR = {"walls": [10.0, 4.0, 10.0, 4.0], "ceiling": 8.0, "doors": 2, "label": "hallway"}


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class FailingModel(ScriptedModel):
    def _generate(self, *args, **kwargs):
        raise RuntimeError("429 rate limit")


def call(name, args, i):  # also used by tests/test_part2.py
    return {"name": name, "args": args, "id": f"c{i}{name}", "type": "tool_call"}


def ai(*calls, text=""):
    return AIMessage(content=text, tool_calls=[call(n, a, i) for i, (n, a) in enumerate(calls)])


WET = ("mark_wet", {"room_id": "h99-r0", "quote": "Hall carpet is soaked."})
SAME = ("no_change", {"room_id": "h99-r0", "quote": "Took photos of every wall."})


def run(script, decision="approve", kind="wet", fallbacks=()):
    asked = []

    def decide(p):
        asked.append(p)
        return decision

    model = script if isinstance(script, GenericFakeChatModel) else ScriptedModel(messages=iter(script))
    res = answer_question("h99-r0", kind, ROOM, TOUR, NOTE, model, decide, fallbacks)
    return res, asked


def test_drafter_approves_and_the_draft_changes():
    res, asked = run([ai(("get_notes", {"room_id": "h99-r0"})), ai(WET), ai(text="Marked wet.")])
    assert res["action"] == "mark_wet" and res["decision"] == "approve" and res["error"] is None
    assert len(asked) == 1 and asked[0]["quote_or_evidence"] == "Hall carpet is soaked." and asked[0]["by"] == "agent"
    assert res["draft"]["affected"] is True and ROOM["affected"] is False  # only the draft copy changes
    assert res["model_calls"] == 3


def test_drafter_rejects_no_retry():
    res, asked = run([ai(WET), ai(text="should never be reached")], decision="reject")
    assert res["action"] == "mark_wet" and res["decision"] == "reject"
    assert len(asked) == 1 and res["draft"]["affected"] is False and res["model_calls"] == 1


def test_bad_quote_never_reaches_the_drafter_then_agent_retries():
    bad = ("mark_wet", {"room_id": "h99-r0", "quote": "the carpet is wet"})
    res, asked = run([ai(bad), ai(SAME), ai(text="No change.")])
    assert asked == [] and res["action"] == "no_change" and res["quote"] == "Took photos of every wall."
    assert "exactly" in [s for s in res["steps"] if s["type"] == "tool_result"][0]["text"]


def test_no_valid_answer_goes_to_drafter():
    bad = ("mark_wet", {"room_id": "h99-r0", "quote": "carpet is wet"})
    wrong_room = ("mark_wet", {"room_id": "h01-r1", "quote": "Hall carpet is soaked."})
    res, asked = run([ai(bad), ai(wrong_room), ai(text="I give up.")])
    assert asked == [] and res["action"] == "ask_drafter" and res["draft"]["affected"] is False


def test_bad_wall_never_reaches_the_drafter():
    door = ("add_door", {"room_id": "h99-r0", "wall": 7, "quote": "Hall carpet is soaked."})
    res, asked = run([ai(door), ai(text="Done.")], kind="doors")
    assert asked == [] and res["action"] == "ask_drafter" and len(res["draft"]["doors"]) == 1


def test_add_door_approved_on_a_wet_room():
    wet_room = {**ROOM, "affected": True}
    door = ("add_door", {"room_id": "h99-r0", "wall": 2, "quote": "Took photos of every wall."})
    model = ScriptedModel(messages=iter([ai(door), ai(text="Door added.")]))
    asked = []
    res = answer_question("h99-r0", "doors", wet_room, TOUR, NOTE, model, lambda p: asked.append(p) or "approve")
    assert res["action"] == "add_door" and res["decision"] == "approve" and res["args"] == {"wall": 2}
    assert len(res["draft"]["doors"]) == 2 and asked[0]["est_cost_at_risk_usd"] >= 0  # a door removes wall area


def test_add_door_refused_when_the_tour_counted_fewer_doors():
    # Plan 1 door, tour 0: the tour missed a door, so a new door can only be wrong. Code refuses it, not the prompt.
    door = ("add_door", {"room_id": "h99-r0", "wall": 1, "quote": "Took photos of every wall."})
    model = ScriptedModel(messages=iter([ai(door), ai(text="Done.")]))
    asked = []
    res = answer_question("h99-r0", "doors", ROOM, {**TOUR, "doors": 0}, NOTE, model, lambda p: asked.append(p))
    assert asked == [] and res["action"] == "ask_drafter" and len(res["draft"]["doors"]) == 1
    assert "fewer doors" in [s for s in res["steps"] if s["type"] == "tool_result"][0]["text"]


def test_unreviewed_edit_is_refused_by_the_tool():
    # "2.0" fails the gate's check, so there is no pause; the schema turns it into 2 and the tool sees a valid call.
    door = ("add_door", {"room_id": "h99-r0", "wall": 2.0, "quote": "Took photos of every wall."})
    res, asked = run([ai(door), ai(text="Done.")], kind="doors")
    assert asked == [] and res["action"] == "ask_drafter" and len(res["draft"]["doors"]) == 1
    assert "approval" in [s for s in res["steps"] if s["type"] == "tool_result"][0]["text"]


def test_two_answers_go_to_drafter():
    res, asked = run([ai(WET, SAME), ai(text="Done.")])
    assert asked == [] and res["action"] == "ask_drafter"
    res, asked = run([ai(SAME), ai(("ask_drafter", {"room_id": "h99-r0", "question": "Wet?"})), ai(text="Done.")])
    assert res["action"] == "ask_drafter" and "more than one" in res["reason"]


def test_step_limit_goes_to_drafter_after_exactly_the_limit():
    script = iter([ai(("get_notes", {"room_id": "h99-r0"})) for _ in range(20)])
    res, asked = run(ScriptedModel(messages=script))
    assert res["action"] == "ask_drafter" and "limit" in res["error"].lower()
    assert res["model_calls"] == MAX_MODEL_STEPS and len(list(script)) == 20 - MAX_MODEL_STEPS


def test_error_after_a_recorded_answer_goes_to_drafter():
    res, asked = run([ai(SAME)])  # the finishing model turn fails: the script is empty
    assert res["action"] == "ask_drafter" and res["error"]


def test_fallback_model_takes_over_when_main_model_fails():
    backup = ScriptedModel(messages=iter([ai(SAME), ai(text="No change.")]))
    res, _ = run(FailingModel(messages=iter([])), fallbacks=[backup])
    assert res["action"] == "no_change" and res["error"] is None


def test_both_models_failing_goes_to_drafter():
    res, _ = run(FailingModel(messages=iter([])), fallbacks=[FailingModel(messages=iter([]))])
    assert res["action"] == "ask_drafter" and "429" in res["error"]
