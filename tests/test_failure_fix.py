"""Regression cases from the failure-and-fix story, checked against the latest agent run (data/agent_runs.json).

The agent itself is not called here (that costs model calls); this checks the answers the last run wrote.
If a code or prompt change breaks one of these questions, the next rerun makes this test fail.
"""
from src.common import DATA, load


def test_regression_cases_hold_in_the_latest_run():
    runs = load(DATA / "agent_runs.json")
    for case in load(DATA / "regression_cases.json"):
        assert case["key"] in runs, f"{case['key']} was not answered by the agent"
        assert runs[case["key"]]["action"] in case["expected"], f"{case['key']}: {case['why']}"
