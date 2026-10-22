#!/usr/bin/env python3
"""Remove exact duplicate rules without changing their first-match order."""
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules"


def normalize(path: Path, write: bool) -> int:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    seen: set[str] = set()
    output: list[str] = []
    removed = 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            output.append(raw)
            continue
        if line in seen:
            removed += 1
            continue
        seen.add(line)
        output.append(raw.rstrip())
    if removed and write:
        while output and not output[-1].strip():
            output.pop()
        path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report duplicates without changing files")
    args = parser.parse_args()
    total = 0
    files = 0
    for path in sorted(RULES.rglob("*.list")):
        if path.name.endswith(".MANUAL.list"):
            continue
        removed = normalize(path, write=not args.check)
        if removed:
            files += 1
            total += removed
            print(f"{path.relative_to(ROOT)}: removed {removed} duplicate rule(s)")
    mode = "would remove" if args.check else "removed"
    print(f"{mode} {total} duplicate rule(s) in {files} file(s).")
    return 1 if args.check and total else 0


if __name__ == "__main__":
    raise SystemExit(main())
