PY = uv run python

all:
	$(PY) -m src.generate
	$(PY) -m src.plant
	$(PY) -m src.checks
	$(PY) -m src.agent
	$(PY) -m src.evaluate
	$(PY) -m src.export

test:
	uv run pytest -q

serve:
	$(PY) -m http.server 8000 -d site

.PHONY: all test serve
