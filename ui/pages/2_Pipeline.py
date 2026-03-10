"""Pipeline: data path, validate & show files, run full pipeline (worker or in-process)."""
import html
import os
import time
import streamlit as st
from pathlib import Path
from app.core.config import get_config
from app.core.ingest import load_documents, preflight
from ui.components.dir_picker import directory_picker

# Fixed-height scrollable console (px)
CONSOLE_HEIGHT_PX = 400


def _console_html(text: str) -> str:
    """Return HTML for a fixed-height scrollable console block (no vertical expansion)."""
    escaped = html.escape(text or "(no output)")
    return (
        f'<div style="max-height: {CONSOLE_HEIGHT_PX}px; overflow-y: auto; border: 1px solid rgba(49, 51, 63, 0.2); '
        "border-radius: 0.25rem; padding: 0.75rem 1rem; background: rgba(49, 51, 63, 0.15); "
        "font-family: ui-monospace, monospace; font-size: 13px; line-height: 1.4; white-space: pre;\">"
        f"{escaped}</div>"
    )

# When set (e.g. in K8s), UI calls the pipeline worker instead of running in-process
PIPELINE_SERVICE_URL = os.environ.get("PIPELINE_SERVICE_URL", "").rstrip("/")
PIPELINE_API_PREFIX = (os.environ.get("PIPELINE_API_PREFIX", "") or "").strip().rstrip("/")


def _pipeline_url(path: str) -> str:
    base = PIPELINE_SERVICE_URL
    if not base:
        return ""
    if PIPELINE_API_PREFIX:
        return f"{base}/{PIPELINE_API_PREFIX}/{path.lstrip('/')}"
    return f"{base}/{path.lstrip('/')}"


def _get_preflight(data_dir: str, max_files: int = 100, preview_chars: int = 400) -> dict | None:
    """Call preflight via worker or in-process."""
    if PIPELINE_SERVICE_URL:
        try:
            import requests
            r = requests.get(
                _pipeline_url("preflight"),
                params={"path": data_dir, "max_files": max_files, "preview_chars": preview_chars},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            st.error(f"Cannot reach pipeline worker: {e}. Is the pipeline pod running?")
            return None
    try:
        return preflight(data_dir, max_files=max_files, preview_chars=preview_chars)
    except Exception as e:
        st.error(f"Preflight failed: {e}")
        return None


st.title("Pipeline")
config = get_config()

# ── Data path ─────────────────────────────────────────────────────────────
with st.expander("Path help", expanded=False):
    cwd = os.getcwd()
    st.markdown("**What path to use:**")
    st.markdown(f"- **Absolute**: e.g. `{Path.home()}/Desktop/my-data` or `~/Desktop/my-data`.")
    st.markdown(f"- **Relative**: resolved from app cwd: `{cwd}`")
    st.markdown("In **Docker/K8s** use the path inside the container (e.g. `/data`). Mount your Engine data there.")
st.caption("Data folder (Engine data root: contains exports/ and extracted/)")
data_dir = directory_picker(
    config.get_data_directory() or "",
    session_state_key="pipeline_data_directory",
    browse_state_key="pipeline_browse_path",
)

# ── Validate & show files ──────────────────────────────────────────────────
st.subheader("Validate & show files")
st.caption("See exactly which files the pipeline will read: path, size, and content preview.")
if st.button("Validate & show files", type="secondary"):
    if not data_dir or not data_dir.strip():
        st.error("Enter a data path first.")
    else:
        with st.spinner("Discovering files…"):
            out = _get_preflight(data_dir.strip(), max_files=100, preview_chars=400)
        if out:
            diag = out.get("diagnostic", {})
            st.success(f"**Data dir:** `{out.get('data_dir', '?')}` · **Exists:** {diag.get('exists', False)} · **CSV found:** {diag.get('chunking_found', False)}")
            total = out.get("total_documents", 0)
            num_exist = out.get("num_files_exist", 0)
            num_missing = out.get("num_files_missing", 0)
            st.metric("Documents in CSV", total)
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Files that exist", num_exist)
            with col2:
                st.metric("Files missing", num_missing)
            if num_exist == 0 and total > 0:
                st.warning("No text files were found at the resolved paths. In K8s, ensure the pipeline pod has the same data mounted (e.g. at /data).")

            files = out.get("files", [])
            if files:
                st.subheader("File list (path, size, preview)")
                for i, f in enumerate(files):
                    with st.expander(f"{'✅' if f.get('exists') else '❌'} {f.get('path_short', '') or f.get('document_uid', '')} — {f.get('document_uid', '')}", expanded=(i < 3)):
                        st.text(f"Path: {f.get('path', '')}")
                        st.caption(f"Exists: {f.get('exists', False)} · Size: {f.get('size_bytes') or 0} bytes · {f.get('size_chars') or 0} chars")
                        if f.get("title"):
                            st.caption(f"Title: {f['title']}")
                        if f.get("preview"):
                            st.text_area("Content preview", value=f["preview"], height=120, key=f"preview_{f.get('document_uid', i)}")
            elif total == 0:
                st.info("No documents in for_chunking.csv. Generate the export from the Engine (RAG Readiness / Export).")

st.markdown("---")
st.subheader("Run full pipeline")

if PIPELINE_SERVICE_URL:
    st.info(
        "**Using pipeline worker** (runs in a separate pod → CPU only). "
        "To use your Mac's GPU (MPS) for faster embedding, run the app on your Mac with: **`make dev-ui-gpu`** "
        "then open Pipeline and run from there."
    )

# When using the worker: show live progress as soon as we open (or return to) this page if pipeline is running.
def _render_live_and_poll():
    import requests
    progress = st.empty()
    console_placeholder = st.empty()
    summary_holder = st.empty()
    try:
        s = requests.get(_pipeline_url("status"), timeout=5)
        s.raise_for_status()
        data = s.json()
    except requests.RequestException:
        progress.markdown("Pipeline status… (checking…)")
        time.sleep(2)
        return None
    while True:
        log_lines = data.get("log_lines", [])
        console_text = "\n".join(log_lines) if log_lines else "(waiting for output…)"
        console_placeholder.markdown(_console_html(console_text), unsafe_allow_html=True)
        if data.get("error"):
            progress.empty()
            summary_holder.error("Pipeline error: " + data["error"])
            return data
        if not data.get("running"):
            progress.empty()
            last = data.get("last_summary") or {}
            docs, chunks, idx = last.get("documents_loaded", 0), last.get("chunks_created", 0), last.get("indexed", 0)
            summary_holder.success(f"Done. Documents: {docs}, Chunks: {chunks}, Indexed: {idx}")
            if last.get("diagnostic"):
                diag = last["diagnostic"]
                lines = ["**Pipeline diagnostic:**"]
                lines.append(f"- Data dir: `{diag.get('data_dir', '?')}`")
                lines.append(f"- Data dir exists: {diag.get('data_dir_exists', diag.get('exists', '?'))}")
                lines.append(f"- for_chunking.csv: {diag.get('chunking_path', '?')} (found: {diag.get('chunking_found', diag.get('chunking_exists', '?'))})")
                if "num_documents_from_csv" in diag:
                    lines.append(f"- Documents from CSV: {diag['num_documents_from_csv']}")
                    lines.append(f"- Text files that exist: {diag.get('num_files_exist', '?')}")
                if diag.get("sample_resolved_paths"):
                    lines.append("- Sample resolved paths:")
                    for s in diag["sample_resolved_paths"][:5]:
                        lines.append(f"  - `{s.get('path', '')}` → exists: {s.get('exists', False)}")
                if diag.get("top_level"):
                    lines.append(f"- Top-level dirs: {diag.get('top_level', [])[:15]}")
                if diag.get("hint"):
                    lines.append(f"\n**Hint:** {diag['hint']}")
                st.warning("\n".join(lines))
            if last.get("errors"):
                st.warning("Errors: " + "; ".join(last["errors"]))
            st.session_state.pipeline_summary = last
            return data
        cur, tot = data.get("current", 0), data.get("total", 0) or 1
        msg = data.get("message", "")
        progress.progress(cur / tot, text=f"{data.get('phase', '')}: {cur}/{tot} — {msg}")
        time.sleep(2)
        try:
            s = requests.get(_pipeline_url("status"), timeout=5)
            s.raise_for_status()
            data = s.json()
        except requests.RequestException:
            continue

if PIPELINE_SERVICE_URL:
    try:
        import requests
        s = requests.get(_pipeline_url("status"), timeout=5)
        s.raise_for_status()
        data = s.json()
        if data.get("running"):
            st.info("Pipeline is running. Progress updates live below. You can switch pages and return; progress will resume here.")
            _render_live_and_poll()
    except Exception:
        pass

full_rebuild = st.checkbox("Full rebuild (clear index first)", value=True)

if st.button("Run full pipeline", type="primary"):
    if not data_dir or not data_dir.strip():
        st.error("Set a data folder first.")
        st.stop()
    _p = Path(data_dir.strip()).expanduser()
    try:
        _p = _p.resolve()
    except Exception:
        pass
    if not _p.exists() or not _p.is_dir():
        st.error(f"Data folder does not exist or is not a directory: `{_p}`. Validate & show files first.")
        st.stop()

    if PIPELINE_SERVICE_URL:
        payload_data_dir = (data_dir or "").strip() or config.get_data_directory() or ""
        if not payload_data_dir:
            st.error("Set a data folder path (e.g. /data in K8s).")
            st.stop()
        try:
            import requests
            r = requests.post(
                _pipeline_url("run-pipeline"),
                json={"data_directory": payload_data_dir, "full_rebuild": full_rebuild},
                timeout=10,
            )
            if r.status_code == 409:
                st.warning("Pipeline is already running. Wait for it to finish.")
                st.stop()
            r.raise_for_status()
        except requests.RequestException as e:
            st.error(f"Cannot reach pipeline worker at {PIPELINE_SERVICE_URL}: {e}")
            st.stop()
        st.rerun()
        st.stop()
    else:
        from app.core.pipeline import run_pipeline
        progress = st.empty()
        summary_holder = st.empty()
        if "pipeline_log" not in st.session_state:
            st.session_state.pipeline_log = []

        def on_progress(phase: str, current: int, total: int, message: str | None):
            total_str = str(total) if total else "?"
            line = f"[{phase}] {current}/{total_str} — {message or ''}".strip()
            if line:
                st.session_state.pipeline_log.append(line)
            progress.progress(current / total if total else 0.0, text=f"{phase}: {current}/{total_str} — {message or ''}")

        st.session_state.pipeline_log = []
        with st.spinner("Running pipeline..."):
            summary = run_pipeline(data_directory=data_dir, full_rebuild=full_rebuild, on_progress=on_progress)
        st.session_state.pipeline_summary = summary
        progress.empty()
        summary_holder.success(
            f"Done. Documents: {summary['documents_loaded']}, Chunks: {summary['chunks_created']}, Indexed: {summary['indexed']}"
        )
        if st.session_state.pipeline_log:
            st.caption("Pipeline log")
            st.markdown(_console_html("\n".join(st.session_state.pipeline_log)), unsafe_allow_html=True)
        if summary.get("errors"):
            st.warning("Errors: " + "; ".join(summary["errors"]))
        if summary.get("diagnostic"):
            st.warning("Diagnostic: " + str(summary["diagnostic"].get("hint", "")))
