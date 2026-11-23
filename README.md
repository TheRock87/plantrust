# PlanTrust

Which rooms of an AI-drawn floor plan can you trust? A small review agent says, for every room: accept, or send to a human drafter, with the reason and the dollars at risk.

**Live page:** https://therock87.github.io/plantrust/ · **Video:** (2 minutes, link to come)

Built by Hossam El-Kharbotly for an application to the Senior Software Engineer, AI Agents role at DocuSketch. Synthetic data only; not affiliated with DocuSketch.

## How it works

1. **Plain-code checks** (`src/checks.py`): walls agree with the 360-degree tour, ceilings agree, rooms do not overlap, no tour room is missing from the plan. Clear cases are decided here, exactly and for free.
2. **A small agent** (`src/agent.py`), only for rooms the checks mark unclear (doors or labels that disagree, overlaps, stairwells, tall ceilings, glass walls). LangChain `create_agent`, one cheap model (Claude Haiku 5.5), 4 tools, a 6-step limit. Any failure sends the room to a drafter.
3. **Cost at risk** (`src/cost.py`): two illustrative items, wet drywall removal and drying fans (Institute of Inspection, Cleaning and Restoration Certification (IICRC) rule of thumb).

Data: 40 seeded synthetic houses (`src/generate.py`), with 0 to 2 planted errors each (`src/plant.py`): wall length, ceiling height, missing door, missing room, overlap.

## Results

See the page; `data/scores.json` holds the numbers. Every number on the page is written by `src/export.py`.

## Run it

```
uv sync
make all          # or: uv run python run_all.py
make test
make serve        # open http://localhost:8000
```

The agent step needs `ANTHROPIC_API_KEY` (environment or a local `.env`). Without it, unclear rooms go to the drafter and the page marks the agent row as pending. Traces in `traces/` are reused on later runs, so a rerun costs nothing; a hard cap stops spending at 4.50 USD.

## Limits

Synthetic rectangular houses, simple simulated tour noise, illustrative prices. It shows the method, not real accuracy. With real data: a test set from drafters' corrections, the vision team's real outputs, every miss added as a test case.
