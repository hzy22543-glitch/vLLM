#!/usr/bin/env bash
# Start one local APC condition. Run from the repository root.
set -euo pipefail
mode="${1:?Usage: bash scripts/serve.sh on|off /absolute/model/path}"
model_path="${2:?Provide an existing local Qwen2.5-1.5B-Instruct directory}"
case "$mode" in
  on) apc_flag=--enable-prefix-caching ;;
  off) apc_flag=--no-enable-prefix-caching ;;
  *) echo "Mode must be on or off" >&2; exit 2 ;;
esac
if [[ ! -d "$model_path" ]]; then
  echo "Model directory does not exist: $model_path" >&2
  exit 2
fi
mkdir -p runs/service-logs
log_file="runs/service-logs/${mode}-$(date -u +%Y%m%dT%H%M%S%N).log"
echo "Saving server log: $log_file"
VLLM_SERVER_DEV_MODE=1 vllm serve "$model_path" \
  --host 127.0.0.1 --port 8000 --dtype half \
  --gpu-memory-utilization 0.85 --max-model-len 4096 \
  --max-num-seqs 256 --max-num-batched-tokens 2048 --enable-chunked-prefill \
  --seed 42 --generation-config vllm "$apc_flag" 2>&1 | tee "$log_file"
