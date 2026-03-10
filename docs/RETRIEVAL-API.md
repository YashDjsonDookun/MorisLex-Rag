# MORISLEX-RAG Retrieval API

**Obsidian:** **01 - Projects/MorisLex Rag**. Index: [[index]]. Implementation: [[IMPLEMENTATION-AND-OPS]].

Third-party apps (MORISLEX-UI, mobile, MCP, or other tools) can use RAG via the retrieval service HTTP API. All answers are **context-only** (no internet); the LLM is strictly local (Ollama or LM Studio).

## Base URL

- **In-cluster:** `http://morislex-rag-retrieval:8082` (namespace `morislex-rag`)
- **Local / port-forward:** `http://localhost:8082` (after `kubectl port-forward -n morislex-rag svc/morislex-rag-retrieval 8082:8082`)

## Endpoints

### Health

- **GET /health** — Returns `{"ok": true}`. Use for readiness/liveness.

### Retrieval (no LLM)

- **POST /retrieve**

  Returns top-k chunks for a query (no LLM call).

  **Request body (JSON):**

  | Field  | Type | Default | Description   |
  |--------|------|---------|---------------|
  | query  | str  | required | Search query |
  | top_k  | int  | 5       | Number of chunks |

  **Response:** `{"chunks": [{"document_uid", "version_id", "chunk_index", "text", "title", "top_level_class", "score", "id", ...}]}`

### RAG Chat

- **POST /chat**

  Retrieves chunks, builds a strict legal RAG prompt, calls the local LLM, returns answer and sources.

  **Request body (JSON):**

  | Field           | Type   | Default   | Description |
  |-----------------|--------|-----------|-------------|
  | question        | str    | required  | User question |
  | top_k           | int    | 5         | Retrieval top-k |
  | model_tier      | str    | (config)  | `primary` \| `fallback` \| `comparison` (paywall-ready: restrict by plan later) |
  | use_playground  | bool   | false     | Use LM Studio playground endpoint if configured |
  | stream          | bool   | false     | If true, response is `text/plain` stream of content (no JSON; no sources in body) |

  **Headers (optional):**

  | Header         | Description |
  |----------------|-------------|
  | X-Model-Tier   | Same as `model_tier` in body (e.g. `primary`, `fallback`, `comparison`) |
  | X-API-Key      | Reserved for future paywall; v1 no-op |

  **Response (non-stream):** `{"answer": "<text>", "sources": [{"text": "...", "document_uid": "...", "title": "..."}]}`

  **Response (stream=true):** `Content-Type: text/plain; charset=utf-8` — body is the raw answer text stream. Sources are not returned; run again without streaming to get citations.

## Model tiers (paywall-ready)

- **primary** — Best for RAG (e.g. qwen2.5:3b). Can be reserved for paying customers.
- **fallback** — Fast, lighter model (e.g. qwen2.5:0.5b).
- **comparison** — Alternative for experiments (e.g. llama3.2:1b).

Config sets default tier and model names. A future paywall layer can validate `X-API-Key` and restrict `model_tier` by subscription (e.g. free = fallback only, paid = primary).

## Strict local / no hallucination

- The LLM is configured to answer **only** from the provided context; it must not use external knowledge or the internet.
- In Kubernetes, a **NetworkPolicy** restricts retrieval pod egress to DNS and in-cluster Ollama (no internet).
- Set `llm.base_url` to a local endpoint (e.g. `http://localhost:11434`, `http://ollama:11434`, or `http://host.docker.internal:1234` for LM Studio on Mac).

## Example (curl)

```bash
# Retrieve only (no LLM)
curl -s -X POST http://localhost:8082/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "consent under Data Protection Act", "top_k": 5}'

# Chat (default tier)
curl -s -X POST http://localhost:8082/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What does the Data Protection Act say about consent?", "top_k": 5}'

# Chat with tier and optional API key (v1 no-op)
curl -s -X POST http://localhost:8082/chat \
  -H "Content-Type: application/json" \
  -H "X-Model-Tier: primary" \
  -H "X-API-Key: your-key" \
  -d '{"question": "What does the Data Protection Act say about consent?", "top_k": 5}'
```
