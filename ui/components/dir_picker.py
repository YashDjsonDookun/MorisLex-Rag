"""Server-side directory picker: browse folders and set the data path."""
from __future__ import annotations

from pathlib import Path
import streamlit as st


def _safe_list_dirs(p: Path) -> list[Path]:
    try:
        return [x for x in p.iterdir() if x.is_dir() and not x.name.startswith(".")]
    except (PermissionError, OSError):
        return []


def directory_picker(
    current_path: str,
    session_state_key: str = "data_directory",
    browse_state_key: str = "browse_current_path",
    start_from_home: bool = True,
) -> str:
    """
    Render a text input plus a "Browse" expander to pick a folder.
    Returns the chosen path (from text input or from "Use this folder").
    Store only strings in session_state so navigation persists across reruns.
    """
    key_prefix = session_state_key.replace("_", "")
    # Persist chosen path (string only so Streamlit keeps it across reruns)
    if session_state_key not in st.session_state:
        st.session_state[session_state_key] = (current_path or "").strip()
    if browse_state_key not in st.session_state:
        start = Path(current_path).expanduser() if current_path else (Path.home() if start_from_home else Path.cwd())
        try:
            p = start.resolve() if start.exists() else Path.home()
            st.session_state[browse_state_key] = str(p)
        except Exception:
            st.session_state[browse_state_key] = str(Path.home())

    # Text input: show and edit path
    path_value = st.text_input(
        "Data folder",
        value=st.session_state[session_state_key],
        key=f"{key_prefix}_input",
        help="Type a path or use 'Browse' below to select a folder. Must contain for_chunking.csv (or exports/for_chunking.csv).",
    )
    if path_value is not None and path_value.strip() != st.session_state.get(session_state_key):
        st.session_state[session_state_key] = path_value.strip()

    # Browse expander: always work with string in session_state, convert to Path for ops
    with st.expander("Browse for folder", expanded=True):
        browse_path_str = st.session_state[browse_state_key]
        try:
            browse_path = Path(browse_path_str).expanduser().resolve()
            if not browse_path.is_dir():
                browse_path = Path.home()
                browse_path_str = str(browse_path)
                st.session_state[browse_state_key] = browse_path_str
        except Exception:
            browse_path = Path.home()
            browse_path_str = str(browse_path)
            st.session_state[browse_state_key] = browse_path_str

        st.caption(f"Current: `{browse_path}`")

        col_up, col_use, _ = st.columns([1, 1, 2])
        with col_up:
            parent = browse_path.parent
            if parent != browse_path and st.button("↑ Up", key=f"{key_prefix}_up"):
                st.session_state[browse_state_key] = str(parent)
                st.rerun()
        with col_use:
            if st.button("Use this folder", key=f"{key_prefix}_use"):
                st.session_state[session_state_key] = str(browse_path)
                st.rerun()

        dirs = sorted(_safe_list_dirs(browse_path), key=lambda x: x.name.lower())
        if not dirs:
            st.caption("No subdirectories here (or no permission).")
        else:
            for i, d in enumerate(dirs[:50]):
                if st.button(f"📁 {d.name}", key=f"{key_prefix}_d_{i}"):
                    st.session_state[browse_state_key] = str(d)
                    st.rerun()
            if len(dirs) > 50:
                st.caption(f"... and {len(dirs) - 50} more. Type the path manually or navigate.")

    return st.session_state[session_state_key]
