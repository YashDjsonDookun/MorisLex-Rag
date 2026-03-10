# MORISLEX-RAG

Mauritius Legal RAG: ingest, chunk, embed, index, retrieve, and chat over Mauritian legal content. Data is read from a **configurable data directory** (typically [MorisLex-Engine](https://github.com/your-org/MorisLex-Engine) exports).

## Quick start

1. **Configure data directory**  
   Point to the Engine data folder (or a copy). In the UI: **Config Center** → Data folder. Or set `ingest.data_directory` in `configs/app.yaml`, or `DATA_DIR` in `.env`.

2. **Run the pipeline**  
   **Pipeline** page → choose data path (if needed) → **Run full pipeline** (Ingest → Chunk → Embed → Index).

3. **Chat**  
   **Chat** page → ask a question. Ensure a local LLM is running (Ollama or LM Studio) and configured in Config Center.

## Requirements

- Python 3.11+
- Optional: Ollama or LM Studio for chat (retrieval works without LLM)

## Setup

```bash
make venv      # create .venv and install deps
source .venv/bin/activate  # or: . .venv/bin/activate
make dev-ui     # run Streamlit on port 8502
```

## Run with GPU (Apple Silicon)

To use your M‑series Mac’s GPU (MPS) for **much faster** embedding, run the app **on your Mac** with the pipeline in-process (no worker pod):

```bash
make dev-ui-gpu
# or: ./scripts/run_with_gpu.sh
```

Then open http://localhost:8502 → **Pipeline** → **Run full pipeline**. You should see “Using Apple Silicon (MPS)” and batches of 256. If you run the app from Rancher Desktop (K8s), the pipeline runs in a Linux container and uses CPU only.

## Data contract (Engine)

The RAG reads from a single configurable data directory containing:

- `rag_manifest.csv` (or under `exports/`)
- `for_chunking.csv` (or under `exports/`)
- `metadata/doc_<uid>.json`
- Extracted `.md` files (paths in CSVs; resolved relative to the data directory)

See [MorisLex-Engine](https://github.com/your-org/MorisLex-Engine) and `docs/` for the full blueprint and decisions.

## Deploy to Rancher Desktop

With [Rancher Desktop](https://rancherdesktop.io/) running (Kubernetes enabled) and `~/.rd/bin` in your PATH:

```bash
./deploy.sh              # build image, deploy, then start port-forward (one command; open http://localhost:8502)
./deploy.sh --local      # run on this machine with pipeline in-process (uses GPU on Mac)
./deploy.sh --status     # show pods and services
./deploy.sh --down       # tear down (delete namespace and resources)
./kill.sh                # full kill switch: stop and delete all containers/resources
```

After `./deploy.sh`, port-forward runs in the foreground; open http://localhost:8502 (Ctrl+C stops only the port-forward, not the pods).

**Microservices:** Three pods — **UI** (Streamlit, 8502), **Pipeline worker** (8080, runs ingest → chunk → embed → index), **Retrieval** (8082, Insights + Chat). UI calls pipeline and retrieval over HTTP so queries don’t load the pipeline pod.

**Using your Mac's data when running on Rancher Desktop:**  
Both pods mount your Engine data at `/data` (hostPath in `k8s/base/ui-deployment.yaml` and `pipeline-deployment.yaml`). Default path is `/Users/djson/Desktop/MorisLex-Engine/data`. In the RAG UI, set **Data folder** to **`/data`**, validate, then run the pipeline. To use a different path, edit `hostPath.path` in both deployment files and redeploy.

**Embedding speed (Apple Silicon):** Containers in Rancher Desktop run **Linux**; Apple’s GPU (MPS) is **macOS-only** and is not available inside those containers. So the pipeline in K8s will always use **CPU** for embedding and can be slow (e.g. hours for large corpora). To use your M4 GPU: run the pipeline **on the host** (Mac) instead of in a container — e.g. run the app with `PIPELINE_SERVICE_URL` unset so the pipeline runs in-process when you click “Run full pipeline”, or run the pipeline worker natively on the Mac and point the UI at it.

**If you get "Documents: 0, Chunks: 0":** The UI will show a diagnostic (whether the path exists in the pipeline pod and if `for_chunking.csv` was found). The pipeline runs in a **separate pod**; that pod must see your data at the path you set. To inspect what the pipeline pod sees, port-forward the **pipeline** service (not the UI). Use a **different local port** (e.g. 8081) so you don't hit the UI by mistake:
```bash
kubectl port-forward -n morislex-rag svc/morislex-rag-pipeline 8081:8080
```
Then open **http://localhost:8081/** — you should see `{"service": "morislex-rag-pipeline", ...}`. If you see "Not Found" or a Streamlit page, you were forwarding the UI; the pipeline is on port **8080** inside the cluster, so the command above maps it to **8081** on your machine. Then open **http://localhost:8081/check-path?path=/data** for the path diagnostic.

## Retrieval API (third-party integrations)

The **retrieval service** (port 8082) exposes:

- **POST /retrieve** — query + top_k → chunks (no LLM)
- **POST /chat** — question + top_k (+ optional `model_tier`, `stream`) → answer + sources

Model tiers: `primary` (best), `fallback` (fast), `comparison` (experiments). Optional **X-Model-Tier** and **X-API-Key** headers (paywall-ready). All answers are **context-only** (no internet). See **`docs/RETRIEVAL-API.md`** for request/response shapes and examples.

## Documentation

- **Architecture:** `docs/ARCHITECTURE-RAG.md` — K8s topology, Ollama, data flow, Mermaid diagrams.
- **Deployment runbook:** `docs/DEPLOYMENT-RUNBOOK.md` — deploy steps, access UI, troubleshooting flowchart.
- **Retrieval API:** `docs/RETRIEVAL-API.md` — /retrieve, /chat, model tiers, strict local, paywall-ready headers.
- **Problems and fixes:** `docs/problems-and-fixes.md` — Ollama 499, retrieval CrashLoopBackOff, Pending Ollama, rollout timeouts.
- **Full implementation & operations:** `docs/IMPLEMENTATION-AND-OPS.md` (summary) and **MorisLex-Engine/docs/MORISLEX-RAG-IMPLEMENTATION-AND-OPS.md** (complete guide: incremental indexing, local embeddings, GPU/MPS, deploy.sh, troubleshooting).
- **Sync to Obsidian:** `make sync-blueprints-to-obsidian` copies into **01 - Projects/MorisLex Rag**: (1) RAG blueprints from Engine/docs, (2) this repo’s **docs/** (`index.md`, `vision.md`, `decisions.md`, `problems-and-fixes.md`, `IMPLEMENTATION-AND-OPS.md`, `RETRIEVAL-API.md`). Those notes use Obsidian links to each other and to **01 - Projects/MorisLex Engine**. `make sync-blueprints-to-engine` pulls from Obsidian back to Engine/docs and to this repo’s docs/.

## Project structure

- `app/core/` — config, ingest, chunker, embedder, vector_store, retriever, pipeline
- `app/llm/` — LLMService, Ollama/LM Studio client, strict legal RAG prompts, model tiers (primary/fallback/comparison)
- `app/models/` — Document, Chunk, etc.
- `ui/` — Streamlit Home + pages (Dashboard, Pipeline, Config Center, Insights, Chat, Logs)
- `configs/app.yaml` — main config (data path, chunking, embedding, LLM, watchdog)
- `state/` — Chroma DB, pipeline state, run_control

## License

Same as MorisLex-Engine.
