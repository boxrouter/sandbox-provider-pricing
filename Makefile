.PHONY: check format lint docs price-sheet cost-method release-assets update-fixtures release-digests new-provider
UV := $(abspath .venv/bin/uv)

new-provider:
	$(UV) run --locked python scripts/new_provider.py $(NAME)
	$(MAKE) update-fixtures docs

docs:
	$(UV) run --locked python scripts/docs.py

update-fixtures:
	$(UV) run --locked python scripts/update_fixtures.py

release-digests:
	$(UV) run --locked python scripts/release_digests.py

conformance:
	$(UV) run --locked python -m sandbox_provider_pricing.conformance --out src/sandbox_provider_pricing/conformance.json

price-sheet:
	mkdir -p dist
	$(UV) run --locked spp-price-sheet --out dist/price-sheet.json
	cp schemas/price-sheet.schema.json dist/price-sheet.schema.json

cost-method:
	mkdir -p dist
	$(UV) run --locked spp-cost-method --out dist/cost-method.json
	cp schemas/cost-method.schema.json dist/cost-method.schema.json

price-text:
	task_capture=$$(mktemp); trap 'rm -f "$$task_capture"' EXIT HUP INT TERM; \
		$(UV) run --locked python scripts/check_price_text.py > "$$task_capture"; \
		$(UV) run --locked sandbox-benchmark-verify rendered-text --capture "$$task_capture"

release-assets:
	rm -rf dist
	$(MAKE) price-sheet
	$(MAKE) cost-method
	$(UV) run --locked pytest tests/test_conformance.py -q
	$(UV) build --wheel --out-dir dist
	cp src/sandbox_provider_pricing/conformance.json dist/conformance.json
	cd dist && sha256sum *.whl *.json > SHA256SUMS

lint:
	$(UV) run --locked ruff format --check .
	$(UV) run --locked ruff check .
	$(UV) run --locked mypy
	$(UV) run --locked pyright
	$(UV) run --locked pylint src

check: lint price-text
	$(UV) run --locked pytest --cov --cov-report=term:skip-covered --cov-fail-under=92
	task_build_dir=$$(mktemp -d); trap 'rm -rf "$$task_build_dir"' EXIT HUP INT TERM; \
		$(UV) build --out-dir "$$task_build_dir"

format:
	$(UV) run --locked ruff format .
	$(UV) run --locked ruff check --fix .
	$(UV) run --locked ruff format .
