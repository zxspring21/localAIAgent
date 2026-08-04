#!/usr/bin/env bash
# Start vLLM OpenAI-compatible API server
# Usage: ./scripts/start_vllm.sh [model_name] [port] [tensor_parallel_size]
#
# Setup (once):
#   python3 -m venv .venv
#   .venv/bin/python3 -m ensurepip --upgrade
#   .venv/bin/python3 -m pip install -r requirements-vllm.txt
#
# vLLM 0.11 requires transformers 4.x — NOT 5.x.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

PYTHON="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

ensure_vllm_deps() {
  if ! "$PYTHON" -c "import vllm" 2>/dev/null; then
    echo "vLLM not found. Install with:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python3 -m ensurepip --upgrade"
    echo "  .venv/bin/python3 -m pip install -r requirements-vllm.txt"
    exit 1
  fi

  local tf_major
  tf_major=$("$PYTHON" -c "import transformers; print(transformers.__version__.split('.')[0])")

  if [[ "$tf_major" -ge 5 ]]; then
    echo "WARNING: transformers $("$PYTHON" -c 'import transformers; print(transformers.__version__)') incompatible with vLLM 0.11."
    if [[ -x "${ROOT}/.venv/bin/python3" ]] && "${ROOT}/.venv/bin/python3" -m pip --version &>/dev/null; then
      echo "Downgrading to transformers 4.x..."
      "${ROOT}/.venv/bin/python3" -m pip install -q 'transformers>=4.55.2,<5.0.0'
    else
      echo "Fix manually:"
      echo "  .venv/bin/python3 -m pip install 'transformers>=4.55.2,<5.0.0'"
      exit 1
    fi
  fi
}

ensure_vllm_deps

MODEL="${1:-${VLLM_DEFAULT_MODEL:-meta-llama/Llama-3.1-8B-Instruct}}"
PORT="${2:-8000}"
TP_SIZE="${3:-1}"
HOST="${4:-0.0.0.0}"

MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-8192}"
MAX_BATCHED_TOKENS="${VLLM_MAX_NUM_BATCHED_TOKENS:-$MAX_MODEL_LEN}"
if [[ "$MAX_BATCHED_TOKENS" -lt "$MAX_MODEL_LEN" ]]; then
  MAX_BATCHED_TOKENS="$MAX_MODEL_LEN"
fi

if ! "$PYTHON" -c "import torch; exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  export VLLM_CPU_KVCACHE_SPACE="${VLLM_CPU_KVCACHE_SPACE:-4}"
  echo "Note: No CUDA GPU — vLLM uses CPU backend (very slow on Mac)."
  echo "      For Apple Silicon, consider mlx-lm instead of vLLM."
  echo "      If OOM, try: VLLM_MAX_MODEL_LEN=4096 VLLM_CPU_KVCACHE_SPACE=8 ./scripts/start_vllm.sh"
fi

echo "Starting vLLM server..."
echo "  Python:              $("$PYTHON" -c 'import sys; print(sys.executable)')"
echo "  transformers:        $("$PYTHON" -c 'import transformers; print(transformers.__version__)')"
echo "  vLLM:                $("$PYTHON" -c 'import vllm; print(vllm.__version__)')"
echo "  Model:               ${MODEL}"
echo "  Port:                ${PORT}"
echo "  max_model_len:       ${MAX_MODEL_LEN}"

exec "$PYTHON" -m vllm.entrypoints.openai.api_server \
    --model "${MODEL}" \
    --tensor-parallel-size "${TP_SIZE}" \
    --host "${HOST}" \
    --port "${PORT}" \
    --max-model-len "${MAX_MODEL_LEN}" \
    --max-num-batched-tokens "${MAX_BATCHED_TOKENS}" \
    --trust-remote-code \
    --enable-auto-tool-choice \
    --tool-call-parser llama3_json
