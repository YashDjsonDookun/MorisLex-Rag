"""Logs: pipeline run output (from worker) and optional log files."""
import html
import os
import streamlit as st
from pathlib import Path

from app.core.config import get_config

st.title("Logs")
st.caption("Pipeline run output and log files. Use the Pipeline page to start a run.")

config = get_config()
PIPELINE_SERVICE_URL = os.environ.get("PIPELINE_SERVICE_URL", "").rstrip("/")
PIPELINE_API_PREFIX = (os.environ.get("PIPELINE_API_PREFIX", "") or "").strip().rstrip("/")
CONSOLE_HEIGHT_PX = 420


def _pipeline_url(path: str) -> str:
    if not PIPELINE_SERVICE_URL:
        return ""
    base = PIPELINE_SERVICE_URL.rstrip("/")
    if PIPELINE_API_PREFIX:
        return f"{base}/{PIPELINE_API_PREFIX.strip('/')}/{path.lstrip('/')}"
    return f"{base}/{path.lstrip('/')}"


def _console_html(text: str) -> str:
    escaped = html.escape(text or "(no output)")
    return (
        f'<div style="max-height: {CONSOLE_HEIGHT_PX}px; overflow-y: auto; border: 1px solid rgba(49, 51, 63, 0.2); '
        "border-radius: 0.25rem; padding: 0.75rem 1rem; background: rgba(49, 51, 63, 0.15); "
        "font-family: ui-monospace, monospace; font-size: 13px; line-height: 1.4; white-space: pre;\">"
        f"{escaped}</div>"
    )


# --- Pipeline run log (when using pipeline worker) ---
if PIPELINE_SERVICE_URL:
    st.subheader("Pipeline run log")
    st.caption("Output from the pipeline worker. Refresh to see latest; the Pipeline page shows live progress while a run is active.")
    if st.button("Refresh", key="logs_refresh"):
        st.rerun()
    try:
        import requests
        r = requests.get(_pipeline_url("status"), timeout=10)
        r.raise_for_status()
        data = r.json()
        log_lines = data.get("log_lines", [])
        running = data.get("running", False)
        if running:
            st.info("Pipeline is currently running. Progress is also shown on the Pipeline page.")
        console_text = "\n".join(log_lines) if log_lines else "(No output yet. Run the pipeline from the Pipeline page.)"
        if data.get("error"):
            st.error("Last error: " + data["error"])
        last = data.get("last_summary")
        if last and not running:
            docs, chunks, idx = last.get("documents_loaded", 0), last.get("chunks_created", 0), last.get("indexed", 0)
            st.caption(f"Last run: documents={docs} chunks={chunks} indexed={idx}")
        st.markdown(_console_html(console_text), unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Could not load pipeline status: {e}. Is the pipeline worker running?")
        st.markdown(_console_html("(Pipeline service unavailable.)"), unsafe_allow_html=True)
else:
    st.subheader("Pipeline run log")
    st.info("Running locally without a pipeline worker. Pipeline output appears on the **Pipeline** page when you run it.")

# --- Log files (if any) ---
st.subheader("Log files")
logs_path = config.logs_path
if not logs_path.exists():
    logs_path.mkdir(parents=True, exist_ok=True)
log_files = sorted(logs_path.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
if not log_files:
    st.caption("No log files in this directory yet. Pipeline output above is the main source of logs.")
else:
    selected = st.selectbox(
        "Log file",
        [f.name for f in log_files],
        index=0,
        key="logs_file_select",
    )
    max_lines = st.number_input("Tail (max lines)", min_value=100, max_value=20000, value=1000, key="logs_max_lines")
    search = st.text_input("Filter lines (optional)", placeholder="e.g. error, WARN", key="logs_search")
    log_file = logs_path / selected
    if log_file.exists():
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if search.strip():
            lines = [l for l in lines if search.strip().lower() in l.lower()]
        lines = lines[-max_lines:]
        st.text_area("Content", value="\n".join(lines), height=400, key="logs_content")
