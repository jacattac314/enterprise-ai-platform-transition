#!/usr/bin/env bash
# Ollama container entrypoint.
# Starts the Ollama server, waits for it to be ready, pulls the model if not
# already cached in the /models volume, then keeps the server running.
set -euo pipefail

MODEL_NAME="${MODEL_NAME:-qwen2.5:7b}"
OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
WAIT_TIMEOUT=120

echo "[entrypoint] Starting Ollama server (model=${MODEL_NAME})"

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for server to become ready
echo "[entrypoint] Waiting for Ollama to be ready (timeout=${WAIT_TIMEOUT}s)..."
elapsed=0
until curl -sf "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; do
    if [ $elapsed -ge $WAIT_TIMEOUT ]; then
        echo "[entrypoint] ERROR: Ollama did not become ready within ${WAIT_TIMEOUT}s"
        exit 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done
echo "[entrypoint] Ollama ready after ${elapsed}s"

# Pull model if not already in the local cache
if ollama list | grep -q "^${MODEL_NAME}"; then
    echo "[entrypoint] Model '${MODEL_NAME}' already cached — skipping pull"
else
    echo "[entrypoint] Pulling model '${MODEL_NAME}'..."
    ollama pull "${MODEL_NAME}"
    echo "[entrypoint] Model pull complete"
fi

echo "[entrypoint] Serving model '${MODEL_NAME}' on ${OLLAMA_HOST}:${OLLAMA_PORT}"

# Keep Ollama process in foreground
wait $OLLAMA_PID
