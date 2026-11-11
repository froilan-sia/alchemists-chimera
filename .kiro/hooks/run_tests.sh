#!/usr/bin/env bash
# Run the repository test hook with the project's available Python interpreter.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
cd "$REPOSITORY_ROOT"

if [[ "${1:-}" == "--pytest" ]]; then
    shift
fi

if [[ -n "${KIRO_PYTHON_BIN:-}" ]]; then
    PYTHON_BIN="$KIRO_PYTHON_BIN"
elif [[ -x "$REPOSITORY_ROOT/venv/bin/python" ]]; then
    PYTHON_BIN="$REPOSITORY_ROOT/venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "No Python interpreter is available for the Kiro test hook." >&2
    exit 127
fi

if [[ "$#" -eq 0 ]]; then
    set -- tests/ -xvs --tb=short
fi

exec "$PYTHON_BIN" -m pytest "$@"
