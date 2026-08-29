#!/usr/bin/env python3
"""Validate rule sources, generated providers, and INI references."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules"
OUTPUT = ROOT / "clash-classic"
STATIC_MANIFEST = ROOT / "config" / "static-yaml-outputs.txt"
EMPTY_MANIFEST = ROOT / "config" / "allowed-empty-yaml.txt"
EXCLUDED = {"app/GameDLCN.MANUAL.list", "MyDirect.SERVER.list"}


def read_manifest(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def report(message: str) -> None:
    print(f"::error::{message}")


errors = 0
static_outputs = read_manifest(STATIC_MANIFEST)
allowed_empty = read_manifest(EMPTY_MANIFEST)
expected: set[str] = set()

valid_prefixes = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-REGEX",
    "IP-CIDR", "IP-CIDR6", "IP-ASN", "GEOIP", "GEOSITE", "MATCH", "PROCESS-NAME",
    "SRC-IP-CIDR", "DST-PORT", "SRC-PORT", "RULE-SET", "AND", "OR",
    "NOT", "URL-REGEX", "DOMAIN-WILDCARD", "PROCESS-NAME-WILDCARD",
}

for source in RULES.rglob("*.list"):
    relative = source.relative_to(RULES).as_posix()
    if relative in EXCLUDED:
        continue
    output = (OUTPUT / Path(relative)).with_suffix(".yaml")
    expected.add(output.relative_to(ROOT).as_posix())
    for number, raw in enumerate(source.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prefix = line.split(",", 1)[0].strip()
        if prefix not in valid_prefixes:
            report(f"{source.relative_to(ROOT)}:{number}: unknown rule type {prefix!r}")
            errors += 1
            break

actual = {path.relative_to(ROOT).as_posix() for path in OUTPUT.rglob("*.yaml")}
for relative in sorted(actual):
    path = ROOT / relative
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    text = "\n".join(lines)
    if not lines or lines[0] != "payload:":
        report(f"{relative}: missing payload header")
        errors += 1
    if text.rstrip() == "payload:" and relative not in allowed_empty:
        report(f"{relative}: empty payload is not allowlisted")
        errors += 1
    for number, line in enumerate(lines[1:], 2):
        if line and not line.startswith(" - "):
            report(f"{relative}:{number}: invalid payload entry")
            errors += 1
            break

for relative in sorted(expected - actual):
    report(f"missing generated output: {relative}")
    errors += 1
for relative in sorted(actual - expected - static_outputs):
    report(f"unregistered generated output: {relative}")
    errors += 1

ini_pattern = re.compile(r"clash-classic/[A-Za-z0-9_./-]+\.yaml")
for ini in ROOT.glob("*.ini"):
    content = ini.read_text(encoding="utf-8", errors="replace")
    for reference in sorted(set(ini_pattern.findall(content))):
        if not (ROOT / reference).exists():
            report(f"{ini.name}: referenced file does not exist: {reference}")
            errors += 1

if errors:
    print(f"Validation failed with {errors} error(s).")
    sys.exit(1)
print(f"Validation passed: {len(expected)} generated outputs and {len(list(ROOT.glob('*.ini')))} INI entries checked.")
