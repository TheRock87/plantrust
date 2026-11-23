"""Regression cases from the failure-and-fix story, checked against the latest agent run.

The agent itself is not called here (that costs model calls); this checks the verdicts the last
`make all` wrote. If a prompt change breaks one of these rooms, the next rerun makes this test fail.
"""
from src.common import DATA, load


def test_regression_cases_hold_in_the_latest_run():
    verdicts = load(DATA / "agent_verdicts.json")
    for case in load(DATA / "regression_cases.json"):
        assert case["room_id"] in verdicts, f"{case['room_id']} was not reviewed by the agent"
        assert verdicts[case["room_id"]]["verdict"] == case["expected"], case["why"]
