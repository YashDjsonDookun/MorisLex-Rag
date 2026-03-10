# MORISLEX-RAG — Implementation & Operations (summary)

**Obsidian:** **01 - Projects/MorisLex Rag**. Index: [[index]]. Architecture: [[ARCHITECTURE-RAG]]. Runbook: [[DEPLOYMENT-RUNBOOK]]. Full guide: [[MORISLEX-RAG-IMPLEMENTATION-AND-OPS]]. Engine: [[01 - Projects/MorisLex Engine/documentation-map|Engine docs]].

This note is a short summary. The full implementation and ops guide is **MORISLEX-RAG-IMPLEMENTATION-AND-OPS** (same folder in Obsidian; in repo: `MorisLex-Engine/docs/MORISLEX-RAG-IMPLEMENTATION-AND-OPS.md`). Run `make sync-blueprints-to-obsidian` to push RAG docs and blueprints to **01 - Projects/MorisLex Rag**.

---

## Quick summary

| Topic | Summary |
|-------|--------|
| **Pods** | UI (8502), Pipeline (8080), Retrieval (8082), Ollama (11434). Retrieval calls in-cluster Ollama for Chat. |
| **Incremental indexing** | `state/indexed_docs.json` tracks indexed docs by `content_hash`. Only new/changed docs are processed unless you do a full rebuild. |
| **Embeddings** | Offline (HF_HUB_OFFLINE=1). Model pre-downloaded in Dockerfile and in `./deploy.sh --local`. Fallback: retry once with network if cache missing. |
| **GPU (MPS)** | Containers are Linux → no MPS. Use `./deploy.sh --local` on Mac to run pipeline on host with MPS. Batch size 256 for local. |
| **Deploy** | `./deploy.sh` = build, K8s apply, rollouts, in-cluster Ollama pull + warm-up, port-forward. `./deploy.sh --local` = venv + pipeline in-process (GPU). |
| **Access UI** | After `./deploy.sh`: http://localhost:8502. If stopped: `kubectl port-forward -n morislex-rag svc/morislex-rag-ui 8502:8502`. See [[DEPLOYMENT-RUNBOOK]]. |
| **Ollama in-cluster** | Models pulled and primary warmed up by deploy; retrieval uses 600s read timeout. |
| **NetworkPolicy** | Default deny egress; same-namespace + DNS; Ollama egress for registry. |
| **Retrieval API** | [[RETRIEVAL-API]] — POST /retrieve, /chat, model_tier, X-API-Key (paywall-ready). |
| **Chroma** | Clear collection in batches of 500 to avoid SQLite “too many SQL variables”. |
| **Pipeline UI** | Fixed-height scrollable console, ETA in progress, live progress when you return to the Pipeline page. |
| **Troubleshooting** | [[problems-and-fixes]] — Ollama 499, retrieval CrashLoopBackOff, Pending Ollama. [[DEPLOYMENT-RUNBOOK]]. |

See the full doc in Engine/docs (or Obsidian after sync) for file paths, config, and detailed troubleshooting.
