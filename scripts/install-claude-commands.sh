#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$ROOT/scripts/sync-codex-skills.py"
python3 "$ROOT/scripts/install-project-skills.py" "$ROOT" claude
echo "Claude Code project skills are available from this repository's .claude/skills directory."
