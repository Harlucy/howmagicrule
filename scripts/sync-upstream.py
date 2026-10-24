#!/usr/bin/env python3
"""Synchronize selected files from the upstream rule repository.

The sync is intentionally policy-driven: only configured paths are copied,
manual and local-network files are preserved, and new rule providers are not
introduced unless they already exist locally.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "upstream-sync.json"


def run_git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if not check and result.returncode != 0:
        return ""
    if check and result.stderr.strip():
        print(result.stderr.strip())
    return result.stdout.strip()


def git_remote_exists(name: str) -> bool:
    return bool(run_git("remote", "get-url", name, check=False))


def fetch_commit(upstream: dict[str, str], no_fetch: bool) -> str:
    remote = upstream["remote"]
    if not git_remote_exists(remote):
        run_git("remote", "add", remote, upstream["url"])
    if not no_fetch:
        print(f"Fetching {remote}/{upstream['ref']}...")
        run_git("fetch", "--no-tags", remote, upstream["ref"])
    if no_fetch:
        commit = run_git("rev-parse", f"refs/remotes/{remote}/{upstream['ref']}", check=False)
        if not commit:
            raise SystemExit(
                f"No local tracking ref for {remote}/{upstream['ref']}; "
                "use a normal fetch or pass --commit with an exact revision."
            )
    else:
        commit = run_git("rev-parse", "FETCH_HEAD")
    print(f"Using upstream commit {commit}")
    return commit


def matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def upstream_files(commit: str) -> list[str]:
    output = run_git("ls-tree", "-r", "--name-only", commit)
    return [line for line in output.splitlines() if line]


def read_blob(commit: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
    )
    return result.stdout


def sanitize_ini(text: str, ini_config: dict[str, object]) -> str:
    repository = str(ini_config["local_repository"])
    tokens = [str(token) for token in ini_config["forbidden_tokens"]]
    preferred_defaults = {
        str(name): str(value)
        for name, value in dict(ini_config.get("preferred_defaults", {})).items()
    }
    token_pattern = "|".join(re.escape(token) for token in tokens)
    output: list[str] = []
    for raw in text.splitlines():
        line = raw.replace(
            "https://raw.githubusercontent.com/fortressme/ownmagicrule",
            f"https://raw.githubusercontent.com/{repository}",
        )
        # Drop rulesets and proxy groups dedicated to excluded providers.
        if line.startswith("ruleset=") and re.search(token_pattern, line, re.IGNORECASE):
            continue
        if line.startswith("custom_proxy_group="):
            group_name = line.split("`", 1)[0].split("=", 1)[1]
            if re.search(token_pattern, group_name, re.IGNORECASE):
                continue
            if group_name in preferred_defaults and "`select`" in line:
                prefix, suffix = line.split("`select`", 1)
                preferred = preferred_defaults[group_name]
                options = [item for item in re.split(r"`?\[\]", suffix) if item]
                options = [preferred] + [item for item in options if item != preferred]
                line = prefix + "`select`[]" + "`[]".join(options)
        # Remove excluded provider names from negative-match alternatives while
        # retaining the surrounding regular expression.
        # Only remove complete alternatives. In particular, \| is a literal
        # pipe in a node name, not an alternative separator to clean up.
        previous = None
        while previous != line:
            previous = line
            line = re.sub(rf"(?<!\\)\|(?:{token_pattern})(?=\||\))", "", line, flags=re.IGNORECASE)
            line = re.sub(rf"(?<=[(:])(?:{token_pattern})\|", "", line, flags=re.IGNORECASE)
        # If every alternative was excluded, the remaining single token must
        # never match. An impossible pattern also keeps negative lookaheads
        # valid without excluding all ordinary nodes.
        line = re.sub(rf"(?<=[(:])(?:{token_pattern})(?=\))", "(?!)", line, flags=re.IGNORECASE)
        if line.strip():
            output.append(line)
    return "\n".join(output) + "\n"


def read_path(commit: str, relative: str, *, existing_only: bool) -> tuple[Path, str] | None:
    destination = ROOT / relative
    if existing_only and not destination.exists():
        return None
    data = read_blob(commit, relative).replace("\r\n", "\n").replace("\r", "\n")
    return destination, data


def write_atomic(destination: Path, data: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        with temporary:
            temporary.write(data)
        os.replace(temporary.name, destination)
    finally:
        if os.path.exists(temporary.name):
            os.unlink(temporary.name)


def write_derived_ini(config: dict[str, object], spec: dict[str, object]) -> None:
    """Rebuild a derived subscription entry from an already sanitized base entry."""
    base = ROOT / str(spec["base"])
    if not base.exists():
        return
    repository = str(config["ini"]["local_repository"])
    group, path, interval = (str(item) for item in spec["ruleset"])
    ruleset = (
        f"ruleset={group},clash-classic:"
        f"https://raw.githubusercontent.com/{repository}/main/{path},{interval}"
    )
    marker = str(spec["insert_before"])
    lines = base.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines()
    if ruleset not in lines:
        position = next((index for index, line in enumerate(lines) if marker in line), len(lines))
        lines.insert(position, ruleset)
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    header = "\n".join([f"# {spec['title']}", *(f"# {note}" for note in spec["notes"])])
    write_atomic(ROOT / str(spec["output"]), f"{header}\n" + "\n".join(lines) + "\n")


def apply_ini_overrides(text: str, overrides: list[dict[str, object]]) -> str:
    """Force selected ``custom_proxy_group`` fields to local values after sanitizing.

    Each override matches a full INI line by regex and replaces one backtick-separated
    field (0-based, counting the ``custom_proxy_group=`` prefix as field 0).
    """
    if not overrides:
        return text
    output: list[str] = []
    for raw in text.splitlines():
        line = raw
        for spec in overrides:
            if not re.search(str(spec["match"]), line):
                continue
            fields = line.split("`")
            index = int(spec["field"])
            if 0 < index < len(fields):
                fields[index] = str(spec["value"])
                line = "`".join(fields)
            break
        output.append(line)
    return "\n".join(output) + "\n"


def apply_local_policy(config: dict[str, object]) -> None:
    """Restore local additions after both upstream sync and provider downloads."""
    for relative in config["remove"]:
        path = ROOT / relative
        if path.exists():
            path.unlink()
            print(f"Removed excluded path: {relative}")

    additions: dict[Path, list[Path]] = {}
    for manual in sorted((ROOT / "rules").rglob("*.MANUAL.list")):
        target = manual.with_name(manual.name.replace(".MANUAL.list", ".list"))
        if target.exists():
            additions.setdefault(target, []).append(manual)
    for relative, sources in config.get("append_rules", {}).items():
        additions.setdefault(ROOT / relative, []).extend(ROOT / source for source in sources)

    for target, sources in additions.items():
        if target.relative_to(ROOT).as_posix() in config.get("force_empty", []):
            continue
        data = target.read_text(encoding="utf-8")
        seen = {line.strip() for line in data.splitlines() if line.strip() and not line.lstrip().startswith("#")}
        for source in sources:
            new_rules: list[str] = []
            for raw in source.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or line in seen:
                    continue
                seen.add(line)
                new_rules.append(line)
            if new_rules:
                data = data.rstrip() + f"\n\n# Local additions: {source.name}\n" + "\n".join(new_rules) + "\n"
        write_atomic(target, data)

    for relative in config.get("force_empty", []):
        write_atomic(ROOT / relative, "# Reserved for the future home network deployment.\n")

    overrides = config.get("ini_overrides", [])
    if overrides:
        for ini in sorted(ROOT.glob("clash-rule*.ini")):
            original = ini.read_text(encoding="utf-8")
            patched = apply_ini_overrides(original, overrides)
            if patched != original:
                write_atomic(ini, patched)

    for spec in config.get("derived_ini", []):
        write_derived_ini(config, spec)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true", help="apply local rule additions without syncing upstream")
    parser.add_argument("--no-fetch", action="store_true", help="use the configured remote ref without fetching")
    parser.add_argument("--commit", help="synchronize from an explicit commit instead of FETCH_HEAD")
    args = parser.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if args.local_only:
        apply_local_policy(config)
        print("Applied local rule policy without upstream sync.")
        return 0
    upstream = config["upstream"]
    commit = args.commit or fetch_commit(upstream, args.no_fetch)
    include = config["include"]
    exclude = config["exclude"]
    existing_only = bool(config.get("rules_existing_only", False))
    synced = 0
    skipped = 0
    pending: list[tuple[Path, str]] = []

    for relative in upstream_files(commit):
        if not matches(relative, include) or matches(relative, exclude):
            continue
        only_existing = existing_only and relative.startswith("rules/")
        if relative.startswith("clash-rule") and relative.endswith(".ini"):
            destination = ROOT / relative
            if config.get("ini_existing_only", True) and not destination.exists():
                skipped += 1
                continue
            pending.append((destination, apply_ini_overrides(
                sanitize_ini(read_blob(commit, relative), config["ini"]),
                config.get("ini_overrides", []),
            )))
            synced += 1
        else:
            copied = read_path(commit, relative, existing_only=only_existing)
            if copied is None:
                skipped += 1
                continue
            pending.append(copied)
            synced += 1

    for destination, data in pending:
        write_atomic(destination, data)
    apply_local_policy(config)

    print(f"Synchronized {synced} paths; skipped {skipped} unconfigured new paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
