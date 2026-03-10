#!/usr/bin/env bash
# Kill switch: completely stop and remove MORISLEX-RAG from the cluster.
# Deletes the namespace and all resources in it (pods, services, PVC, config, etc.).
set -euo pipefail

cd "$(dirname "$0")"

RED='\033[0;31m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
NC='\033[0m'

log()  { echo -e "${CYAN}[kill]${NC} $1"; }
ok()   { echo -e "${GREEN}[  ok  ]${NC} $1"; }
fail() { echo -e "${RED}[FAIL  ]${NC} $1"; exit 1; }

NAMESPACE="morislex-rag"

# Rancher Desktop
if [[ -d "${HOME}/.rd/bin" ]]; then
    export PATH="${HOME}/.rd/bin:${PATH}"
fi

command -v kubectl >/dev/null 2>&1 || fail "kubectl not found. Is Rancher Desktop running?"

if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
    ok "Namespace $NAMESPACE does not exist. Nothing to kill."
    exit 0
fi

log "Deleting namespace $NAMESPACE (pods, services, PVC, config, etc.)..."
kubectl delete namespace "$NAMESPACE" --ignore-not-found --wait --timeout=180s
ok "Namespace and all MORISLEX-RAG resources removed."

log "Optional: remove the Docker image to free space: docker rmi morislex-rag:latest"
echo ""
ok "Kill complete. Run ./deploy.sh to deploy again."
