"""Part 2 tests: price sources, ingestion layers, quantities, scoring, and the estimation agent loop (offline)."""
import pytest
from langchain_core.messages import AIMessage

from src.estimate import History, run_agent, score
from src.history import quantities
from src.ingest import exact, fuzzy
from src.prices import CATALOG, MockPriceSource, XactimatePriceSource
from tests.test_agent_loop import ScriptedModel, call

JOB = {"id": "T1", "room_type": "bathroom", "loss_category": 2, "width": 10.0, "depth": 8.0, "ceiling": 8.0,
       "doors": 1, "windows": 0, "registers": 1, "contents_heavy": False, "region": "FL-TAMPA", "month": "2026-10",
       "notes": "Category 2 water: toilet overflowed. Tile floor. Floor register in the wet area."}


def test_mock_prices_vary_by_region_and_month():
    m = MockPriceSource()
    assert m.get_price("EQ-AIRM-DAY", "FL-TAMPA", "2026-01") == 30.0
    assert m.get_price("EQ-AIRM-DAY", "CA-SACRAMENTO", "2026-01") > 30.0
    assert m.get_price("EQ-AIRM-DAY", "FL-TAMPA", "2026-10") > 30.0


def test_xactimate_source_is_a_stub():
    with pytest.raises(NotImplementedError):
        XactimatePriceSource().get_price("EQ-AIRM-DAY", "FL-TAMPA", "2026-10")


def test_exact_layer_ignores_case_and_punctuation():
    assert exact("AIR MOVER per 24 hour period") == "EQ-AIRM-DAY"
    assert exact("air movers") is None


def test_fuzzy_layer_needs_a_clear_winner():
    assert fuzzy("REMOVE BASEBOARD")[0] == "BSB-RMV-LF"
    assert fuzzy("remove wet carpet")[0] is None  # too close to "remove wet carpet pad": goes on to the model
    assert fuzzy("air movers")[0] == "EQ-AIRM-DAY"
    assert fuzzy("demo")[0] is None


def test_quantities_come_from_room_size():
    q = quantities(JOB)
    assert q["floor_sf"] == 80 and q["perimeter_lf"] == 36 and q["flood_cut_lf"] == 33


def test_every_catalog_basis_has_a_quantity():
    q = quantities(JOB)
    assert all(basis in q for (_d, _u, basis, _p, _m) in CATALOG.values())


def test_score_counts_found_missed_extra():
    s = score({"a": [{"code": "EQ-AIRM-DAY"}, {"code": "PPE-EA"}]}, {"a": {"EQ-AIRM-DAY", "WIN-SCR-DR"}})
    assert (s["found"], s["missed"], s["extra"], s["often_missed_caught"], s["often_missed_total"]) == (1, 1, 1, 0, 1)


def test_estimation_agent_loop_offline():
    model = ScriptedModel(messages=iter([
        AIMessage(content="", tool_calls=[call("item_frequency", {"room_type": "bathroom", "loss_category": 2}, 1)]),
        AIMessage(content="", tool_calls=[call("submit_draft", {"room_id": "T1", "items": [
            {"code": "EQ-AIRM-DAY", "reason": "always"}, {"code": "HVAC-REG-CLN", "reason": "register in notes"}]}, 2)]),
    ]))
    res = run_agent(JOB, History(), model)
    assert [i["code"] for i in res["items"]] == ["EQ-AIRM-DAY", "HVAC-REG-CLN"]


def test_invalid_code_is_rejected():
    model = ScriptedModel(messages=iter([
        AIMessage(content="", tool_calls=[call("submit_draft", {"room_id": "T1", "items": [
            {"code": "XM-MADE-UP", "reason": "?"}]}, 1)]),
        AIMessage(content="done"),
    ]))
    assert run_agent(JOB, History(), model)["items"] is None
