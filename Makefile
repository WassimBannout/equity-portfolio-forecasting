UV ?= uv
CADDY ?= caddy

.PHONY: install check lint format-check typecheck test format package-smoke database-smoke deployment-smoke

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

deployment-smoke:
	$(UV) run --locked python -m pytest tests/test_operations.py tests/test_deployment.py -v
	$(UV) run --locked python scripts/deployment_checks.py --caddy "$(CADDY)"
	go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 -color=false
