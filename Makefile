PY = uv run python

all:
	$(PY) run_all.py

test:
	uv run pytest -q

serve:
	$(PY) -m http.server 8000 -d site

.PHONY: all test serve
