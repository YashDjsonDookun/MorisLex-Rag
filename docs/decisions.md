# MORISLEX-RAG — Decisions

**Obsidian:** **01 - Projects/MorisLex Rag**. Index: [[index]]. Engine: [[01 - Projects/MorisLex Engine/decisions|Engine decisions]].

| Decision | Rationale |
|----------|-----------|
| v1: no LangChain | Plain Python unless a concrete problem requires it; add later for multiple retrievers/agents/MCP. |
| v1: no MCP | Design retrieval/chat as callable functions so they can be wrapped as APIs or MCP tools in v2/v3. |
| Configurable data directory | User may move Engine data; multiple projects may share one engine. |
| Manual pipeline trigger | User controls when indexing runs. |
| Watchdog optional, off by default | Some users want “reindex on new data”; others want full manual control. |
| Chroma as default vector store | Simple, persistent, good for local; easy to replace later. |
| Streamlit IHM like Engine | Consistency; non-technical users get same UX patterns. |
| Local LLM first | Matches Engine’s local-first approach; LM Studio/Ollama on Mac. |
