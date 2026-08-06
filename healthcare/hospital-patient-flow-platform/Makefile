# Convenience targets. Everything here is a thin wrapper over a command
# documented in the README — nothing hides behind make.

.PHONY: help install sample load api web test typecheck build docs clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install backend and frontend dependencies
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

sample:  ## Generate 180 days of synthetic hospital data
	python scripts/generate_sample_data.py --days 180 --out data/samples

load:  ## Create the schema and import the sample data
	python scripts/load_demo.py --data data/samples

api:  ## Run the API with reload
	cd backend && uvicorn app.main:app --reload --port 8000

web:  ## Run the dashboards
	cd frontend && npm run dev

test:  ## Run the backend test suite
	python -m pytest backend/tests -q

typecheck:  ## Typecheck the frontend
	cd frontend && npx tsc --noEmit

build:  ## Production build of the frontend
	cd frontend && npm run build

docs:  ## Regenerate the data dictionary from the code
	python scripts/build_data_dictionary.py

templates:  ## Build the Excel import templates
	python scripts/build_excel_templates.py --out data/templates

clean:  ## Remove generated artefacts
	rm -rf hpf.db backend/hpf.db var backend/var data/samples data/templates
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
