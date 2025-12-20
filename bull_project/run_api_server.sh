#!/usr/bin/env bash
set -euo pipefail

# Determine project root (directory containing this script)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$PROJECT_ROOT/.venv/bin"

# Prefer project virtual environment if it exists
if [[ -x "$VENV_BIN/python" ]]; then
    PYTHON_BIN="$VENV_BIN/python"
else
    PYTHON_BIN="$(command -v python3 || command -v python)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
    echo "Python interpreter not found. Install Python or create .venv first." >&2
    exit 1
fi

cd "$PROJECT_ROOT"
exec "$PYTHON_BIN" -m bull_project.bull_bot.core.api_server "$@"
