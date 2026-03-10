"""Config Center: data path, chunking, embedding, vector store, LLM, watchdog."""
import streamlit as st
from pathlib import Path
import yaml
from app.core.config import get_config, load_config
from ui.components.dir_picker import directory_picker

st.title("Config Center")
config = get_config()
root = Path(__file__).resolve().parent.parent.parent
config_path = root / "configs" / "app.yaml"

# Data directory with picker
st.caption("Data folder: use an absolute path the app can read, or a path relative to the app's working directory.")
data_dir = directory_picker(
    config.get_data_directory() or "",
    session_state_key="config_data_directory",
    browse_state_key="config_browse_path",
)
# Chunking
st.subheader("Chunking")
chunk_strategy = st.selectbox("Strategy", ["fixed", "by_heading", "hybrid"], index=["fixed", "by_heading", "hybrid"].index(config.chunking.strategy) if config.chunking.strategy in ["fixed", "by_heading", "hybrid"] else 1)
chunk_size = st.number_input("Chunk size", min_value=64, max_value=2048, value=config.chunking.chunk_size)
chunk_overlap = st.number_input("Overlap", min_value=0, max_value=512, value=config.chunking.overlap)
# Embedding
st.subheader("Embedding")
emb_provider = st.text_input("Provider", value=config.embedding.provider)
emb_model = st.text_input("Model", value=config.embedding.model)
try:
    from app.core.embedder import get_embedding_device
    effective_device = get_embedding_device()
    device_label = {"cpu": "CPU", "cuda": "NVIDIA GPU", "mps": "Apple Silicon (MPS)"}.get(effective_device, effective_device)
    st.caption(f"**Effective device:** {device_label} — pipeline and retrieval use this for embedding.")
except Exception:
    st.caption("Effective device: (unable to detect)")
# Vector store
st.subheader("Vector store")
vs_path = st.text_input("Index path", value=config.vector_store.path)
vs_collection = st.text_input("Collection name", value=config.vector_store.collection_name)
# Retrieval
st.subheader("Retrieval")
top_k = st.number_input("Top K", min_value=1, max_value=20, value=config.retrieval.top_k)
# LLM
st.subheader("LLM")
llm_base = st.text_input("LLM base URL", value=config.llm.base_url, help="e.g. http://localhost:11434 for Ollama")
tier_options = ["primary", "fallback", "comparison"]
tier_labels = {"primary": "Primary", "fallback": "Fallback", "comparison": "Comparison"}
tier_index = tier_options.index(config.llm.active_tier) if config.llm.active_tier in tier_options else 0
active_tier = st.selectbox(
    "Default model tier",
    options=tier_options,
    format_func=lambda x: f"{tier_labels[x]} — {config.llm.get_model_for_tier(x)}",
    index=tier_index,
    help="Primary = best for RAG; Fallback = fast; Comparison = for experiments. Paywall can restrict tier by plan.",
)
st.caption(f"Primary: {config.llm.models.primary} · Fallback: {config.llm.models.fallback} · Comparison: {config.llm.models.comparison}")
llm_model_primary = st.text_input("Primary model", value=config.llm.models.primary, help="e.g. qwen2.5:3b")
llm_model_fallback = st.text_input("Fallback model", value=config.llm.models.fallback, help="e.g. qwen2.5:0.5b")
llm_model_comparison = st.text_input("Comparison model", value=config.llm.models.comparison, help="e.g. llama3.2:1b")
llm_temperature = st.number_input("Temperature", min_value=0.0, max_value=2.0, value=config.llm.parameters.temperature, step=0.1)
llm_max_tokens = st.number_input("Max tokens", min_value=256, max_value=8192, value=config.llm.parameters.max_tokens)
strict_local = st.checkbox("Strict local (reject non-local LLM URL)", value=config.llm.strict_local, help="When enabled, only localhost / host.docker.internal / in-cluster Ollama are allowed.")
st.subheader("Playground (LM Studio, Mac)")
st.caption("Optional: use LM Studio on your Mac for testing other models. Leave empty for production.")
playground_base = st.text_input("Playground base URL", value=config.llm.playground.base_url or "", placeholder="e.g. http://host.docker.internal:1234")
playground_model = st.text_input("Playground model", value=config.llm.playground.model or "", placeholder="e.g. llama3.2:1b")
# Watchdog
st.subheader("Watchdog")
watchdog_enabled = st.checkbox("Enable watchdog", value=config.watchdog.enabled)
watchdog_auto = st.checkbox("Auto-reindex on new data", value=config.watchdog.auto_reindex)

if st.button("Save config"):
    data = {
        "project": {"name": config.project.name, "display_name": config.project.display_name, "version": config.project.version},
        "paths": {"data_dir": config.paths.data_dir, "state_dir": config.paths.state_dir, "logs_dir": config.paths.logs_dir, "configs_dir": config.paths.configs_dir},
        "ingest": {"data_directory": data_dir or "", "manifest_file": config.ingest.manifest_file, "chunking_file": config.ingest.chunking_file, "metadata_dir": config.ingest.metadata_dir},
        "chunking": {"strategy": chunk_strategy, "chunk_size": chunk_size, "overlap": chunk_overlap, "respect_headers": config.chunking.respect_headers},
        "embedding": {"provider": emb_provider, "model": emb_model, "device": config.embedding.device},
        "vector_store": {"type": config.vector_store.type, "path": vs_path, "collection_name": vs_collection},
        "retrieval": {"top_k": top_k, "min_score": config.retrieval.min_score},
        "llm": {
            "runtime": config.llm.runtime,
            "provider": config.llm.provider,
            "base_url": llm_base,
            "model": llm_model_primary,
            "models": {"primary": llm_model_primary, "fallback": llm_model_fallback, "comparison": llm_model_comparison},
            "parameters": {"temperature": llm_temperature, "top_p": config.llm.parameters.top_p, "max_tokens": llm_max_tokens},
            "active_tier": active_tier,
            "strict_local": strict_local,
            "playground": {"base_url": (playground_base or "").strip(), "model": (playground_model or "").strip()},
            "temperature": llm_temperature,
            "max_tokens": llm_max_tokens,
        },
        "watchdog": {"enabled": watchdog_enabled, "auto_reindex": watchdog_auto},
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
    load_config(config_path)
    st.success("Config saved. Reload the app or re-run pipeline to apply.")
