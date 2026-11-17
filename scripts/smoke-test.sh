#!/usr/bin/env bash
# 交付链路冒烟测试：检查 6 条短链是否可用、关键节点/组是否齐全
# 用法: bash smoke-test.sh    （需要能解析 *.lululucy.top）
set -uo pipefail

LINKS="3PXMe mupDF poTPl voxC8 PLl4z 8xFBY"
BASE="https://s.lululucy.top"
TMP=$(mktemp -d)
FAIL=0

for s in $LINKS; do
  f="$TMP/$s.yaml"
  code=$(curl -sL -m 120 -o "$f" -w '%{http_code}' "$BASE/$s" 2>/dev/null)
  if [ "$code" != "200" ]; then
    echo "FAIL $s http=$code"; FAIL=1; continue
  fi
  nodes=$(grep -c '^  - name:' "$f" 2>/dev/null || echo 0)
  groups=$(awk '/^proxy-groups:/{f=1;next} /^(rules|rule-providers):/{f=0} f&&/^  - name:/{c++} END{print c+0}' "$f")
  rules=$(awk '/^rules:/{f=1;next} f&&/^  - /{c++} END{print c+0}' "$f")
  liuzi=$(grep -c '美国留子高质' "$f" || true)
  fish=$(awk '/^  - name: 🐟 漏网之鱼/{f=1} f{print;c++} c>4{exit}' "$f" | sed -n '4p' | sed 's/^ *- //')
  printf "%-8s http=%s nodes=%-3s groups=%-3s rules=%-5s 留子=%s 漏网首=%s\n" "$s" "$code" "$nodes" "$groups" "$rules" "$liuzi" "$fish"
  [ "$nodes" -lt 40 ] && { echo "  WARN nodes too few"; FAIL=1; }
  [ "$liuzi" -lt 1 ] && { echo "  WARN 留子 missing"; FAIL=1; }
done

rm -rf "$TMP"
if [ "$FAIL" -eq 0 ]; then echo "SMOKE OK"; else echo "SMOKE FAILED"; exit 1; fi
