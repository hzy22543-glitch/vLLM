#!/usr/bin/env bash
set -e

echo "===== OS ====="
uname -a

echo "===== GPU ====="
nvidia-smi

echo "===== Python ====="
python --version

echo "===== vLLM ====="
python -m pip show vllm

echo "===== PyTorch ====="
python -c "import torch; print(torch.__version__); print(torch.version.cuda)"

echo "===== Transformers ====="
python -m pip show transformers