#!/usr/bin/env bash
# Optional: vendor the official Anthropic skills repo next to skills/anthropic/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/vendor/anthropic-skills"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only
else
  git clone --depth 1 --filter=blob:none --sparse https://github.com/anthropics/skills.git "$DEST"
  git -C "$DEST" sparse-checkout set skills
fi
echo "Synced to $DEST — restart the backend to load SKILL.md files."
