#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 "$ROOT/scripts/sync-codex-skills.py"
python3 "$ROOT/scripts/install-project-skills.py" "$ROOT" codex
echo "Codex skills are available from this repository's .agents/skills directory."
echo "Restart Codex to pick up new skills."
