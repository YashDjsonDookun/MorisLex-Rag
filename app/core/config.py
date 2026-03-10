"""Load YAML config with .env overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, model_validator
from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG_PATH = _ROOT / "configs" / "app.yaml"


class ProjectConfig(BaseModel):
    name: str = "MorisLex-RAG"
    display_name: str = "Mauritius Legal RAG"
    version: str = "0.1.0"


class PathsConfig(BaseModel):
    data_dir: str = "./data"
    state_dir: str = "./state"
    logs_dir: str = "./logs"
    configs_dir: str = "./configs"


class IngestConfig(BaseModel):
    data_directory: str = ""
    manifest_file: str = "rag_manifest.csv"
    chunking_file: str = "for_chunking.csv"
    metadata_dir: str = "metadata"


class ChunkingConfig(BaseModel):
    strategy: str = "by_heading"
    chunk_size: int = 512
    overlap: int = 64
    respect_headers: bool = True


class EmbeddingConfig(BaseModel):
    provider: str = "sentence-transformers"
    model: str = "all-MiniLM-L6-v2"
    device: str = "cpu"
    batch_size: int = 128  # Chunks per batch. On GPU 256 is often fastest; 512 can be slower (memory/throttling on Mac). CPU: 128.


class VectorStoreConfig(BaseModel):
    type: str = "chroma"
    path: str = "./state/chroma_db"
    collection_name: str = "morislex"


class RetrievalConfig(BaseModel):
    top_k: int = 5
    min_score: float = 0.0


class LLMModelsConfig(BaseModel):
    """Model tier names (Ollama model tags)."""
    primary: str = "qwen2.5:3b"
    fallback: str = "qwen2.5:0.5b"
    comparison: str = "llama3.2:1b"


class LLMParametersConfig(BaseModel):
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 2048


class LLMPlaygroundConfig(BaseModel):
    """Optional LM Studio endpoint for Mac playground (dev only)."""
    base_url: str = ""
    model: str = ""


class LLMConfig(BaseModel):
    runtime: str = "ollama"
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "llama3"  # legacy single model; use models.primary when active_tier is used
    models: LLMModelsConfig = LLMModelsConfig()
    parameters: LLMParametersConfig = LLMParametersConfig()
    active_tier: str = "primary"  # primary | fallback | comparison (paywall-ready)
    strict_local: bool = True  # validate base_url is local; reject public URLs
    playground: LLMPlaygroundConfig = LLMPlaygroundConfig()
    # Legacy fields (used when parameters not set)
    temperature: float = 0.2
    max_tokens: int = 1024

    @model_validator(mode="before")
    @classmethod
    def _legacy_model_to_tiers(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "models" not in data and "model" in data:
            data = {**data, "models": {"primary": data["model"], "fallback": "qwen2.5:0.5b", "comparison": "llama3.2:1b"}}
        if "parameters" not in data:
            data = {
                **data,
                "parameters": {
                    "temperature": data.get("temperature", 0.2),
                    "top_p": data.get("top_p", 0.9),
                    "max_tokens": data.get("max_tokens", 2048),
                },
            }
        return data

    def get_model_for_tier(self, tier: str) -> str:
        """Resolve model name for tier (primary, fallback, comparison)."""
        t = (tier or self.active_tier or "primary").strip().lower()
        if t == "primary":
            return self.models.primary
        if t == "fallback":
            return self.models.fallback
        if t == "comparison":
            return self.models.comparison
        return self.models.primary

    @property
    def active_model(self) -> str:
        """Current model for default tier (backward compat)."""
        return self.get_model_for_tier(self.active_tier)

    def is_base_url_local(self) -> bool:
        """True if base_url is considered local (no internet). Used when strict_local=True."""
        url = (self.base_url or "").strip().lower()
        if not url:
            return False
        if "localhost" in url or "127.0.0.1" in url:
            return True
        if "host.docker.internal" in url:
            return True
        if url.startswith("http://ollama") or ".ollama." in url:
            return True
        return False


class WatchdogConfig(BaseModel):
    enabled: bool = False
    auto_reindex: bool = False


class AppConfig(BaseModel):
    project: ProjectConfig = ProjectConfig()
    paths: PathsConfig = PathsConfig()
    ingest: IngestConfig = IngestConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    vector_store: VectorStoreConfig = VectorStoreConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    llm: LLMConfig = LLMConfig()
    watchdog: WatchdogConfig = WatchdogConfig()

    def get_data_directory(self) -> str:
        """Resolve data directory: .env DATA_DIR > ingest.data_directory."""
        env_dir = os.environ.get("DATA_DIR", "").strip()
        if env_dir:
            return env_dir
        return self.ingest.data_directory or ""

    def resolve_path(self, rel: str) -> Path:
        return (_ROOT / rel).resolve()

    @property
    def state_path(self) -> Path:
        return self.resolve_path(self.paths.state_dir)

    @property
    def logs_path(self) -> Path:
        return self.resolve_path(self.paths.logs_dir)


_config: AppConfig | None = None


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load config from YAML and apply .env overrides."""
    global _config
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not config_path.is_absolute():
        config_path = _ROOT / config_path
    if not config_path.exists():
        _config = AppConfig()
        _apply_env_overrides(_config)
        return _config
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _config = AppConfig(**data)
    _apply_env_overrides(_config)
    return _config


def _apply_env_overrides(c: AppConfig) -> None:
    if os.environ.get("DATA_DIR"):
        c.ingest.data_directory = os.environ["DATA_DIR"]
    if os.environ.get("LLM_BASE_URL"):
        c.llm.base_url = os.environ["LLM_BASE_URL"]
    if os.environ.get("LLM_MODEL"):
        c.llm.model = os.environ["LLM_MODEL"]
    if os.environ.get("LLM_ACTIVE_TIER"):
        t = os.environ["LLM_ACTIVE_TIER"].strip().lower()
        if t in ("primary", "fallback", "comparison"):
            c.llm.active_tier = t
    if os.environ.get("LLM_STRICT_LOCAL", "").strip().lower() in ("0", "false", "no"):
        c.llm.strict_local = False
    if os.environ.get("LLM_PLAYGROUND_BASE_URL"):
        c.llm.playground.base_url = os.environ["LLM_PLAYGROUND_BASE_URL"].strip()
    if os.environ.get("LLM_PLAYGROUND_MODEL"):
        c.llm.playground.model = os.environ["LLM_PLAYGROUND_MODEL"].strip()
    if os.environ.get("EMBEDDING_DEVICE"):
        c.embedding.device = os.environ["EMBEDDING_DEVICE"].strip().lower()
    try:
        if os.environ.get("EMBEDDING_BATCH_SIZE"):
            c.embedding.batch_size = max(1, int(os.environ["EMBEDDING_BATCH_SIZE"]))
    except (ValueError, TypeError):
        pass


def get_config() -> AppConfig:
    """Return cached config; load from default path if not yet loaded."""
    global _config
    if _config is None:
        load_config()
    assert _config is not None
    return _config
