UV ?= uv

.PHONY: install check lint format-check typecheck test format package-smoke database-smoke

install:
	$(UV) sync --locked

check:
	$(UV) lock --check
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .
	$(UV) run --locked mypy
	$(UV) run --locked pytest

lint:
	$(UV) run --locked ruff check .

format-check:
	$(UV) run --locked ruff format --check .

typecheck:
	$(UV) run --locked mypy

test:
	$(UV) run --locked pytest

format:
	$(UV) run --locked ruff format .

package-smoke:
	$(UV) run --locked python scripts/package_smoke.py --uv "$(UV)"

# Explicit real PostgreSQL/PostgREST verification; no hosted credentials needed.
database-smoke:
	$(UV) run --locked python -m pytest integration -v
