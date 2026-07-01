#!/usr/bin/env python3
"""Docs lint — the mechanized rot-prevention gate.

Runs three checks against every markdown file under docs/:

  1. FRONTMATTER — every page must carry the contract fields
     (title, status, owner, last_reviewed, tags). Missing or malformed
     frontmatter FAILS the PR.

  2. LINKS — every internal markdown link resolves. Dead links FAIL.

  3. ROT AGE — every `status: stable` page whose `last_reviewed` is
     older than the rot threshold (default 90 days) WARNS by default;
     set --strict to promote to failure. Rot doesn't fail routine PRs
     but shows up in CI so it can't be ignored forever.

Also runs one repo-wide invariant:

  4. ADR CROSS-REFS — every code reference of the form `ADR-NNNN`
     (in comments) must point at an ADR file that exists.

Exit code 0 = green, 1 = errors, 2 = only warnings (when --strict is off).

Usage:

    python3 scripts/docs_lint.py            # normal PR gate (warns on rot)
    python3 scripts/docs_lint.py --strict   # scheduled audit (fails on rot)
    python3 scripts/docs_lint.py --json     # machine output for CI
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Rot threshold — a stable page whose last_reviewed is older than this many
# days is due for a re-read.
ROT_DAYS = 90

# Required frontmatter keys for every page under docs/.
REQUIRED_KEYS = ("title", "status", "owner", "tags")
# ADRs use `date` (immutable acceptance date) instead of `last_reviewed`
# because they're immutable-once-accepted (see docs/architecture/decisions/README.md).
# Every other page needs `last_reviewed` for the rot-audit.
REQUIRED_KEYS_ADR = ("title", "status", "owner", "date", "tags")
VALID_STATUS = {"stable", "draft", "proposed", "accepted", "superseded", "deprecated", "under-review", "rejected", "withdrawn", "active", "mitigated", "post-mortem"}

# ADR filenames MUST match this pattern.
ADR_FILE_RE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")

# References to ADRs from code / docs, e.g. "see ADR-0006".
ADR_REF_RE = re.compile(r"\bADR-(\d{4})\b")

# Markdown link regex — captures `[label](url)` with a relative or absolute url.
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


@dataclass
class Finding:
    level: str  # "error" | "warn"
    file: str
    line: int | None
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "file": self.file, "line": self.line, "code": self.code, "message": self.message}


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warn"]

    def add(self, level: str, file: Path, line: int | None, code: str, message: str) -> None:
        self.findings.append(Finding(level, str(file.relative_to(REPO_ROOT)), line, code, message))


def _read_frontmatter(text: str) -> tuple[dict, int] | None:
    """Return (parsed_frontmatter, body_start_line) or None if no frontmatter.

    Minimal YAML-ish parser — no external dependency. Supports key: value and
    key: [comma, separated, list]. Good enough for our contract; the CI can
    call a real YAML parser later if needed.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None
    fm = {}
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return fm, i + 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # tags: [a, b, c] → list
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            value = [item.strip().strip('"').strip("'") for item in inner.split(",") if item.strip()]
        else:
            value = value.strip('"').strip("'")
            if value == "null":
                value = None
        fm[key] = value
    return fm, len(lines) + 1  # frontmatter never closed — will error later


def _is_adr(path: Path) -> bool:
    """ADR files live under docs/architecture/decisions/ and match NNNN-slug.md."""
    return (
        "decisions" in path.parts
        and "architecture" in path.parts
        and bool(ADR_FILE_RE.match(path.name))
    )


def check_frontmatter(path: Path, text: str, result: Result) -> dict | None:
    fm_and_start = _read_frontmatter(text)
    if fm_and_start is None:
        result.add("error", path, 1, "no-frontmatter", "missing YAML frontmatter block at file start")
        return None
    fm, _ = fm_and_start
    required = REQUIRED_KEYS_ADR if _is_adr(path) else REQUIRED_KEYS + ("last_reviewed",)
    for key in required:
        if key not in fm:
            result.add("error", path, 1, "missing-key", f"frontmatter missing required key: {key}")
    status = fm.get("status")
    if status and status not in VALID_STATUS:
        result.add("error", path, 1, "bad-status", f"status={status!r} not in {sorted(VALID_STATUS)}")
    owner = fm.get("owner")
    if owner and not (isinstance(owner, str) and owner.startswith("@")):
        result.add("error", path, 1, "bad-owner", f"owner must be a @github-handle, got {owner!r}")
    for date_field in ("last_reviewed", "date"):
        value = fm.get(date_field)
        if value:
            try:
                datetime.strptime(str(value), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                result.add("error", path, 1, "bad-date", f"{date_field}={value!r} not a YYYY-MM-DD date")
    return fm


def check_rot(path: Path, fm: dict, result: Result, today: date) -> None:
    if fm.get("status") != "stable":
        return  # rot audit only fires on stable pages
    last = fm.get("last_reviewed")
    if not last:
        return
    try:
        last_date = datetime.strptime(str(last), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return  # already errored in check_frontmatter
    age = (today - last_date).days
    if age > ROT_DAYS:
        result.add(
            "warn", path, 1, "rot",
            f"page is {age} days past last_reviewed ({last_date}); re-read and bump the date, or mark superseded/deprecated",
        )


def check_links(path: Path, text: str, result: Result) -> None:
    # Track whether we're inside a fenced code block — links there are examples,
    # not real references. Skip them.
    in_fence = False
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in MD_LINK_RE.finditer(line):
            url = match.group(2).strip()
            # Skip anchors, external URLs, and mailto
            if url.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # Strip anchor
            url_no_anchor = url.split("#", 1)[0]
            if not url_no_anchor:
                continue
            target = (path.parent / url_no_anchor).resolve()
            if not target.exists():
                result.add("error", path, i, "dead-link", f"link target does not exist: {url}")


def check_adr_naming(result: Result) -> None:
    """ADR filenames must match NNNN-slug.md — the sequence is the audit trail."""
    adr_dir = DOCS_DIR / "architecture" / "decisions"
    if not adr_dir.exists():
        return
    for f in adr_dir.glob("*.md"):
        if f.name in ("INDEX.md", "README.md"):
            continue
        if not ADR_FILE_RE.match(f.name):
            result.add("error", f, 1, "bad-adr-name", f"ADR filename must match NNNN-slug.md — got {f.name!r}")


def check_adr_crossrefs(result: Result) -> None:
    """Every ADR-NNNN reference in code or docs must point at a real ADR."""
    adr_dir = DOCS_DIR / "architecture" / "decisions"
    existing = set()
    if adr_dir.exists():
        for f in adr_dir.glob("*.md"):
            match = ADR_FILE_RE.match(f.name)
            if match:
                existing.add(match.group(1))

    scan_dirs = [REPO_ROOT / "app", REPO_ROOT / "frontend" / "src", REPO_ROOT / "tests", DOCS_DIR, REPO_ROOT / "AGENTS.md"]
    for target in scan_dirs:
        if target.is_file():
            files: Iterable[Path] = [target]
        elif target.is_dir():
            files = [p for p in target.rglob("*") if p.is_file() and p.suffix in (".py", ".ts", ".tsx", ".md", ".yml", ".yaml", ".sh")]
        else:
            continue
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                for match in ADR_REF_RE.finditer(line):
                    n = match.group(1)
                    if n not in existing:
                        result.add("error", f, i, "unknown-adr", f"reference to ADR-{n} but no docs/architecture/decisions/{n}-*.md exists")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="promote rot warnings to errors")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    result = Result()
    today = date.today()

    if not DOCS_DIR.exists():
        print("docs/ does not exist — nothing to lint", file=sys.stderr)
        return 0

    for path in sorted(DOCS_DIR.rglob("*.md")):
        # Templates are exempt from frontmatter contract (their frontmatter is
        # a placeholder for callers to fill in).
        text = path.read_text(encoding="utf-8", errors="replace")
        if "_templates" in path.parts:
            check_links(path, text, result)
            continue
        fm = check_frontmatter(path, text, result)
        if fm:
            check_rot(path, fm, result, today)
        check_links(path, text, result)

    # Repo-wide invariants
    check_adr_naming(result)
    check_adr_crossrefs(result)

    if args.json:
        print(json.dumps({"findings": [f.to_dict() for f in result.findings]}, indent=2))
    else:
        for f in result.findings:
            marker = "\033[31mERROR\033[0m" if f.level == "error" else "\033[33mwarn \033[0m"
            loc = f"{f.file}:{f.line}" if f.line else f.file
            print(f"{marker} {loc} [{f.code}] {f.message}")

        n_err = len(result.errors)
        n_warn = len(result.warns)
        print(f"\ndocs lint: {n_err} error(s), {n_warn} warning(s)")

    if result.errors:
        return 1
    if args.strict and result.warns:
        return 1
    if result.warns:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
