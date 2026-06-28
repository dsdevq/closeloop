.PHONY: verify test-unit test-e2e

# Full CI gate: Python unit tests + Playwright e2e tests.
# Delegates to scripts/verify.sh which auto-handles the ARM64 / no-root
# libXfixes workaround (no manual pre-steps needed).
verify:
	bash scripts/verify.sh

test-unit:
	pip install -q -r requirements.txt
	python -m pytest -q

# Standalone e2e target — requires root for 'playwright install --with-deps'.
# Use 'make verify' or 'bash scripts/verify.sh' for the auto-fallback path.
test-e2e:
	npm ci
	npx playwright install --with-deps chromium
	npx playwright test --reporter=list
