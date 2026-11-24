# PlanTrust: notes for Claude Code

Small demo for a job application (DocuSketch, Senior Software Engineer, AI Agents). Synthetic data only.

- **Current task:** v2, specified in `docs/V2_BRIEF.md`. Work one numbered step at a time (section 8, steps 1 to 9), then stop and summarise. Plain-language version for the author: `docs/V2_EXPLAINED.md`.
- **Keep it simple.** One agent (LangChain v1 `create_agent` + built-in middleware), plain Python, one static page. No new frameworks, servers or databases.
- **Model:** Mistral `voxtral-small-latest`, free mode, key `MISTRAL_API_KEY` in `.env` (never commit it). Config lives in `src/llm.py`.
- **Numbers:** every number on the page is written by the scripts (`src/export.py`). Never type results by hand.
- **Tests:** `uv run pytest -q`, offline, with the scripted fake model. Never call the real model in tests.
- **Run:** `uv run python run_all.py` (or `make all`); page: `uv run python -m http.server 8000 -d site`. The author is on Windows; `make` may be missing.
- **Honesty:** if the agent does not beat a baseline, say so on the page.
- **Git:** work on the `v2` branch. Do not push to `main` until all steps are done: every push to `main` redeploys the live page (`.github/workflows/pages.yml`).
