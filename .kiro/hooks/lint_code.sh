#!/usr/bin/env bash
# Run format, import, and style checks for a saved Python file or target path.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
cd "$REPOSITORY_ROOT"

if [[ -n "${KIRO_PYTHON_BIN:-}" ]]; then
    PYTHON_BIN="$KIRO_PYTHON_BIN"
elif [[ -x "$REPOSITORY_ROOT/venv/bin/python" ]]; then
    PYTHON_BIN="$REPOSITORY_ROOT/venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "No Python interpreter is available for the Kiro lint hook." >&2
    exit 127
fi

if [[ "$#" -eq 1 && "$1" == "." && -n "${KIRO_FILE_PATH:-}" ]]; then
    set -- "$KIRO_FILE_PATH"
elif [[ "$#" -eq 0 ]]; then
    set -- .
fi

"$PYTHON_BIN" -m black --check "$@"
"$PYTHON_BIN" -m isort --check-only --profile black "$@"
"$PYTHON_BIN" -m flake8 "$@"
