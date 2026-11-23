"""Offline tests of the agent wrapper with a scripted fake model (no API key, no cost)."""
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.agent import review_room


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


ROOM = {"id": "h99-r0", "label": "living", "polygon": [[0, 0], [10, 0], [10, 12], [0, 12]],
        "ceiling": 16.0, "doors": [{"wall": 0, "width": 3.0}], "affected": True, "flags": ["tall_ceiling"]}
TOUR = {"walls": [10.1, 11.9, 10.0, 12.1], "ceiling": 15.8, "doors": 1, "label": "living"}
CHECK = {"status": "unclear", "reasons": ["Known weak spot for scanners: tall ceiling"],
         "numbers": {}, "est_cost_at_risk_usd": 3.1}


def call(name, args, i):
    return {"name": name, "args": args, "id": f"c{i}", "type": "tool_call"}


def test_agent_uses_tools_then_accepts():
    model = ScriptedModel(messages=iter([
        AIMessage(content="", tool_calls=[call("get_tour", {"room_id": "h99-r0"}, 1)]),
        AIMessage(content="", tool_calls=[call("submit_verdict", {"room_id": "h99-r0", "verdict": "accept",
                                                                   "reason": "Ceiling 16 vs 15.8 ft."}, 2)]),
    ]))
    res = review_room("h99-r0", ROOM, TOUR, CHECK, model)
    assert res["verdict"] == "accept"
    assert [s["name"] for s in res["steps"] if s["type"] == "tool_call"] == ["get_tour", "submit_verdict"]


def test_no_verdict_goes_to_drafter():
    model = ScriptedModel(messages=iter([AIMessage(content="I think it is fine.")]))
    res = review_room("h99-r0", ROOM, TOUR, CHECK, model)
    assert res["verdict"] == "send_to_drafter"


def test_invalid_verdict_value_goes_to_drafter():
    model = ScriptedModel(messages=iter([
        AIMessage(content="", tool_calls=[call("submit_verdict", {"room_id": "h99-r0", "verdict": "maybe",
                                                                   "reason": "?"}, 1)]),
        AIMessage(content="done"),
    ]))
    res = review_room("h99-r0", ROOM, TOUR, CHECK, model)
    assert res["verdict"] == "send_to_drafter"


def test_step_limit_goes_to_drafter():
    loop = [AIMessage(content="", tool_calls=[call("get_room", {"room_id": "h99-r0"}, i)]) for i in range(20)]
    res = review_room("h99-r0", ROOM, TOUR, CHECK, ScriptedModel(messages=iter(loop)))
    assert res["verdict"] == "send_to_drafter"
    assert "Recursion" in (res["error"] or "")
