.PHONY: help venv db-up db-down db-logs psql data phase1 phase2 phase3 phase4 app test clean-db reset
.DEFAULT_GOAL := help

PY := .venv/bin/python
PIP := .venv/bin/pip

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

venv:  ## Create .venv and install requirements
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "done — activate with: source .venv/bin/activate"

db-up:  ## Start Postgres 15 (docker compose)
	docker compose up -d
	@echo "waiting for postgres to accept connections..."
	@until docker compose exec -T db pg_isready -U $${PGUSER:-dhia} >/dev/null 2>&1; do sleep 1; done
	@echo "postgres ready on localhost:$${PGPORT:-5433}"

db-down:  ## Stop Postgres (data volume preserved)
	docker compose down

db-logs:  ## Tail Postgres logs
	docker compose logs -f db

psql:  ## Open a psql shell
	docker compose exec db psql -U $${PGUSER:-dhia} -d $${PGDATABASE:-dhia}

data:  ## Phase 0 — download and verify all sources
	$(PY) -m src.phase0_acquire

test:  ## Run the test suite
	.venv/bin/pytest -q

clean-db:  ## DESTROY the postgres volume (irreversible)
	docker compose down -v
	rm -rf pgdata

reset: clean-db db-up  ## Nuke and recreate an empty database
