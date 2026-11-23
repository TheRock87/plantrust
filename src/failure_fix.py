"""The page's "one failure, one fix" story. The words are written by hand; every number is read from files.

  python -m src.failure_fix snapshot   # before the fix: keep the scores and the trace of the example room
  python -m src.failure_fix build      # after the fix and a rerun: write data/failure_fix.json for the page
"""
import shutil
import sys

from .common import DATA, TRACES, load, save

DIR = DATA / "failure_fix"
ROOM = "h07-r1"
HOUSE = "h07"


def snapshot():
    DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(DATA / "scores.json", DIR / "scores_before.json")
    shutil.copy(TRACES / f"{ROOM}.json", DIR / "trace_before.json")
    print("failure_fix: snapshot saved")


def build():
    before = load(DIR / "scores_before.json")["code_plus_agent"]
    after = load(DATA / "scores.json")["code_plus_agent"]
    t_before = load(DIR / "trace_before.json")
    t_after = load(TRACES / f"{ROOM}.json")
    n = load(DATA / "checks.json")[HOUSE][ROOM]["numbers"]
    cases = load(DATA / "regression_cases.json")
    agent_unclear = before["sent_to_drafter"] - after["sent_to_drafter"]
    story = {
        "summary": (f"The first run of the agent sent all {before['agent_rooms_run']} unclear rooms to a drafter, "
                    f"so it removed none of the {before['false_alarms']} false alarms the code checks had raised."),
        "steps": [
            {"title": "Read the trace",
             "text": (f"Room {ROOM}, a stairwell. Plan walls {n['plan_walls']}, tour walls {n['tour_walls']} ft "
                      f"(worst {n['worst_wall_diff_pct']:+g}%), ceiling {n['plan_ceiling']:g} ft in the plan and "
                      f"{n['tour_ceiling']:g} ft in the tour, doors {n['plan_doors']} and {n['tour_doors']}. "
                      f"Everything agrees within noise, yet the agent answered: \"{t_before['reason']}\"")},
            {"title": "Find the cause",
             "text": ("The agent repeated the code's warning as its verdict. The instruction said what the inputs "
                      "mean, but never that a warning is a reason to look at the numbers, not a reason to reject. "
                      "So 'when unsure, send to a drafter' won every time.")},
            {"title": "Add the case",
             "text": (f"{len(cases)} rooms became regression cases with the verdict a drafter would expect, "
                      f"including {ROOM} (accept) and a bathroom with a truly missing door (send to drafter). "
                      "tests/test_failure_fix.py fails if a rerun breaks any of them.")},
            {"title": "Change the instruction",
             "text": ("Each warning now says what to check: a weak spot or an overlap is fine when this room's "
                      "measurements match the tour; a label mismatch alone does not change quantities; a door-count "
                      "mismatch still goes to a drafter, because a missing door is a real error type.")},
            {"title": "Before, after",
             "text": (f"False alarms {before['false_alarms']} to {after['false_alarms']} of {after['clean_rooms']} "
                      f"clean rooms; errors caught {before['caught']} to {after['caught']} of {after['errors']}; "
                      f"rooms sent to a drafter {before['sent_to_drafter']} to {after['sent_to_drafter']} "
                      f"({agent_unclear} fewer). {ROOM} now: {t_after['verdict'].replace('_', ' ')}, "
                      f"\"{t_after['reason']}\"")},
        ],
    }
    save(DATA / "failure_fix.json", story)
    print("failure_fix: written")


if __name__ == "__main__":
    commands = {"snapshot": snapshot, "build": build}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit("usage: python -m src.failure_fix snapshot|build")
    commands[sys.argv[1]]()
