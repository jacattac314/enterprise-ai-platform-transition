#!/usr/bin/env bash
# Ollama container health check.
# Returns 0 (healthy) if the API is reachable AND the configured model is loaded.
set -euo pipefail

OLLAMA_PORT="${OLLAMA_PORT:-11434}"
MODEL_NAME="${MODEL_NAME:-qwen2.5:7b}"

# 1. API reachability
if ! curl -sf "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
    echo "UNHEALTHY: Ollama API not reachable on port ${OLLAMA_PORT}"
    exit 1
fi

# 2. Model is loaded (present in /api/tags response)
if ! curl -sf "http://localhost:${OLLAMA_PORT}/api/tags" \
    | grep -q "\"${MODEL_NAME}\""; then
    echo "UNHEALTHY: Model '${MODEL_NAME}' not found in loaded models"
    exit 1
fi

echo "HEALTHY: Ollama serving ${MODEL_NAME} on port ${OLLAMA_PORT}"
exit 0
