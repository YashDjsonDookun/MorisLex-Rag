# MORISLEX-RAG — Documentation index

**In this project (01 - Projects/MorisLex Rag):**
- [[ARCHITECTURE-RAG|Architecture]] — K8s topology, Ollama, data flow, diagrams
- [[DEPLOYMENT-RUNBOOK|Deployment runbook]] — deploy steps, access UI, troubleshooting
- [[vision|Vision and plan]]
- [[decisions|Decisions]]
- [[problems-and-fixes|Problems and fixes]] — Ollama 499, retrieval CrashLoopBackOff, Pending, rollout timeouts
- [[IMPLEMENTATION-AND-OPS|Implementation & operations]] — summary; full guide: [[MORISLEX-RAG-IMPLEMENTATION-AND-OPS]]
- [[RETRIEVAL-API|Retrieval API]] — POST /retrieve, /chat, model tiers, paywall-ready
- [[MORISLEX-RAG-BLUEPRINT|Blueprint]] · [[MORISLEX-RAG_Blueprint_for_Cursor|Blueprint for Cursor]]

**MorisLex Engine (links to other project):**
- [[01 - Projects/MorisLex Engine/documentation-map|Documentation map]]
- [[01 - Projects/MorisLex Engine/ARCHITECTURE-MORISLEX|Engine architecture]]
- [[01 - Projects/MorisLex Engine/vision-and-plan|Vision and plan]]
- [[01 - Projects/MorisLex Engine/decisions|Decisions]]
- [[01 - Projects/MorisLex Engine/changelog|Changelog]]

**Sync:** From RAG repo set `OBSIDIAN_VAULT` to your vault root, then `make sync-blueprints-to-obsidian` (push) or `make sync-blueprints-to-engine` (pull). RAG `docs/*.md` (including ARCHITECTURE-RAG, DEPLOYMENT-RUNBOOK, RETRIEVAL-API) and Engine RAG blueprints live in **01 - Projects/MorisLex Rag**.
