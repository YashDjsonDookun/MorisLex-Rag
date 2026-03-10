# MORISLEX-RAG — Vision

**Obsidian:** This note is in **01 - Projects/MorisLex Rag**. Index: [[index]]. Engine: [[01 - Projects/MorisLex Engine/vision-and-plan|Engine vision]].

---

MORISLEX-RAG is a **configurable, manual-first** RAG system for Mauritian legal content. It reads from a single **configurable data directory** (typically MorisLex-Engine exports), runs ingest → chunk → embed → index, and exposes retrieval and chat as **callable functions** (wrapper-ready for REST API or MCP later).

## Principles

- **v1: plain Python** — No LangChain, no MCP. Add later only if needed.
- **Configurable data path** — User can point to Engine data or any copy; change anytime via Config Center or .env.
- **Manual pipeline** — No auto-run unless watchdog is enabled and user opts in.
- **Streamlit IHM** — Dashboard, Pipeline, Config Center, Insights, Chat, Logs (mirror Engine UX).
- **Local LLM first** — Ollama or LM Studio for chat; retrieval works without LLM.

## Data flow

Configurable data dir → Ingest (manifest + for_chunking + metadata) → Chunk → Embed → Chroma → Retrieve / Chat.
