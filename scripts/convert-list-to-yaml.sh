#!/usr/bin/env bash
set -Eeuo pipefail

INPUT_ROOT="${INPUT_ROOT:-rules}"
OUTPUT_ROOT="${OUTPUT_ROOT:-clash-classic}"
STATIC_MANIFEST="${STATIC_MANIFEST:-config/static-yaml-outputs.txt}"

EXCLUDE_FILES=(
  "app/GameDLCN.MANUAL.list"
  "MyDirect.SERVER.list"
)
EXCLUDE_PREFIXES=("USER-AGENT,")
REPLACE_PREFIXES=(
  "URL-REGEX,^https://|DOMAIN-REGEX,^"
  "URL-REGEX,^http://|DOMAIN-REGEX,^"
  "URL-REGEX,|DOMAIN-REGEX,"
)

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
generated_root="$work_dir/output"
mkdir -p "$generated_root"

prefix_regex=""
for prefix in "${EXCLUDE_PREFIXES[@]}"; do
  escaped="$(printf '%s\n' "$prefix" | sed 's/[][()\.^$?*+|]/\\&/g')"
  if [[ -z "$prefix_regex" ]]; then
    prefix_regex="$escaped"
  else
    prefix_regex="$prefix_regex|$escaped"
  fi
done
[[ -n "$prefix_regex" ]] && prefix_regex="^($prefix_regex)"

replace_file="$work_dir/replacements"
printf '%s\n' "${REPLACE_PREFIXES[@]}" > "$replace_file"
exclude_file="$work_dir/excludes"
printf '%s\n' "${EXCLUDE_FILES[@]}" > "$exclude_file"

process_file() {
  local input_file="$1" relative_path output_path
  relative_path="${input_file#"$INPUT_ROOT"/}"
  if grep -Fxq "$relative_path" "$exclude_file"; then
    echo "Skipping excluded file: $input_file"
    return 0
  fi

  output_path="$generated_root/${relative_path%.list}.yaml"
  mkdir -p "$(dirname "$output_path")"
  {
    echo "payload:"
    awk -v pattern="$prefix_regex" -v replace_file="$replace_file" '
      BEGIN {
        while ((getline line < replace_file) > 0) {
          split(line, arr, /\|/)
          old_prefix[++replace_count] = arr[1]
          new_prefix[replace_count] = arr[2]
        }
        close(replace_file)
      }
      {
        sub(/\r$/, "", $0)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
        if ($0 == "" || $0 ~ /^#/) next
        sub(/[[:space:]]+#.*$/, "", $0)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
        if ($0 == "") next
        for (i = 1; i <= replace_count; i++) {
          if (index($0, old_prefix[i]) == 1) {
            $0 = new_prefix[i] substr($0, length(old_prefix[i]) + 1)
            break
          }
        }
        if (pattern != "" && $0 ~ pattern) next
        if (!seen[$0]++) print " - " $0
      }
    ' "$input_file"
  } > "$output_path"
}

export INPUT_ROOT prefix_regex replace_file exclude_file generated_root
export -f process_file
find "$INPUT_ROOT" -type f -name '*.list' -print0 |
  xargs -0 -r -n 1 -P "$(nproc)" bash -c 'process_file "$1"' _

mkdir -p "$OUTPUT_ROOT"
while IFS= read -r existing; do
  [[ -z "$existing" ]] && continue
  [[ "$existing" == \#* ]] && continue
  if ! grep -Fxq "clash-classic/$existing" "$STATIC_MANIFEST" 2>/dev/null; then
    rm -f "$OUTPUT_ROOT/$existing"
  fi
done < <(cd "$OUTPUT_ROOT" && find . -type f -name '*.yaml' -printf '%P\n')
cp -R "$generated_root"/. "$OUTPUT_ROOT"/
find "$OUTPUT_ROOT" -type d -empty -delete

echo "Conversion finished: $(find "$generated_root" -type f -name '*.yaml' | wc -l) generated YAML files."
