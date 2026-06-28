"""
Drive the Playwright e2e suite from within pytest so the done-gate verify_cmd
(`python -m pytest -q`) captures full Playwright reporter output in its tail.

Setup steps mirror scripts/verify.sh:
  1. npm ci — installs node_modules if absent (requires package-lock.json).
  2. Playwright browser install — tries --with-deps; falls back to the ARM64
     no-root libXfixes workaround documented in AGENTS.md when that fails.
  3. npx playwright test --reporter=list — streams directly to stdout/stderr so
     the gate log includes every test name, pass/fail marker, and timing line.
"""

import os
import pathlib
import shutil
import subprocess

_REPO = pathlib.Path(__file__).parent.parent


def _npm_ci_if_needed() -> None:
    if not (_REPO / "node_modules" / ".bin" / "playwright").exists():
        subprocess.run(["npm", "ci"], cwd=_REPO, check=True)


def _install_playwright_browser() -> None:
    """Install Chromium; fall back to the ARM64 no-root workaround on failure."""
    home = pathlib.Path.home()
    xfixes = home / "lib" / "libXfixes.so.3"

    if xfixes.exists():
        # Workaround already applied from a prior run — just ensure browser binary.
        subprocess.run(
            ["npx", "playwright", "install", "chromium"],
            cwd=_REPO,
            env={**os.environ, "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS": "1"},
            check=True,
        )
        return

    # Try the standard path first (works when we have root / full system deps).
    result = subprocess.run(
        ["npx", "playwright", "install", "--with-deps", "chromium"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return

    # ARM64 no-root fallback: extract libXfixes.so.3 from the Debian package
    # without needing apt or sudo.  playwright.config.ts prepends ~/lib to
    # LD_LIBRARY_PATH so Chromium can find the shared library at runtime.
    lxf_deb = "/tmp/lxf.deb"
    lxf_dir = "/tmp/lxf"
    subprocess.run(
        [
            "curl", "-fsSL",
            (
                "http://deb.debian.org/debian/pool/main/libx/libxfixes"
                "/libxfixes3_6.0.0-2+b5_arm64.deb"
            ),
            "-o", lxf_deb,
        ],
        check=True,
    )
    subprocess.run(["dpkg-deb", "-x", lxf_deb, lxf_dir], check=True)
    lib_dir = home / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    for lib_file in pathlib.Path(lxf_dir).rglob("libXfixes.so.3*"):
        shutil.copy2(lib_file, lib_dir / lib_file.name)

    subprocess.run(
        ["npx", "playwright", "install", "chromium"],
        cwd=_REPO,
        env={**os.environ, "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS": "1"},
        check=True,
    )


def test_playwright_suite():
    _npm_ci_if_needed()
    _install_playwright_browser()

    result = subprocess.run(
        ["npx", "playwright", "test", "--reporter=list"],
        cwd=_REPO,
        capture_output=False,
        text=True,
    )
    assert result.returncode == 0, f"Playwright suite exited {result.returncode}"
