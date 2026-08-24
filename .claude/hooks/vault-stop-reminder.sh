#!/bin/bash
# Stop hook: nudge Claude to update .claudevault/ (vault-skill) before ending a turn.
#
# Stop fires on every turn-end. This reminds every turn the vault looks stale -
# it only skips when the vault was JUST touched (this turn's own update), so it
# doesn't immediately re-block right after Claude updates it. No-ops entirely in
# projects with no .claudevault/.

cat >/dev/null  # drain stdin; hook input isn't needed
cwd="$PWD"
vault_dir="$cwd/.claudevault"

[ -d "$vault_dir" ] || exit 0

now=$(date +%s)

# Most recent mtime among real vault content (skip raw/ intake and outputs/,
# which don't represent "the vault was updated" per vault-skill conventions).
last_update=0
while IFS= read -r -d '' f; do
  m=$(stat -f "%m" "$f" 2>/dev/null || stat -c "%Y" "$f" 2>/dev/null)
  if [ -n "$m" ] && [ "$m" -gt "$last_update" ]; then
    last_update=$m
  fi
done < <(find "$vault_dir" \
  -path "$vault_dir/raw" -prune -o \
  -path "$vault_dir/outputs" -prune -o \
  -type f -name '*.md' -print0 2>/dev/null)

seconds_since_update=$((now - last_update))

# Vault was touched within the last 3 minutes - assume this turn already
# handled it. Let the stop proceed.
if [ "$seconds_since_update" -lt 180 ]; then
  exit 0
fi

cat <<'EOF'
{"decision":"block","reason":"This project has a .claudevault/ knowledge vault (vault-skill) that has not been updated in a while. Before stopping, briefly check: did this session make a decision, change project context, or surface reusable knowledge worth logging? If yes, update .claudevault/ now (logs/, decisions/, knowledge/, context.md) per the vault-skill. If nothing vault-worthy happened, it is fine to stop as-is."}
EOF
