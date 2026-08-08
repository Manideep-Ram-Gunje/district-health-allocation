.PHONY: help venv db-up db-down db-logs db-create psql data reconcile load analytics allocate sensitivity geo snapshot app pipeline test clean-db reset
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

db-create:  ## Create the dhia role and database on a NATIVE postgres (needs sudo)
	sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$${PGUSER:-dhia}'" \
	  | grep -q 1 || sudo -u postgres psql -c \
	  "CREATE ROLE $${PGUSER:-dhia} LOGIN PASSWORD '$${PGPASSWORD:-dhia}';"
	sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$${PGDATABASE:-dhia}'" \
	  | grep -q 1 || sudo -u postgres psql -c \
	  "CREATE DATABASE $${PGDATABASE:-dhia} OWNER $${PGUSER:-dhia};"
	@echo "role and database ready"

data:  ## Phase 0 — download and verify all sources
	$(PY) -m src.phase0_acquire

reconcile:  ## Phase 1a — build the district crosswalk
	$(PY) -m src.phase1_reconcile

load:  ## Phase 1b — build schema and load the database
	$(PY) -m src.phase1_load

analytics:  ## Phase 2 — build the Need Index and analytics views
	$(PY) -m src.phase2_need_index

allocate:  ## Phase 3 — solve the ILP and compare against baselines
	$(PY) -m src.phase3_allocate

sensitivity:  ## Phase 4 — Dirichlet weight sensitivity
	$(PY) -m src.phase4_sensitivity

geo:  ## Phase 5a — match map polygons to districts
	$(PY) -m src.phase5_geo

snapshot:  ## Export a file-based snapshot so the app runs without Postgres
	$(PY) -m src.snapshot

app:  ## Phase 5b — launch the Streamlit app
	.venv/bin/streamlit run app/streamlit_app.py

pipeline: data reconcile load analytics allocate sensitivity geo snapshot  ## Run every phase end to end

test:  ## Run the test suite
	$(PY) -m pytest

clean-db:  ## DESTROY the postgres volume (irreversible)
	docker compose down -v
	rm -rf pgdata

reset: clean-db db-up  ## Nuke and recreate an empty database
