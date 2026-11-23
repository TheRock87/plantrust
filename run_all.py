"""Run the whole pipeline (same as `make all`).

Part 1: generate, plant, checks, agent, evaluate, failure-and-fix story, export.
Part 2: history, ingest, estimate, then export again so the page gets both parts.
"""
from src import agent, checks, estimate, evaluate, export, failure_fix, generate, history, ingest, plant

for step in (generate, plant, checks, agent, evaluate):
    step.main()
if (failure_fix.DIR / "scores_before.json").exists():
    failure_fix.build()
for step in (export, history, ingest, estimate, export):
    step.main()
