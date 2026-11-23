"""Run the whole pipeline (same as `make all`): generate, plant, check, agent, evaluate, export."""
from src import agent, checks, evaluate, export, generate, plant

for step in (generate, plant, checks, agent, evaluate, export):
    step.main()
