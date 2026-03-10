#!/usr/bin/env bash
# Run the RAG app on your Mac with the pipeline in-process so embedding uses Apple Silicon GPU (MPS).
# Usage: from repo root,   ./scripts/run_with_gpu.sh
# Then open http://localhost:8502 → Pipeline → Run full pipeline.

set -e
cd "$(dirname "$0")/.."

if [ "$(uname -s)" != "Darwin" ]; then
  echo "run_with_gpu.sh is for macOS (Apple Silicon). On this machine the pipeline will use CPU."
fi

if [ ! -d ".venv" ]; then
  echo "No .venv found. Run: make venv"
  exit 1
fi

echo "Starting app with pipeline on this machine (GPU/MPS for embedding)..."
echo "Open http://localhost:8502 → Pipeline → Run full pipeline."
echo ""

PIPELINE_SERVICE_URL= PIPELINE_API_PREFIX= PYTHONPATH="$(pwd)" .venv/bin/streamlit run ui/Home.py --server.port "${STREAMLIT_PORT:-8502}" --server.headless true
