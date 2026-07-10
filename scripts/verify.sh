#!/usr/bin/env bash
# Full CI gate: Python unit tests then Playwright e2e tests.
#
# On ARM64 environments without root access (libXfixes.so.3 unavailable via
# apt), the Chromium install step falls back to a user-space library workaround
# automatically — no manual steps required.
#
# Usage:
#   bash scripts/verify.sh
set -euo pipefail

# ── Step 1: Python unit tests ─────────────────────────────────────────────────
pip install -q -r requirements.txt
python -m pytest -q

# ── Step 2: Playwright e2e tests ──────────────────────────────────────────────
npm ci

# Install Playwright Chromium together with system host dependencies.
# If the install fails (typical on ARM64 containers without root because
# "su: Authentication failure"), fall back to:
#   1. Extracting libXfixes.so.3 from the Debian package without root.
#   2. Installing Chromium with host-requirement validation skipped.
# playwright.config.ts already prepends ~/lib to LD_LIBRARY_PATH.
#
# NOTE: npx playwright install --with-deps exits 0 even when the privileged
# dep-install step fails (ARM64 no-root: "su: Authentication failure").
# We capture the output and check for that signal independently of exit code.
set +e
_pw_out=$(npx playwright install --with-deps chromium 2>&1)
_pw_ec=$?
set -e
printf '%s\n' "$_pw_out"
if [ "$_pw_ec" -ne 0 ] || printf '%s' "$_pw_out" | grep -q "Authentication failure"; then
    echo "[verify.sh] --with-deps install failed; applying ARM64 no-root workaround..." >&2
    if [ ! -f "${HOME}/lib/libXfixes.so.3" ]; then
        curl -fsSL "http://deb.debian.org/debian/pool/main/libx/libxfixes/libxfixes3_6.0.0-2+b5_arm64.deb" \
             -o /tmp/lxf.deb
        dpkg-deb -x /tmp/lxf.deb /tmp/lxf
        mkdir -p "${HOME}/lib"
        cp /tmp/lxf/usr/lib/*/libXfixes.so.3* "${HOME}/lib/"
    fi
    PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright install chromium
fi

npx playwright test --reporter=list
