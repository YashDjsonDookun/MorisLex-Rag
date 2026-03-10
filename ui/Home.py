"""
MORISLEX-RAG — Streamlit IHM (port 8502).
Dashboard, Pipeline, Config Center, Insights, Chat, Logs.
"""
import sys
from pathlib import Path

# Ensure project root is on path (for Docker and any run context)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

st.set_page_config(
    page_title="Mauritius Legal RAG",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("Mauritius Legal RAG")
st.markdown("Ingest → Chunk → Embed → Index → Retrieve & Chat over Engine data.")
st.sidebar.markdown("### Pages")
st.sidebar.markdown("Use the sidebar or navigate to **Dashboard**, **Pipeline**, **Config Center**, **Insights**, **Chat**, or **Logs**.")
# State for pipeline progress (optional)
if "pipeline_summary" not in st.session_state:
    st.session_state.pipeline_summary = None
if "last_run_phase" not in st.session_state:
    st.session_state.last_run_phase = None
