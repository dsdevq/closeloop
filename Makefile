.PHONY: verify test-unit test-e2e

# Full CI gate: Python unit tests + Playwright e2e tests.
#
# On ARM64 without root (libXfixes.so.3 missing), do the one-time workaround
# from AGENTS.md before running this target, then set
# PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 for the install step.
verify: test-unit test-e2e

test-unit:
	pip install -q -r requirements.txt
	python -m pytest -q

test-e2e:
	npm ci
	npx playwright install --with-deps chromium
	npx playwright test --reporter=list
