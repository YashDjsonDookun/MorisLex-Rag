# MORISLEX-RAG — venv, dev, deploy, sync to Obsidian
SHELL := /bin/sh
VENV := .venv
PY := $(VENV)/bin/python
RAG_ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# Engine repo: sibling of RAG repo by default
ENGINE_ROOT ?= $(RAG_ROOT)../MorisLex-Engine
# Obsidian vault root (must contain "01 - Projects/MorisLex Rag")
OBSIDIAN_VAULT ?=
OBSIDIAN_RAG_FOLDER := 01 - Projects/MorisLex Rag

.PHONY: help install venv dev-ui test ollama-pull logs sync-blueprints-to-obsidian sync-blueprints-to-engine

help:
	@echo "MORISLEX-RAG targets:"
	@echo "  install                   Install all dependencies (.venv + pip install -r requirements.txt)"
	@echo "  venv                      Same as install"
	@echo "  dev-ui                    Run Streamlit UI (port 8502)"
	@echo "  test                      Run pytest"
	@echo "  ollama-pull               Pull default Ollama models (qwen2.5:3b, qwen2.5:0.5b, llama3.2:1b) on this machine"
	@echo "  logs                      Show retrieval + Ollama logs (K8s; use after Chat 500 or connection errors)"
	@echo "  sync-blueprints-to-obsidian   Push RAG docs + Engine RAG blueprints to Obsidian (set OBSIDIAN_VAULT)"
	@echo "  sync-blueprints-to-engine     Pull from Obsidian back to Engine and RAG docs (set OBSIDIAN_VAULT)"

install venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	@echo "All dependencies installed. Run: make dev-ui or ./deploy.sh --local"

dev-ui:
	$(VENV)/bin/streamlit run ui/Home.py --server.port=8502

test:
	$(PY) -m pytest tests/ -v

# ── K8s: fetch error logs (retrieval + Ollama) ─
logs:
	@echo "=== Retrieval (last 60 lines) ==="
	@kubectl logs -n morislex-rag -l component=retrieval --tail=60 2>/dev/null || echo "kubectl not available or no retrieval pods"
	@echo ""
	@echo "=== Ollama (last 60 lines) ==="
	@kubectl logs -n morislex-rag -l component=ollama --tail=60 2>/dev/null || echo "kubectl not available or no ollama pods"

# ── Ollama (run on the host where Ollama runs, e.g. your Mac) ─
ollama-pull:
	@echo "Pulling default RAG models (run where Ollama is running, e.g. your Mac)..."
	ollama pull qwen2.5:3b
	ollama pull qwen2.5:0.5b
	ollama pull llama3.2:1b
	@echo "Done. Primary: qwen2.5:3b, fallback: qwen2.5:0.5b, comparison: llama3.2:1b"

# ── Obsidian sync ─────────────────────────────────────────────
# Push: RAG docs/ + Engine RAG blueprints → OBSIDIAN_VAULT/01 - Projects/MorisLex Rag
sync-blueprints-to-obsidian:
	@if [ -z "$(OBSIDIAN_VAULT)" ]; then \
		echo "Set OBSIDIAN_VAULT to your Obsidian vault root (e.g. export OBSIDIAN_VAULT=~/Documents/Obsidian)"; exit 1; \
	fi
	@DEST="$(OBSIDIAN_VAULT)/$(OBSIDIAN_RAG_FOLDER)" && \
	mkdir -p "$$DEST" && \
	echo "Copying RAG docs to $$DEST ..." && \
	for f in "$(RAG_ROOT)docs/"*.md; do [ -f "$$f" ] && cp "$$f" "$$DEST/"; done && \
	echo "Copying Engine RAG blueprints to $$DEST ..." && \
	cp "$(ENGINE_ROOT)/docs/MORISLEX-RAG-BLUEPRINT.md" "$(ENGINE_ROOT)/docs/MORISLEX-RAG-IMPLEMENTATION-AND-OPS.md" "$(ENGINE_ROOT)/docs/MORISLEX-RAG_Blueprint_for_Cursor.md" "$$DEST/" 2>/dev/null || true && \
	echo "Done. Obsidian folder: $$DEST"

# Pull: OBSIDIAN_VAULT/01 - Projects/MorisLex Rag → RAG docs/ and Engine docs/
sync-blueprints-to-engine:
	@if [ -z "$(OBSIDIAN_VAULT)" ]; then \
		echo "Set OBSIDIAN_VAULT to your Obsidian vault root"; exit 1; \
	fi
	@SRC="$(OBSIDIAN_VAULT)/$(OBSIDIAN_RAG_FOLDER)" && \
	[ -d "$$SRC" ] || { echo "Folder not found: $$SRC"; exit 1; } && \
	echo "Copying from $$SRC to RAG docs/ ..." && \
	for f in "$$SRC"/*.md; do [ -f "$$f" ] && cp "$$f" "$(RAG_ROOT)docs/"; done && \
	echo "Copying Engine blueprints from $$SRC to Engine docs/ ..." && \
	cp "$$SRC/MORISLEX-RAG-BLUEPRINT.md" "$$SRC/MORISLEX-RAG-IMPLEMENTATION-AND-OPS.md" "$$SRC/MORISLEX-RAG_Blueprint_for_Cursor.md" "$(ENGINE_ROOT)/docs/" 2>/dev/null || true && \
	echo "Done."
