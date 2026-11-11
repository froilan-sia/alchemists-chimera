#!/usr/bin/env bash
set -Eeuo pipefail

# Hugging Face Spaces runs the container as UID 1000. Keep all runtime state
# under /app (or APP_DIR) so Ollama, Hugging Face, and ChromaDB are writable.
APP_DIR="${APP_DIR:-/app}"
OLLAMA_MODELS="${OLLAMA_MODELS:-${APP_DIR}/.ollama/models}"
HF_HOME="${HF_HOME:-${APP_DIR}/.cache}"
DATA_DIR="${DATA_DIR:-${APP_DIR}/data}"
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_URL="${OLLAMA_URL:-http://${OLLAMA_HOST}}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:3b}"
OLLAMA_STARTUP_TIMEOUT="${OLLAMA_STARTUP_TIMEOUT:-120}"
OLLAMA_POLL_INTERVAL="${OLLAMA_POLL_INTERVAL:-2}"
STREAMLIT_PORT="${STREAMLIT_PORT:-7860}"
STREAMLIT_ADDRESS="${STREAMLIT_ADDRESS:-0.0.0.0}"
STARTUP_LOG_FILE="${STARTUP_LOG_FILE:-${APP_DIR}/startup.log}"
OLLAMA_LOG_FILE="${OLLAMA_LOG_FILE:-${APP_DIR}/ollama.log}"

export OLLAMA_MODELS HF_HOME OLLAMA_HOST

OLLAMA_PID=""
STREAMLIT_PID=""

log() {
    local message
    message="$(date -u '+%Y-%m-%dT%H:%M:%SZ') [start] $*"
    printf '%s\n' "$message"
    printf '%s\n' "$message" >>"$STARTUP_LOG_FILE" 2>/dev/null || true
}

cleanup() {
    local exit_status=$?
    trap - EXIT INT TERM

    if [[ -n "$STREAMLIT_PID" ]] && kill -0 "$STREAMLIT_PID" 2>/dev/null; then
        log "Stopping Streamlit process (PID ${STREAMLIT_PID})."
        kill "$STREAMLIT_PID" 2>/dev/null || true
    fi
    if [[ -n "$OLLAMA_PID" ]] && kill -0 "$OLLAMA_PID" 2>/dev/null; then
        log "Stopping Ollama process (PID ${OLLAMA_PID})."
        kill "$OLLAMA_PID" 2>/dev/null || true
    fi

    if [[ -n "$STREAMLIT_PID" ]]; then
        wait "$STREAMLIT_PID" 2>/dev/null || true
    fi
    if [[ -n "$OLLAMA_PID" ]]; then
        wait "$OLLAMA_PID" 2>/dev/null || true
    fi

    log "Startup process exited with status ${exit_status}."
    exit "$exit_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

prepare_runtime_directories() {
    log "Preparing runtime directories for UID $(id -u)."
    mkdir -p "$OLLAMA_MODELS" "$HF_HOME" "$DATA_DIR"

    # The image is normally already running as UID 1000. When the script is
    # used as root during a local container check, assign ownership explicitly.
    if [[ "$(id -u)" -eq 0 ]]; then
        chown -R 1000:1000 "$OLLAMA_MODELS" "$HF_HOME" "$DATA_DIR"
    fi
    chmod -R a+rwX "$OLLAMA_MODELS" "$HF_HOME" "$DATA_DIR"

    touch "$STARTUP_LOG_FILE" "$OLLAMA_LOG_FILE"
}

require_commands() {
    local command_name
    for command_name in curl ollama streamlit; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            log "ERROR: Required command not found: ${command_name}."
            return 1
        fi
    done
}

wait_for_ollama() {
    local deadline=$((SECONDS + OLLAMA_STARTUP_TIMEOUT))
    log "Waiting for Ollama readiness at ${OLLAMA_URL}/api/tags."

    while (( SECONDS < deadline )); do
        if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
            log "ERROR: Ollama exited before becoming ready."
            return 1
        fi
        if curl --fail --silent --show-error --max-time 5 \
            "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
            log "Ollama is ready."
            return 0
        fi
        sleep "$OLLAMA_POLL_INTERVAL"
    done

    log "ERROR: Ollama did not become ready within ${OLLAMA_STARTUP_TIMEOUT} seconds."
    return 1
}

model_is_cached() {
    ollama list 2>/dev/null \
        | awk 'NR > 1 { print $1 }' \
        | grep --fixed-strings --line-regexp --quiet "$OLLAMA_MODEL"
}

start_ollama() {
    log "Starting Ollama server in the background."
    ollama serve >"$OLLAMA_LOG_FILE" 2>&1 &
    OLLAMA_PID=$!

    if ! wait_for_ollama; then
        return 1
    fi

    if model_is_cached; then
        log "Ollama model ${OLLAMA_MODEL} is already cached."
    else
        log "Pulling Ollama model ${OLLAMA_MODEL}."
        if ! ollama pull "$OLLAMA_MODEL"; then
            log "ERROR: Failed to pull Ollama model ${OLLAMA_MODEL}."
            return 1
        fi
        log "Ollama model ${OLLAMA_MODEL} is ready."
    fi
}

start_streamlit() {
    log "Starting Streamlit on ${STREAMLIT_ADDRESS}:${STREAMLIT_PORT}."
    streamlit run "${APP_DIR}/app.py" \
        --server.port="$STREAMLIT_PORT" \
        --server.address="$STREAMLIT_ADDRESS" &
    STREAMLIT_PID=$!

    # Keep the shell as PID 1, monitor both services, and terminate the other
    # service if either process exits unexpectedly.
    while kill -0 "$STREAMLIT_PID" 2>/dev/null; do
        if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
            log "ERROR: Ollama stopped while Streamlit was running."
            return 1
        fi
        sleep 2
    done

    if wait "$STREAMLIT_PID"; then
        return 0
    fi
    log "ERROR: Streamlit exited unexpectedly."
    return 1
}

main() {
    prepare_runtime_directories
    require_commands
    start_ollama
    start_streamlit
}

main "$@"
