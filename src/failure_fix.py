"""The page's "one failure, one fix" story. The words are written by hand; every number is read from files.

  python -m src.failure_fix snapshot   # before the fix: keep the scores, all agent answers, the example trace
  python -m src.failure_fix build      # after the fix and a rerun: write data/failure_fix.json for the page

The rerun repeats every model call, and the model is not fully repeatable, so `build` also counts the answers
that changed on questions the fix does not target (model variance), next to the change the fix made.
"""
import shutil
import sys

from .common import DATA, TRACES, load, save
from .evaluate import OFF_QUESTION

DIR = DATA / "failure_fix"
KEY = "h42-r1.doors"  # a door question the agent answered with mark_wet
STUCK = "h27-r5.doors"  # the regression case where the model wrote its add_door call as text


def snapshot():
    DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(DATA / "scores.json", DIR / "scores_before.json")
    shutil.copy(DATA / "agent_runs.json", DIR / "runs_before.json")
    shutil.copy(TRACES / f"{KEY}.json", DIR / "trace_before.json")
    print("failure_fix: snapshot saved")


def tool_call(trace, names):
    return next(s for s in trace["steps"] if s["type"] == "tool_call" and s["name"] in names)


def build():
    s_before, s_after = load(DIR / "scores_before.json"), load(DATA / "scores.json")
    before, after = s_before["rows"]["D"], s_after["rows"]["D"]
    r_before, r_after = load(DIR / "runs_before.json"), load(DATA / "agent_runs.json")
    t_before, t_after = load(DIR / "trace_before.json"), load(TRACES / f"{KEY}.json")
    if t_before["input_hash"] == t_after["input_hash"]:
        raise SystemExit("failure_fix: the example was not rerun after the fix (same input hash)")
    rid = KEY.split(".")[0]
    plan = next(r for h in load(DATA / "ai_plan.json").values() for r in h["rooms"] if r["id"] == rid)
    tour = next(h[rid] for h in load(DATA / "tour.json").values() if rid in h)
    note = load(DATA / "notes.json")[rid]
    bad = tool_call(t_before, ("mark_wet", "add_door"))
    cases = load(DATA / "regression_cases.json")
    no_answer = lambda runs: sum("no valid answer" in (r["reason"] or "") for k, r in runs.items() if "/" not in k)
    off = lambda runs: sum(r["action"] == OFF_QUESTION[k.split(".")[1]] for k, r in runs.items() if "/" not in k)
    # questions a fix targets: off-question answers (fix 1) and runs with no valid answer (fix 2, the reminder)
    targeted = {k for k, r in r_before.items() if "/" not in k and (r["action"] == OFF_QUESTION[k.split(".")[1]]
                                                                    or "no valid answer" in (r["reason"] or ""))}
    drift = sum(r_before[k]["action"] != r_after[k]["action"] for k in r_before
                if "/" not in k and k not in targeted and k in r_after)
    untouched = sum(1 for k in r_before if "/" not in k and k not in targeted)
    now = t_after["action"].replace("_", " ") + (f", \"{t_after['quote']}\"" if t_after["quote"] else "")
    story = {
        "variance": {"changed": drift, "of": untouched},
        "summary": (f"In the first full run, the agent answered {off(r_before)} door questions with mark_wet: "
                    "an edit for a different question. The drafter rejected each one, but each cost a review."),
        "steps": [
            {"title": "Read the trace",
             "text": (f"Question {KEY}: the plan shows {len(plan['doors'])} door, the tour counted {tour['doors']}. "
                      f"The note says only: \"{note}\" The agent called {bad['name']} with the quote "
                      f"\"{bad['args'].get('quote', '')}\": true, but about water, not doors.")},
            {"title": "Find the cause",
             "text": ("Every question got all seven tools. The model picked the edit it had evidence for, not the one "
                      "the question asked about. The prompt said to answer the question; with a small model, "
                      "a sentence in a prompt is a hope, not a rule.")},
            {"title": "Add the cases",
             "text": (f"{len(cases)} real questions became regression cases, including this one, a negation "
                      "(\"No water in the bedroom.\") and a note about another room. tests/test_failure_fix.py fails "
                      "if a rerun breaks any of them.")},
            {"title": "Change the code, not the prompt",
             "text": ("Each question now gets only its own tools and its own short prompt (a door question: "
                      "add_door, no_change, ask_drafter). The guard that checks quotes also refuses an edit for the "
                      "other question, so the drafter never sees one.")},
            {"title": "A second habit, a second code fix",
             "text": (f"The first rerun showed another weak-model habit: the model sometimes wrote its tool call as "
                      f"text instead of calling the tool, so the run ended with no valid answer. The runner now "
                      f"reminds it once. Runs with no valid answer: {no_answer(r_before)} before both fixes, "
                      f"{no_answer(r_after)} after. Regression case {STUCK}: "
                      f"{'holds' if r_after[STUCK]['action'] == 'add_door' else 'still fails'} "
                      f"({r_after[STUCK]['action'].replace('_', ' ')}).")},
            {"title": "Before, after",
             "text": (f"Off-question answers {off(r_before)} to {off(r_after)}; harmful edits {before['harmful_edits']} "
                      f"to {after['harmful_edits']}; errors fixed {before['fixed']} to {after['fixed']} and missed "
                      f"{before['missed']} to {after['missed']} of {after['errors']}; drafter items "
                      f"{before['manual_items']} to {after['manual_items']}. {KEY} now: {now}. "
                      f"The rerun repeats every model call: {drift} of {untouched} answers that no fix targets "
                      f"also changed, which is the model's own variance.")},
        ],
    }
    save(DATA / "failure_fix.json", story)
    print("failure_fix: written")
    for s in story["steps"]:
        print(f"  {s['title']}: {s['text']}")


if __name__ == "__main__":
    commands = {"snapshot": snapshot, "build": build}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit("usage: python -m src.failure_fix snapshot|build")
    commands[sys.argv[1]]()
