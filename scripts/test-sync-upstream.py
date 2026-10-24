#!/usr/bin/env python3
"""Regression checks for upstream filtering and local rule preservation."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sync_upstream", ROOT / "scripts/sync-upstream.py")
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)
CONFIG = json.loads((ROOT / "config/upstream-sync.json").read_text(encoding="utf-8"))


class IniFilteringTests(unittest.TestCase):
    def test_exclusions_preserve_escaped_pipes_and_node_matching(self):
        line = r"custom_proxy_group=test`url-test`(^(?!.*(?:WHS|CQGAS|LFB|\[LS\]|\|L\|))(?=.*US).+$)`https://example.com`300"
        result = SYNC.sanitize_ini(line, CONFIG["ini"])
        pattern = result.split("`")[2]
        # A literal |L| marker must still be excluded; ordinary US nodes match.
        self.assertIn(r"\|L\|", pattern)
        self.assertIsNotNone(re.search(pattern, "US ordinary"))
        self.assertIsNone(re.search(pattern, "US |L|"))
        self.assertNotIn("WHS", result)
        self.assertNotIn("CQGAS", result)

    def test_filter_leaves_unrelated_regex_unchanged(self):
        line = r"custom_proxy_group=test`select`(foo\|bar|baz\|)"
        self.assertEqual(SYNC.sanitize_ini(line, CONFIG["ini"]), line + "\n")

    def test_apple_default_is_direct_and_can_still_select_proxy(self):
        line = "custom_proxy_group=🍏 苹果服务`select`[]🚀 主要代理`[]🚄 本地直连`[]🇺🇸 美国节点"
        result = SYNC.sanitize_ini(line, CONFIG["ini"])
        self.assertEqual(result.split("`")[2:], ["[]🚄 本地直连", "[]🚀 主要代理", "[]🇺🇸 美国节点\n"])

    def test_dedicated_groups_and_rulesets_are_removed(self):
        content = "\n".join([
            "ruleset=🧭 WHSpecial,clash-classic:https://example.com/WHSpecial.yaml",
            "custom_proxy_group=重庆 CQGAS`select`[]DIRECT",
            "custom_proxy_group=wanhua WH`select`[]DIRECT",
            "custom_proxy_group=🚄 本地直连`select`[]DIRECT",
        ])
        self.assertEqual(SYNC.sanitize_ini(content, CONFIG["ini"]), "custom_proxy_group=🚄 本地直连`select`[]DIRECT\n")

    def test_all_forbidden_alternatives_are_removed(self):
        line = r"custom_proxy_group=test`select`((?:WH|WHSpecial|CQGAS))"
        result = SYNC.sanitize_ini(line, CONFIG["ini"])
        self.assertNotRegex(result, r"(?i)WH|CQGAS")


class SyncIntegrationTests(unittest.TestCase):
    def test_sync_preserves_local_rules_and_does_not_grow_on_repeat(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "config").mkdir()
            (root / "rules").mkdir()
            shutil.copyfile(ROOT / "scripts/sync-upstream.py", root / "scripts/sync-upstream.py")
            shutil.copyfile(ROOT / "config/upstream-sync.json", root / "config/upstream-sync.json")
            (root / "rules/A-ForcedDirect.list").write_text("DOMAIN,upstream.example\n", encoding="utf-8")
            (root / "rules/A-ForcedDirect.SERVER.list").write_text("IP-CIDR,192.0.2.1/32,no-resolve\n", encoding="utf-8")
            (root / "rules/A-ForcedDirect.MANUAL.list").write_text("DOMAIN,upstream-manual.example\n", encoding="utf-8")
            (root / "rules/gohome.list").write_text("DOMAIN,upstream-home.example\n", encoding="utf-8")
            (root / "clash-rule-new.ini").write_text("[custom]\n", encoding="utf-8")
            for args in (["init", "-q"], ["add", "."], ["-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "upstream fixture"]):
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            manual = root / "rules/A-ForcedDirect.MANUAL.list"
            manual.write_text("# Local only\nDOMAIN,personal.example\n", encoding="utf-8")
            (root / "clash-rule-new.ini").unlink()
            command = [sys.executable, "scripts/sync-upstream.py", "--commit", commit]
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            source = root / "rules/A-ForcedDirect.list"
            first = source.read_text(encoding="utf-8")
            self.assertIn("DOMAIN,personal.example\n", first)
            self.assertIn("IP-CIDR,192.0.2.1/32,no-resolve\n", first)
            self.assertEqual(manual.read_text(encoding="utf-8"), "# Local only\nDOMAIN,personal.example\n")
            self.assertFalse((root / "clash-rule-new.ini").exists())
            self.assertNotIn("DOMAIN,", (root / "rules/gohome.list").read_text(encoding="utf-8"))
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            self.assertEqual(source.read_text(encoding="utf-8"), first)
            subprocess.run([sys.executable, "scripts/sync-upstream.py", "--local-only"], cwd=root, check=True, capture_output=True)
            self.assertEqual(source.read_text(encoding="utf-8"), first)


class DerivedIniTests(unittest.TestCase):
    def test_derived_entry_is_generated_before_its_anchor_and_is_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("scripts", "config", "rules", "clash-classic"):
                (root / name).mkdir()
            shutil.copyfile(ROOT / "scripts/sync-upstream.py", root / "scripts/sync-upstream.py")
            shutil.copyfile(ROOT / "config/upstream-sync.json", root / "config/upstream-sync.json")
            (root / "rules/A-ForcedDirect.list").write_text("DOMAIN,upstream.example\n", encoding="utf-8")
            (root / "rules/A-ForcedDirect.SERVER.list").write_text("IP-CIDR,192.0.2.1/32,no-resolve\n", encoding="utf-8")
            (root / "clash-rule.ini").write_text(
                "# clash-rule-small\n[custom]\n"
                "ruleset=⛔ 禁止访问,clash-classic:https://example.com/clash-classic/MyReject.yaml,28800\n",
                encoding="utf-8",
            )
            command = [sys.executable, "scripts/sync-upstream.py", "--local-only"]
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            derived = (root / "clash-rule-ad.ini").read_text(encoding="utf-8")
            self.assertTrue(derived.startswith("# clash-rule-small-ad\n"))
            self.assertLess(derived.index("ADDRejectLite.yaml,28800"), derived.index("clash-classic/MyReject.yaml"))
            self.assertEqual(derived.count("ruleset="), 2)
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            self.assertEqual((root / "clash-rule-ad.ini").read_text(encoding="utf-8"), derived)


class IniOverrideTests(unittest.TestCase):
    def test_override_replaces_only_matching_field(self):
        overrides = CONFIG["ini_overrides"]
        line = "custom_proxy_group=🏘 回家专用低延`url-test`(回家).+$`http://192.168.66.66:51512`600,,15"
        other = "custom_proxy_group=🚄 本地直连`select`[]DIRECT"
        result = SYNC.apply_ini_overrides(line + "\n" + other + "\n", overrides)
        fields = result.splitlines()[0].split("`")
        self.assertEqual(fields[3], "http://192.168.1.75:5666")
        self.assertEqual(fields[0], "custom_proxy_group=🏘 回家专用低延")
        self.assertEqual(fields[1], "url-test")
        self.assertEqual(fields[4], "600,,15")
        self.assertEqual(result.splitlines()[1], other)

    def test_override_is_idempotent_and_skips_untouched_lines(self):
        overrides = CONFIG["ini_overrides"]
        line = "custom_proxy_group=🏘 回家专用灾备`fallback`(回家)`http://192.168.1.75:5666`30,,15"
        once = SYNC.apply_ini_overrides(line + "\n", overrides)
        twice = SYNC.apply_ini_overrides(once, overrides)
        self.assertEqual(once, twice)
        self.assertIn("192.168.1.75:5666", once)
        self.assertEqual(SYNC.apply_ini_overrides("", overrides), "\n")


    def test_override_leaves_select_group_member_lists_alone(self):
        # 组引用行里也会出现「回家专用灾备」这些字，匹配必须限定在组定义行和类型字段上
        overrides = CONFIG["ini_overrides"]
        line = "custom_proxy_group=🏡 回家节点`select`[]🏘 回家专用灾备`[]🏘 回家专用低延`[]🏘 回家专用手选`[]🚄 本地直连"
        self.assertEqual(SYNC.apply_ini_overrides(line + "\n", overrides), line + "\n")


class ValidationTests(unittest.TestCase):
    def test_invalid_node_regex_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("scripts", "config", "rules", "clash-classic"):
                (root / name).mkdir()
            shutil.copyfile(ROOT / "scripts/validate-rules.py", root / "scripts/validate-rules.py")
            shutil.copyfile(ROOT / "config/upstream-sync.json", root / "config/upstream-sync.json")
            (root / "clash-rule.ini").write_text("custom_proxy_group=bad`select`(broken\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "scripts/validate-rules.py"], cwd=root, text=True, encoding="utf-8", capture_output=True)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("invalid node regex", result.stdout)


if __name__ == "__main__":
    unittest.main()
