"""Run the whole pipeline (`make all` calls this).

Part 1: generate, plant, checks, agent, evaluate, failure-and-fix story.
Part 2: history, ingest, estimate. Export comes last and writes everything the page shows.
"""
from src import agent, checks, estimate, evaluate, export, failure_fix, generate, history, ingest, notes, plant

for step in (generate, plant, notes, checks, agent, evaluate):
    step.main()
if (failure_fix.DIR / "scores_before.json").exists():
    failure_fix.build()
for step in (history, ingest, estimate, export):
    step.main()
