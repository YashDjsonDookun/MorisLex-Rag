#!/usr/bin/env bash
# MORISLEX-RAG: one script for deploy and run (prod, use-host-state, or local).
#
# Modes and resource use:
#   ./deploy.sh                    → Prod: pure K8s. State in PVC, compute in-cluster (whatever K8s offers: CPU/memory as configured).
#   ./deploy.sh --use-host-state   → K8s + host leverage. Uses host state, configs, logs, and Engine data (no re-index). Compute still in-cluster (CPU); max out host-mounted resources where possible.
#   ./deploy.sh --local            → Local: GPU-first. Runs on this machine; embedding and pipeline use GPU (MPS on Mac, CUDA if available). Ollama/LM Studio on host use their own GPU.
#
# Prereqs (K8s): Rancher Desktop running. PATH: export PATH="$HOME/.rd/bin:$PATH"
# LLM: In-cluster Ollama by default (models pulled in containers by deploy.sh). Use --no-pull-models to skip. LM Studio: set Playground in Config Center for host LM.
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$PWD"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[deploy]${NC} $1"; }
ok()   { echo -e "${GREEN}[  ok  ]${NC} $1"; }
warn() { echo -e "${YELLOW}[ warn ]${NC} $1"; }
fail() { echo -e "${RED}[FAIL  ]${NC} $1"; exit 1; }

NAMESPACE="morislex-rag"
IMAGE_NAME="morislex-rag:latest"
KUSTOMIZE_DIR="k8s/overlays/local"
STREAMLIT_PORT="${STREAMLIT_PORT:-8502}"

usage() {
    echo "Usage: ./deploy.sh [MODE] [OPTIONS]"
    echo ""
    echo "Modes (choose one for deploy):"
    echo "  (none) / --prod     Prod: pure K8s. State in PVC, compute in-cluster (CPU/memory as configured)."
    echo "  --use-host-state   K8s + host: mount this machine's state, configs, logs, Engine data (no re-index). Compute in-cluster."
    echo "  --local             Local: GPU-first on this machine (MPS/CUDA for embedding and pipeline). Venv + Streamlit in-process."
    echo ""
    echo "Options (all modes):"
    echo "  --down              Tear down (use with same mode if you used --use-host-state to deploy)"
    echo "  --status            Show pods/services and port-forward hint"
    echo "  --logs              Stream pod logs (--logs --previous for last exited container)"
    echo "  -h, --help          Show this help"
    echo ""
    echo "Options (K8s modes only):"
    echo "  --no-cache          Build Docker image without cache"
    echo "  --no-pull-models    Do not pull Ollama models (use if you use LM Studio only or already have models)"
    echo ""
    echo "LLM: In-cluster Ollama by default (deploy pulls models in cluster). Use --no-pull-models to skip. For LM Studio: set Playground in Config Center."
    echo ""
    echo "Examples:"
    echo "  ./deploy.sh                      # Prod K8s deploy + port-forward"
    echo "  ./deploy.sh --use-host-state     # K8s reusing local index + port-forward"
    echo "  ./deploy.sh --local              # Run on Mac with GPU"
    echo "  ./deploy.sh --use-host-state --down   # Tear down when you deployed with --use-host-state"
    echo "  ./deploy.sh --local --no-pull-models  # Local run, skip Ollama pull (e.g. LM Studio only)"
    exit 0
}

NO_CACHE=""
ACTION="deploy"
LOG_PREVIOUS=""
LOCAL_RUN=""
USE_HOST_STATE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --local)            LOCAL_RUN=1; shift ;;
        --use-host-state)   USE_HOST_STATE=1; shift ;;
        --prod)             shift ;;
        --no-cache)         NO_CACHE="--no-cache"; shift ;;
        --no-pull-models)   DEPLOY_SKIP_OLLAMA_PULL=1; shift ;;
        --down)             ACTION="down"; shift ;;
        --status)           ACTION="status"; shift ;;
        --logs)             ACTION="logs"; shift ;;
        --previous)         LOG_PREVIOUS="--previous"; shift ;;
        -h|--help)          usage ;;
        *)                  fail "Unknown option: $1. Use --help for usage." ;;
    esac
done

[[ -n "$USE_HOST_STATE" ]] && KUSTOMIZE_DIR="k8s/overlays/use-host-state"

# Default RAG models (Ollama). Cached after first pull. Skip with --no-pull-models.
OLLAMA_MODELS="qwen2.5:3b qwen2.5:0.5b llama3.2:1b"

# Pull on host (for --local).
pull_ollama_models() {
    if [[ -n "${DEPLOY_SKIP_OLLAMA_PULL:-}" ]]; then return 0; fi
    if ! command -v ollama >/dev/null 2>&1; then
        warn "Ollama not in PATH. For Chat: run Ollama and make ollama-pull, or use LM Studio and set Playground in Config Center."
        return 0
    fi
    log "Ensuring Ollama models on host (cached after first pull)..."
    for m in $OLLAMA_MODELS; do
        if ollama pull "$m" 2>/dev/null; then
            ok "Pulled or already present: $m"
        else
            warn "Could not pull $m (Ollama running?). Chat may fail until models are available."
        fi
    done
}

# Primary model for Chat (and warm-up). Must match configs/app.yaml llm.models.primary.
OLLAMA_PRIMARY_MODEL="qwen2.5:3b"

# Pull inside the in-cluster Ollama pod so Chat works without host LLM.
pull_ollama_models_in_cluster() {
    if [[ -n "${DEPLOY_SKIP_OLLAMA_PULL:-}" ]]; then return 0; fi
    if ! kubectl get deployment ollama -n "$NAMESPACE" >/dev/null 2>&1; then
        warn "Ollama deployment not found; skipping in-cluster model pull."
        return 0
    fi
    log "Pulling Ollama models inside cluster (cached in PVC after first run)..."
    for m in $OLLAMA_MODELS; do
        if kubectl exec -n "$NAMESPACE" deploy/ollama -- ollama pull "$m" 2>/dev/null; then
            ok "In-cluster: $m"
        else
            warn "Could not pull $m in cluster (Ollama ready?). Chat may fail until models are available."
        fi
    done
}

# Load primary model in Ollama so Chat works as soon as the UI is opened (no cold-start wait).
# Uses port-forward + curl with long timeout (5 min) so we do not close the connection while
# the model is loading; closing mid-load causes "client connection closed before server
# finished loading" and aborts the load (Ollama then returns 499).
warm_up_ollama_in_cluster() {
    if ! kubectl get deployment ollama -n "$NAMESPACE" >/dev/null 2>&1; then return 0; fi
    if ! command -v curl >/dev/null 2>&1; then
        warn "curl not found; skipping Ollama warm-up. Chat may be slow on first use (model load)."
        return 0
    fi
    local host_port=11435
    log "Loading primary model so Chat is ready (may take 1–3 min on CPU; do not interrupt)..."
    kubectl port-forward -n "$NAMESPACE" "svc/ollama" "${host_port}:11434" >/dev/null 2>&1 &
    local pf_pid=$!
    sleep 5
    if ! kill -0 "$pf_pid" 2>/dev/null; then
        warn "Port-forward failed; skipping warm-up."
        return 0
    fi
    if curl -s -X POST "http://127.0.0.1:${host_port}/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$OLLAMA_PRIMARY_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false}" \
        --max-time 600 >/dev/null 2>&1; then
        ok "Ollama warm-up done ($OLLAMA_PRIMARY_MODEL)."
    else
        warn "Warm-up request failed or timed out. Chat may still work after first load."
    fi
    kill "$pf_pid" 2>/dev/null; wait "$pf_pid" 2>/dev/null; true
}

# ── Local run: GPU-first on this machine (embedding + pipeline use MPS/CUDA) ─
if [[ -n "$LOCAL_RUN" ]] && [[ "$ACTION" == "deploy" ]]; then
    log "Local run: GPU-first. App and pipeline on this machine; embedding uses MPS (Mac) or CUDA when available."
    export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-auto}"
    PYTHON="${PYTHON:-python3}"
    VENV="$ROOT/.venv"
    if [[ ! -d "$VENV" ]]; then
        log "Creating venv and installing dependencies..."
        "$PYTHON" -m venv "$VENV"
        "$VENV/bin/pip" install --upgrade pip
        if [[ "$(uname -s)" = "Darwin" ]]; then
            "$VENV/bin/pip" install 'torch>=2.0.0' --force-reinstall
        fi
        "$VENV/bin/pip" install -r requirements.txt
        ok "Venv ready."
    else
        if [[ "$(uname -s)" = "Darwin" ]]; then
            log "Ensuring PyTorch MPS (Apple Silicon)..."
            "$VENV/bin/pip" install 'torch>=2.0.0' --force-reinstall -q 2>/dev/null || true
        fi
    fi
    log "Ensuring embedding model is cached (downloads once if missing)..."
    if PIPELINE_SERVICE_URL= PYTHONPATH="$ROOT" "$VENV/bin/python" -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('all-MiniLM-L6-v2')
"; then
        ok "Embedding model ready (cached or downloaded)."
    else
        warn "Could not cache embedding model (network?). Pipeline will try to download when you run it."
    fi
    pull_ollama_models
    echo ""
    ok "Starting app at http://localhost:$STREAMLIT_PORT — GPU-first (embedding + pipeline use MPS/CUDA where available)."
    echo "  Chat: Ollama (localhost:11434) or LM Studio (set Playground in Config Center)."
    echo "  Stop with Ctrl+C. Re-run ./deploy.sh --local anytime."
    echo ""
    # 256 is typically faster than 512 on M-series: 512 can cause memory pressure or throttling.
    EMBEDDING_BATCH_SIZE=256 PIPELINE_SERVICE_URL= PIPELINE_API_PREFIX= PYTHONPATH="$ROOT" "$VENV/bin/streamlit" run ui/Home.py --server.port "$STREAMLIT_PORT" --server.headless true
    exit 0
fi

# ── Rancher Desktop: ensure docker and kubectl are on PATH ─────────────────
if [[ -d "${HOME}/.rd/bin" ]]; then
    export PATH="${HOME}/.rd/bin:${PATH}"
fi

# ── Preflight ─────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || fail "docker not found. Is Rancher Desktop running? Add: export PATH=\"\$HOME/.rd/bin:\$PATH\""
docker info >/dev/null 2>&1     || fail "Docker daemon not reachable. Start Rancher Desktop first."
command -v kubectl >/dev/null 2>&1 || fail "kubectl not found. Install Kubernetes in Rancher Desktop and add ~/.rd/bin to PATH."

# ── Down: full teardown ────────────────────────────────────────────────────
if [[ "$ACTION" == "down" ]]; then
    log "Tearing down MORISLEX-RAG (namespace: $NAMESPACE)..."
    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        kubectl delete -k "$KUSTOMIZE_DIR" --ignore-not-found --timeout=90s 2>/dev/null || true
        kubectl delete namespace "$NAMESPACE" --ignore-not-found --wait --timeout=120s 2>/dev/null || true
        ok "Namespace and all resources removed."
    else
        ok "Namespace $NAMESPACE does not exist; nothing to remove."
    fi
    exit 0
fi

# ── Status ─────────────────────────────────────────────────────────────────
if [[ "$ACTION" == "status" ]]; then
    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        kubectl get pods,svc,pvc -n "$NAMESPACE" 2>/dev/null || true
        echo ""
        log "To access the UI: kubectl port-forward -n $NAMESPACE svc/morislex-rag-ui 8502:8502"
        log "Then open http://localhost:8502"
    else
        warn "Namespace $NAMESPACE does not exist. Run ./deploy.sh to deploy."
    fi
    exit 0
fi

# ── Logs (diagnose why pod exited) ──────────────────────────────────────────
if [[ "$ACTION" == "logs" ]]; then
    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        if [[ -n "$LOG_PREVIOUS" ]]; then
            log "Logs from the last (exited) container:"
            kubectl logs -n "$NAMESPACE" -l app=morislex-rag $LOG_PREVIOUS --tail=200 2>/dev/null || warn "No previous logs (pod may not have exited yet)."
        else
            kubectl logs -n "$NAMESPACE" -l app=morislex-rag -f --tail=100 2>/dev/null || true
        fi
        echo ""
        log "To see why the pod exited: kubectl describe pod -n $NAMESPACE -l app=morislex-rag (check Last State / Reason)"
        log "Or: ./deploy.sh --logs --previous"
    else
        warn "Namespace $NAMESPACE does not exist."
    fi
    exit 0
fi

# ── Build image (installs all dependencies from requirements.txt) ───────────
[ -f requirements.txt ] || fail "requirements.txt not found. Run from MORISLEX-RAG repo root."
log "Building Docker image $IMAGE_NAME (installing all dependencies)..."
docker build $NO_CACHE -t "$IMAGE_NAME" .
ok "Image built."

# ── Ensure namespace exists (idempotent) ───────────────────────────────────
if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
    log "Creating namespace $NAMESPACE..."
    kubectl create namespace "$NAMESPACE"
    ok "Namespace created."
fi

# ── Apply manifests ────────────────────────────────────────────────────────
if [[ -n "$USE_HOST_STATE" ]]; then
    log "Applying manifests ($KUSTOMIZE_DIR) — host state, configs, logs, Engine data (no re-index); compute in-cluster."
else
    log "Applying manifests ($KUSTOMIZE_DIR) — prod: pure K8s (PVC state; run pipeline in UI to index)."
fi
kubectl apply -k "$KUSTOMIZE_DIR"
ok "Manifests applied."

# ── Force rollout restart so new image is used on redeploy ──────────────────
log "Restarting UI, Pipeline, and Retrieval deployments to use new image..."
for dep in morislex-rag-ui morislex-rag-pipeline morislex-rag-retrieval; do
    if kubectl get deployment "$dep" -n "$NAMESPACE" >/dev/null 2>&1; then
        kubectl rollout restart deployment/"$dep" -n "$NAMESPACE"
        ok "Restarted $dep."
    fi
done

# ── Wait for rollouts ───────────────────────────────────────────────────────
log "Waiting for UI, Pipeline, Retrieval, and Ollama deployments..."
kubectl rollout status deployment/morislex-rag-ui -n "$NAMESPACE" --timeout=180s 2>/dev/null && ok "UI is ready." || warn "UI rollout wait timed out."
if kubectl rollout status deployment/morislex-rag-pipeline -n "$NAMESPACE" --timeout=120s 2>/dev/null; then
    ok "Pipeline worker is ready."
else
    warn "Pipeline rollout wait timed out. Check: kubectl get pods -n $NAMESPACE -l component=pipeline; kubectl describe pod -n $NAMESPACE -l component=pipeline"
fi
if kubectl rollout status deployment/morislex-rag-retrieval -n "$NAMESPACE" --timeout=180s 2>/dev/null; then
    ok "Retrieval service is ready."
else
    warn "Retrieval rollout wait timed out. Check: kubectl get pods -n $NAMESPACE -l component=retrieval; kubectl describe pod -n $NAMESPACE -l component=retrieval"
fi
OLLAMA_READY=0
if kubectl get deployment ollama -n "$NAMESPACE" >/dev/null 2>&1; then
    if kubectl rollout status deployment/ollama -n "$NAMESPACE" --timeout=600s 2>/dev/null; then
        ok "Ollama is ready."
        pull_ollama_models_in_cluster
        warm_up_ollama_in_cluster
        OLLAMA_READY=1
    else
        warn "Ollama rollout wait timed out. Chat may fail until Ollama is ready."
        warn "If the Ollama pod is Pending: kubectl describe pod -n $NAMESPACE -l component=ollama (see Events: often 'Insufficient memory' — give the node more RAM or reduce Ollama resources in k8s/base/ollama-deployment.yaml)."
        warn "If the pod is Running: kubectl exec -n $NAMESPACE deploy/ollama -- ollama pull qwen2.5:3b"
    fi
fi

echo ""
if [[ -n "$USE_HOST_STATE" ]]; then
    ok "MORISLEX-RAG deployed (K8s + host state). Leverages host: state, configs, logs, Engine data (no re-index). Compute in-cluster (CPU)."
else
    ok "MORISLEX-RAG deployed (K8s prod). Pure cluster resources; run pipeline in UI to index, or use --use-host-state to reuse local index."
fi
echo ""
if [[ "$OLLAMA_READY" -eq 1 ]]; then
    log "LLM (Chat): In-cluster Ollama (models pulled and primary loaded). For host LM Studio set Playground in Config Center."
    log "Primary model loaded; Chat is ready. Starting port-forward (Ctrl+C to stop)."
else
    log "LLM (Chat): Ollama did not become ready in time; Chat may fail until the Ollama pod is up. For host LM Studio set Playground in Config Center."
    log "Starting port-forward (Ctrl+C to stop)."
fi
echo -e "${GREEN}  Streamlit UI: http://localhost:${STREAMLIT_PORT}${NC}"
# LoadBalancer fallback (avoids port-forward timeouts on Rancher Desktop)
LB_IP=$(kubectl get svc morislex-rag-ui-lb -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
if [[ -n "$LB_IP" ]]; then
    LB_PORT=$(kubectl get svc morislex-rag-ui-lb -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
    echo -e "${GREEN}  Or (no port-forward): http://${LB_IP}:${LB_PORT:-8502}${NC}"
fi
log "If you see 'Timeout occurred' from port-forward, use the LoadBalancer URL above."
echo ""
# Brief wait so UI pod Streamlit is listening after rollout (avoids Connection refused on first forward)
sleep 3
trap 'echo ""; log "Stopped."; exit 0' INT TERM
while true; do
    kubectl port-forward -n "$NAMESPACE" svc/morislex-rag-ui "$STREAMLIT_PORT:8502" 2>&1 || true
    warn "Port-forward disconnected (pod may be restarting). Reconnecting in 5s..."
    sleep 5
done
