#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Idempotent SPDX header sweep for the BountyStrike monorepo.

Walk ONLY the six licensed roots; apply the correct SPDX-License-Identifier
comment to each eligible source file.  Re-running is safe: files that already
carry any SPDX-License-Identifier line are left untouched.

Usage:
    uv run python scripts/add_spdx_headers.py          # apply (writes files)
    uv run python scripts/add_spdx_headers.py --check  # report missing, exit 1
    uv run python scripts/add_spdx_headers.py --root /path/to/repo
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# SPDX identifier map — authoritative per LICENSES.md
# ---------------------------------------------------------------------------

# Six licensed roots (relative to repo root) → SPDX identifier.
# ONLY these paths are ever walked.  Any file outside all six is skipped.
ROOT_SPDX: list[tuple[str, str]] = [
    ("packages/core", "Apache-2.0"),
    ("packages/enterprise", "LicenseRef-BountyStrike-Proprietary"),
    ("packages/community", "AGPL-3.0-or-later"),
    ("control-plane", "AGPL-3.0-or-later"),
    ("mcp", "AGPL-3.0-or-later"),
    ("scripts", "AGPL-3.0-or-later"),
]

# Comment prefix per file extension.
EXT_PREFIX: dict[str, str] = {
    ".py": "#",
    ".sh": "#",
    ".ts": "//",
    ".tsx": "//",
    ".js": "//",
    ".sql": "--",
}

# ---------------------------------------------------------------------------
# Deny skip-list (second gate; belt-and-suspenders even inside a root)
# ---------------------------------------------------------------------------
SKIP_PATH_FRAGMENTS: tuple[str, ...] = (
    "/__pycache__/",
    "/.pyc",
    "/.turbo/",
    "/node_modules/",
    "/migrations/",
    "/fixtures/",
    "/testdata/",
    "/.git/",
    "/.venv/",
    "/site-packages/",
    "/dist/",
    "/build/",
    ".d.ts",
    ".min.",
    "/.claude/",
    "/.gemini/",
    "/.github/",
)

SKIP_FILENAMES: tuple[str, ...] = (
    "pnpm-lock.yaml",
    "uv.lock",
)

SKIP_SUFFIXES: tuple[str, ...] = (
    ".lock",
    ".json",
    ".toml",
    ".md",
    ".txt",
    ".env",
)

SPDX_MARKER = "SPDX-License-Identifier:"


def find_repo_root(start: Path) -> Path:
    """Return the git repo root, falling back to *start*."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return Path(out.strip())
    except subprocess.CalledProcessError:
        return start


def spdx_comment(prefix: str, spdx_id: str) -> str:
    return f"{prefix} {SPDX_MARKER} {spdx_id}"


def should_skip(rel: str) -> bool:
    """Return True if the relative path (using forward slashes) must be skipped."""
    # Normalise to forward slashes for fragment matching
    norm = "/" + rel.replace("\\", "/")

    # Check .lock suffix explicitly (catches pnpm-lock.yaml etc.)
    fname = os.path.basename(norm)
    if fname in SKIP_FILENAMES:
        return True

    for suffix in SKIP_SUFFIXES:
        if norm.endswith(suffix):
            return True

    # Env files: .env, .env.example, .env.local …
    if "/.env" in norm:
        return True

    return any(frag in norm for frag in SKIP_PATH_FRAGMENTS)


def insert_spdx(lines: list[str], comment: str) -> list[str]:
    """Return *lines* with *comment* inserted at the correct position.

    Rules (audit AC-2a):
    - If line 0 is a shebang (#!), insert AFTER it.
    - If line 0 or 1 is a PEP-263 coding cookie, insert AFTER it.
    - Otherwise insert at position 0.
    - Add one blank-line separator after the SPDX line when the next
      existing line is non-blank.
    """
    insert_idx = 0

    # Check shebang
    if lines and lines[0].startswith("#!"):
        insert_idx = 1

    # Check PEP-263 coding cookie in first two original lines
    for i in range(min(2, len(lines))):
        line = lines[i].strip()
        if line.startswith(("#", "//")) and ("coding:" in line or "coding=" in line):
            insert_idx = max(insert_idx, i + 1)
            break

    # Determine whether to add a blank separator
    spdx_line = comment + "\n"
    after_idx = insert_idx  # index into *lines* of the line that will follow the SPDX

    if after_idx < len(lines) and lines[after_idx].strip():
        # Next line is non-blank: add separator
        return lines[:insert_idx] + [spdx_line, "\n"] + lines[insert_idx:]
    else:
        return lines[:insert_idx] + [spdx_line] + lines[insert_idx:]


def process_file(
    path: Path,
    spdx_id: str,
    *,
    check: bool,
) -> str:
    """Process a single file.

    Returns one of: "updated", "already_has_header", "skipped_ext", "check_missing".
    """
    suffix = path.suffix.lower()
    prefix = EXT_PREFIX.get(suffix)
    if prefix is None:
        return "skipped_ext"

    try:
        content = path.read_bytes()
    except OSError:
        return "skipped_ext"

    # Decode; skip binary files
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return "skipped_ext"

    lines = text.splitlines(keepends=True)

    # Idempotency: skip if any of the first 10 lines already has SPDX marker
    for line in lines[:10]:
        if SPDX_MARKER in line:
            return "already_has_header"

    comment = spdx_comment(prefix, spdx_id)

    if check:
        return "check_missing"

    new_lines = insert_spdx(lines, comment)
    new_text = "".join(new_lines)

    # Atomic write
    tmp = path.with_suffix(path.suffix + ".spdx_tmp")
    try:
        tmp.write_bytes(new_text.encode("utf-8"))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()

    return "updated"


def sweep(repo_root: Path, *, check: bool) -> int:  # noqa: PLR0912
    """Run the sweep; return exit code."""
    updated = 0
    already = 0
    skipped_ext = 0
    skipped_list = 0
    check_missing: list[str] = []

    for root_rel, spdx_id in ROOT_SPDX:
        root_abs = repo_root / root_rel
        if not root_abs.exists():
            continue

        for dirpath, dirnames, filenames in os.walk(root_abs):
            # Prune directory traversal for speed (deny-list fragments)
            dirnames[:] = [
                d
                for d in dirnames
                if not should_skip(
                    "/" + str(Path(dirpath, d).relative_to(repo_root)).replace("\\", "/") + "/"
                )
            ]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                rel = str(fpath.relative_to(repo_root))

                if should_skip(rel):
                    skipped_list += 1
                    continue

                # Only process known source extensions
                if fpath.suffix.lower() not in EXT_PREFIX:
                    skipped_list += 1
                    continue

                result = process_file(fpath, spdx_id, check=check)

                if result == "updated":
                    print(f"  stamped: {rel}")
                    updated += 1
                elif result == "already_has_header":
                    already += 1
                elif result == "skipped_ext":
                    skipped_ext += 1
                elif result == "check_missing":
                    check_missing.append(rel)

    if check:
        for rel in sorted(check_missing):
            print(f"  MISSING SPDX: {rel}")
        total_missing = len(check_missing)
        print(
            f"\n{total_missing} files missing header, "
            f"{already} files already have header, "
            f"{skipped_list + skipped_ext} files skipped"
        )
        if total_missing:
            return 1
        return 0

    print(
        f"\n{updated} files updated, "
        f"{already} files skipped (already have header), "
        f"{skipped_ext} files skipped (not eligible), "
        f"{skipped_list} files skipped (skip-list)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent SPDX header sweep for BountyStrike monorepo"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report missing headers and exit 1 if any found (do not write files)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detected via git rev-parse)",
    )
    args = parser.parse_args()

    repo_root = args.root if args.root else find_repo_root(Path.cwd())
    repo_root = repo_root.resolve()

    print(f"Repo root: {repo_root}")
    print(f"Mode: {'CHECK (dry-run)' if args.check else 'APPLY'}")
    print()

    try:
        return sweep(repo_root, check=args.check)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
