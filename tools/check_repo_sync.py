"""P2 §6 #14 — repo sync verifier (standalone vs vendored).

The futures bot lives in two trees:

- the source-of-truth standalone repo at ``romaincortese-ui/futuresbot``
  (cloned to ``c:/Users/Rocot/Downloads/futuresbot``);
- the vendored copy under ``mexc-bot2/Futures-bot/`` that Railway deploys.

Drift between the two is a recurring incident class ("fixed in repo X,
deployed from repo Y"). This tool compares the ``futuresbot/`` package
between two trees byte-for-byte (excluding ``__pycache__`` / ``.pyc``)
and prints any differences. Exit code 0 == in sync; 1 == drift.

Usage
-----

    python tools/check_repo_sync.py \\
        --standalone c:/Users/Rocot/Downloads/futuresbot \\
        --vendored   c:/Users/Rocot/Downloads/mexc-bot2/Futures-bot

Run with ``--update-vendored`` to copy the standalone package over the
vendored one (destructive; backed by an explicit confirmation prompt
unless ``--yes`` is passed).
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path


PACKAGE = "futuresbot"
SKIP_NAMES = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_NAMES for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        if path.is_file():
            yield path.relative_to(root)


def diff_packages(standalone: Path, vendored: Path) -> tuple[list[Path], list[Path], list[Path]]:
    """Return (only_in_standalone, only_in_vendored, modified) relative paths."""

    a = standalone / PACKAGE
    b = vendored / PACKAGE
    if not a.is_dir():
        raise SystemExit(f"standalone package not found: {a}")
    if not b.is_dir():
        raise SystemExit(f"vendored package not found: {b}")
    a_files = set(_iter_files(a))
    b_files = set(_iter_files(b))
    only_a = sorted(a_files - b_files)
    only_b = sorted(b_files - a_files)
    common = sorted(a_files & b_files)
    modified = [
        rel for rel in common
        if not filecmp.cmp(a / rel, b / rel, shallow=False)
    ]
    return only_a, only_b, modified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--standalone", type=Path, required=True, help="Path to the standalone repo root")
    parser.add_argument("--vendored", type=Path, required=True, help="Path to the vendored deploy copy root")
    parser.add_argument("--update-vendored", action="store_true",
                        help="Mirror the standalone package into the vendored tree (destructive)")
    parser.add_argument("--yes", action="store_true", help="Skip the destructive-action prompt")
    args = parser.parse_args()

    only_a, only_b, modified = diff_packages(args.standalone, args.vendored)
    if not (only_a or only_b or modified):
        print(f"[REPO_SYNC] OK — {PACKAGE}/ is identical between standalone and vendored.")
        return 0

    print(f"[REPO_SYNC] DRIFT detected in {PACKAGE}/:")
    if only_a:
        print(f"  only in standalone ({len(only_a)}):")
        for p in only_a:
            print(f"    + {p}")
    if only_b:
        print(f"  only in vendored ({len(only_b)}):")
        for p in only_b:
            print(f"    - {p}")
    if modified:
        print(f"  modified ({len(modified)}):")
        for p in modified:
            print(f"    ~ {p}")

    if args.update_vendored:
        if not args.yes:
            ans = input(f"\nMirror standalone -> vendored? This will overwrite {args.vendored / PACKAGE}. [y/N] ")
            if ans.strip().lower() not in {"y", "yes"}:
                print("Aborted.")
                return 1
        dest = args.vendored / PACKAGE
        src = args.standalone / PACKAGE
        # Remove deleted files first (only_a contains files only-in-source;
        # only_b contains files we should drop from vendored).
        for rel in only_b:
            (dest / rel).unlink(missing_ok=True)
        # Copy added + modified.
        for rel in only_a + modified:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, target)
        print(f"[REPO_SYNC] vendored package mirrored from {src}.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
