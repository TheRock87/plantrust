# PlanTrust

A small drafting agent for AI-drawn floor plans. Code fixes what a rule can fix; the agent proposes an edit only where the technician's notes decide (is this room wet? is a door missing?); a drafter approves or rejects every edit. Scripts measure the result against a keyword baseline.

**Live page:** https://therock87.github.io/plantrust/

Built by Hossam El-Kharbotly for an application to the Senior Software Engineer, AI Agents role at DocuSketch. Synthetic data only; not affiliated with DocuSketch. How I directed the coding agent: [CLAUDE.md](CLAUDE.md).

## How it works

1. **Data** (`src/generate.py`, `src/plant.py`, `src/notes.py`): seeded synthetic houses, a simulated 360-degree tour, technician notes from phrase banks, and planted errors (walls, ceilings, missing doors, missing rooms, overlaps, wet rooms left out).
2. **Code** (`src/checks.py`, `src/fixes.py`): routes every room; proposes wall and ceiling fixes from the tour; asks a drafter to draw a missing room.
3. **Agent** (`src/agent.py`): LangChain `create_agent` with Mistral `voxtral-small-latest` (free mode). One question per run, only that question's tools, a quote guard in code, `HumanInTheLoopMiddleware` before every edit, a model-call limit. Any failure goes to the drafter.
4. **Drafter** (`src/drafter.py`): simulated in the test run; it knows the true house and approves an edit only if it fixes a wrong field.
5. **Scoring** (`src/baseline.py`, `src/evaluate.py`, `src/failure_fix.py`): rows v1, code fixes, keyword baseline and agent on the same rooms; a hand-written hard set; an autonomy ladder; a run report; a failure-and-fix story.
6. **Part 2** (`src/history.py`, `src/ingest.py`, `src/estimate.py`): drafts mitigation line items for a trusted room from past jobs, with a mock price source.

Every number on the page is written by `src/export.py` into `site/data/results.json`; `data/scores.json` holds the scores.

## Run it

```
uv sync
uv run python run_all.py      # or: make all
uv run pytest -q              # offline, with a scripted fake model
uv run python -m http.server 8000 -d site
```

Agent answers are cached in `traces/`, keyed by the inputs, prompt and tools; with a complete cache a rerun makes no model call and needs no key. A new live run needs `MISTRAL_API_KEY` (environment or a local `.env`; never committed) and costs nothing on the free mode. Behind a proxy that replaces TLS certificates, start Python with the system certificate store (`truststore.inject_into_ssl()`).

## Limits

Synthetic rectangular houses, simple simulated tour noise, notes from phrase banks, illustrative prices, a weak free model that is not fully repeatable. It shows the method, not real accuracy.
