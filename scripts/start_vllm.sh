#!/usr/bin/env bash
# Start vLLM OpenAI-compatible API server
# Usage: ./scripts/start_vllm.sh [model_name] [port] [tensor_parallel_size]

set -euo pipefail

MODEL="${1:-meta-llama/Meta-Llama-3-8B-Instruct}"
PORT="${2:-8000}"
TP_SIZE="${3:-1}"
HOST="${4:-0.0.0.0}"

echo "Starting vLLM server..."
echo "  Model: ${MODEL}"
echo "  Port:  ${PORT}"
echo "  TP:    ${TP_SIZE}"

python3 -m vllm.entrypoints.openai.api_server \
    --model "${MODEL}" \
    --tensor-parallel-size "${TP_SIZE}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --trust-remote-code \
    --enable-auto-tool-choice \
    --tool-call-parser llama3_json
