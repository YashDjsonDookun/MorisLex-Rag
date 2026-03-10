"""Dashboard: status, index stats, quick actions."""
import streamlit as st
from app.core.config import get_config
from app.core.vector_store import count as vector_count

st.title("Dashboard")
config = get_config()
data_dir = config.get_data_directory() or "(not set)"

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Data folder", data_dir if len(data_dir) < 40 else data_dir[:37] + "...")
with col2:
    try:
        n = vector_count()
        st.metric("Chunks indexed", n)
    except Exception:
        st.metric("Chunks indexed", "—")
with col3:
    st.metric("Config", config.chunking.strategy)

st.markdown("---")
st.subheader("Quick actions")
c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Run pipeline", use_container_width=True):
        st.switch_page("pages/2_Pipeline.py")
with c2:
    if st.button("Open Chat", use_container_width=True):
        st.switch_page("pages/5_Chat.py")
with c3:
    if st.button("View Insights", use_container_width=True):
        st.switch_page("pages/4_Insights.py")

st.markdown("---")
if st.session_state.get("pipeline_summary"):
    st.subheader("Last pipeline run")
    st.json(st.session_state["pipeline_summary"])
st.caption("Change data folder in **Config Center**.")
