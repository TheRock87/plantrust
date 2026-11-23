"""Run the whole pipeline (same as `make all`).

Part 1: generate, plant, checks, agent, evaluate, export.
Part 2: history, ingest, estimate, then export again so the page gets both parts.
"""
from src import agent, checks, estimate, evaluate, export, generate, history, ingest, plant

for step in (generate, plant, checks, agent, evaluate, export, history, ingest, estimate, export):
    step.main()
