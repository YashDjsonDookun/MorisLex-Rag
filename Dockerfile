# MORISLEX-RAG — Streamlit UI + pipeline worker (port 8502 / 8080)
FROM python:3.11-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding model under /app so the non-root appuser can load it offline (HF_HUB_OFFLINE=1).
# This layer is cached unless base/requirements change; code-only rebuilds skip the download.
# Override: docker build --build-arg EMBEDDING_MODEL=sentence-transformers/other-model .
# Clean rebuild (re-download): docker build --no-cache .
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('$EMBEDDING_MODEL')"

COPY . .
ENV PYTHONPATH=/app \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

# Non-root user for K8s securityContext runAsUser: 1000
RUN groupadd -r -g 1000 appuser && useradd -r -u 1000 -g 1000 -d /app appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8502
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1
# Use shell so PYTHONPATH is set for Streamlit and any subprocesses
CMD ["/bin/sh", "-c", "export PYTHONPATH=/app && exec streamlit run ui/Home.py --server.port=8502 --server.address=0.0.0.0 --server.headless=true"]
