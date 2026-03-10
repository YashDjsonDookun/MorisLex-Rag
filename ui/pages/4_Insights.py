"""Insights: corpus stats, index stats, retrieval test."""
import os
import streamlit as st
from app.core.config import get_config
from app.core.vector_store import count as vector_count
from app.core.ingest import load_documents

st.title("Insights")
config = get_config()
data_dir = config.get_data_directory()
retrieval_url = os.environ.get("RETRIEVAL_SERVICE_URL", "").rstrip("/")

# Corpus stats
st.subheader("Corpus")
if data_dir:
    docs = load_documents(data_dir)
    st.metric("Documents (from ingest)", len(docs))
else:
    st.info("Set data folder in Config Center to see corpus stats.")

# Index stats
st.subheader("Index")
try:
    n = vector_count()
    st.metric("Chunks indexed", n)
except Exception as e:
    st.metric("Chunks indexed", "—")
    st.caption(str(e))

# Retrieval test
st.subheader("Retrieval test")
st.caption("Enter a query to see top chunks (no LLM).")
q = st.text_input("Query", placeholder="e.g. data protection")
top_k = st.slider("Top K", min_value=1, max_value=20, value=3)
if q and q.strip():
    try:
        if retrieval_url:
            import requests
            r = requests.post(
                f"{retrieval_url}/retrieve",
                json={"query": q.strip(), "top_k": top_k},
                timeout=60,
            )
            r.raise_for_status()
            chunks = r.json().get("chunks", [])
        else:
            from app.core.retriever import retrieve
            raw = retrieve(q.strip(), top_k=top_k)
            chunks = [c.model_dump() for c in raw]
        for i, c in enumerate(chunks):
            score = c.get("score", 0)
            doc_uid = c.get("document_uid", "")
            text = c.get("text", "")
            with st.expander(f"Chunk {i+1} (score {score:.3f}) — {doc_uid}"):
                st.text(text[:500] + ("..." if len(text) > 500 else ""))
        if not chunks:
            st.info("No chunks found. Run the pipeline first.")
    except Exception as e:
        st.error(str(e))
