# Run MORISLEX-RAG with the LLM

**Obsidian:** **01 - Projects/MorisLex Rag**. Index: [[index]].

Short walkthrough to run the project and use Chat with a local LLM (Ollama or LM Studio).

---

## 1. Prerequisites: local LLM

**Option A — Ollama (recommended)**

- Install [Ollama](https://ollama.com) and start it (e.g. open the app or `ollama serve`).
- Pull the default models (run on the **same machine** where Ollama runs, e.g. your Mac):
  ```bash
  make ollama-pull
  ```
  or manually:
  ```bash
  ollama pull qwen2.5:3b
  ollama pull qwen2.5:0.5b
  ollama pull llama3.2:1b
  ```
- If you don’t pull these, the app will get 500 or “model not found” when calling `/chat`.

**Option B — LM Studio (Mac playground)**

- Install [LM Studio](https://lmstudio.ai), open it, download a model, and start the local server.
- In Config Center set **Playground** base URL (e.g. `http://localhost:1234`) and model; then on the Chat page use **Use Playground (LM Studio)** to test that model.

---

## 2. Data and pipeline (one-time or when data changes)

- **Data directory:** Point the app at your Engine exports (folder that contains `for_chunking.csv`, `rag_manifest.csv`, `metadata/`, and the extracted `.md` paths). In the UI: **Config Center** → Data folder. Or set `DATA_DIR` in `.env` or `ingest.data_directory` in `configs/app.yaml`.
- **Run the pipeline:** Open the **Pipeline** page → set/confirm data path → click **Run full pipeline** (Ingest → Chunk → Embed → Index). Wait until it finishes so the vector index is built.

---

## 3. Run the app

**On your Mac (recommended for first run; uses GPU for embedding if available):**

```bash
cd /path/to/MorisLex-Rag
./deploy.sh --local
```

- Creates/uses `.venv`, caches the embedding model, starts Streamlit.
- Open **http://localhost:8502**.

**Or with Make:**

```bash
make venv
source .venv/bin/activate   # or: . .venv/bin/activate
make dev-ui
```

Then open **http://localhost:8502**.

**On Rancher Desktop (K8s):** `./deploy.sh` (build, deploy, port-forward). Open http://localhost:8502. **Default:** in-cluster Ollama is deployed and models are pulled inside the cluster by the script, so Chat works without any host LLM. Use `--no-pull-models` to skip (e.g. if you use LM Studio only).

**Reuse your local index in containers (no re-index):** If you already indexed on the Mac with `./deploy.sh --local` and want the same 505k+ chunks when running in K8s, use `./deploy.sh --use-host-state`. That overlay mounts your Mac’s `MorisLex-Rag` repo (state, configs, logs) into the pods so they see the same Chroma DB. Edit the path in `k8s/overlays/use-host-state/*.yaml` if your repo lives elsewhere.

**K8s + Ollama on the Mac (optional):** To use Ollama on your host instead of in-cluster, set **LLM base URL** in Config Center to `http://host.docker.internal:11434` and ensure models are pulled on the Mac (`make ollama-pull`).

---

## 4. LLM config (defaults usually work)

- **Config Center** → **LLM**:
  - **LLM base URL:** `http://localhost:11434` for local run; in K8s retrieval uses `http://ollama:11434` by default (set via ConfigMap).
  - **Default model tier:** Primary (uses `qwen2.5:3b` by default).
  - **Strict local** is on by default (only local/in-cluster URLs allowed).
- Save if you change anything.

---

## 5. Use Chat

- Go to **Chat**.
- Choose **Model tier** (Primary / Fallback / Comparison) if you want to switch.
- Optionally enable **Use Playground (LM Studio)** if you configured a playground and want to test that model.
- Type a question → **Ask**. The app retrieves chunks, sends them to the LLM with a strict “answer only from context” prompt, and shows the answer and sources.

If the LLM doesn’t respond, check that Ollama (or LM Studio) is running and that the base URL in Config Center matches (e.g. `http://localhost:11434` for Ollama on the same machine).
