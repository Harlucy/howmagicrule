#!/usr/bin/env python3
"""Validate rule sources, generated providers, and INI references."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules"
OUTPUT = ROOT / "clash-classic"
STATIC_MANIFEST = ROOT / "config" / "static-yaml-outputs.txt"
EMPTY_MANIFEST = ROOT / "config" / "allowed-empty-yaml.txt"
EXCLUDED = {"app/GameDLCN.MANUAL.list", "MyDirect.SERVER.list", "A-ForcedDirect.SERVER.update.list"}
FORBIDDEN_RULES = {"app/WHSpecial.list", "cqgas.list"}
POLICY = json.loads((ROOT / "config/upstream-sync.json").read_text(encoding="utf-8"))
FORBIDDEN_MARKERS = POLICY["ini"]["forbidden_tokens"]


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

for forbidden in sorted(FORBIDDEN_RULES):
    if (RULES / forbidden).exists():
        report(f"{RULES.relative_to(ROOT) / forbidden}: forbidden provider rule is present")
        errors += 1

for relative in POLICY.get("force_empty", []):
    path = ROOT / relative
    if not path.exists() or any(line.strip() and not line.lstrip().startswith("#") for line in path.read_text(encoding="utf-8").splitlines()):
        report(f"{relative}: reserved local rule source must remain empty")
        errors += 1

valid_prefixes = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-REGEX",
    "IP-CIDR", "IP-CIDR6", "IP-ASN", "GEOIP", "GEOSITE", "MATCH", "PROCESS-NAME",
    "SRC-IP-CIDR", "DST-PORT", "SRC-PORT", "RULE-SET", "AND", "OR",
    "NOT", "URL-REGEX", "DOMAIN-WILDCARD", "PROCESS-NAME-WILDCARD",
    "PROCESS-PATH-REGEX",
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
        if line and line[3:].split(",", 1)[0] not in valid_prefixes:
            report(f"{relative}:{number}: unsupported generated rule type")
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
    for marker in FORBIDDEN_MARKERS:
        if marker.casefold() in content.casefold():
            report(f"{ini.name}: forbidden provider marker is present: {marker}")
            errors += 1
    apple_group = re.search(r"^custom_proxy_group=🍏 苹果服务`select`\[\]([^`\r\n]+)", content, re.MULTILINE)
    if apple_group and apple_group.group(1) != "🚄 本地直连":
        report(f"{ini.name}: Apple service default must be local direct")
        errors += 1
    for number, line in enumerate(content.splitlines(), 1):
        if not line.startswith("custom_proxy_group="):
            continue
        fields = line.split("`")
        if len(fields) < 3 or fields[2] in {"", "[]"}:
            continue
        selector = fields[2]
        if selector.startswith("("):
            try:
                re.compile(selector)
            except re.error as exc:
                report(f"{ini.name}:{number}: invalid node regex: {exc}")
                errors += 1
    for reference in sorted(set(ini_pattern.findall(content))):
        if not (ROOT / reference).exists():
            report(f"{ini.name}: referenced file does not exist: {reference}")
            errors += 1

if errors:
    print(f"Validation failed with {errors} error(s).")
    sys.exit(1)
print(f"Validation passed: {len(expected)} generated outputs and {len(list(ROOT.glob('*.ini')))} INI entries checked.")
