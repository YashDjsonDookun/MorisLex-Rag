"""Chat: question input, RAG (retrieve + LLM), show answer and sources. Optional tier, playground, stream."""
import os
import streamlit as st
from app.core.config import get_config

st.title("Chat")
st.caption("Ask a question. RAG will retrieve relevant chunks and send them to the LLM. Configure LLM in Config Center (Ollama or LM Studio).")

config = get_config()
retrieval_url = os.environ.get("RETRIEVAL_SERVICE_URL", "").rstrip("/")
playground_available = bool(config.llm.playground.base_url and config.llm.playground.model)

question = st.text_area("Question", placeholder="e.g. What does the Data Protection Act say about consent?")
top_k = st.slider("Retrieval top K", min_value=1, max_value=20, value=5)

# Model tier (paywall-ready)
tier_options = ["primary", "fallback", "comparison"]
tier_labels = {"primary": "Primary", "fallback": "Fallback", "comparison": "Comparison"}
tier_index = tier_options.index(config.llm.active_tier) if config.llm.active_tier in tier_options else 0
model_tier = st.selectbox(
    "Model tier",
    options=tier_options,
    format_func=lambda x: f"{tier_labels[x]} — {config.llm.get_model_for_tier(x)}",
    index=tier_index,
    help="Primary = best; Fallback = fast; Comparison = experiments.",
)
use_playground = False
if playground_available:
    use_playground = st.checkbox("Use Playground (LM Studio)", value=False, help="Use LM Studio endpoint for testing other models (Mac).")

stream_response = st.checkbox("Stream response", value=False, help="Show answer as it is generated.")

if st.button("Ask"):
    if not question or not question.strip():
        st.warning("Enter a question.")
    else:
        with st.spinner("Retrieving and generating..."):
            try:
                if retrieval_url:
                    import requests
                    payload = {
                        "question": question.strip(),
                        "top_k": top_k,
                        "model_tier": model_tier,
                        "use_playground": use_playground,
                        "stream": stream_response,
                    }
                    if stream_response:
                        r = requests.post(
                            f"{retrieval_url}/chat",
                            json=payload,
                            timeout=300,
                            stream=True,
                        )
                        r.raise_for_status()
                        st.subheader("Answer")
                        placeholder = st.empty()
                        full = []
                        for chunk in r.iter_content(decode_unicode=True):
                            if chunk:
                                full.append(chunk)
                                placeholder.markdown("".join(full) + "▌")
                        placeholder.markdown("".join(full))
                        # Sources not returned in stream mode; show message
                        st.caption("Sources: run again without streaming to see citations.")
                    else:
                        r = requests.post(
                            f"{retrieval_url}/chat",
                            json=payload,
                            timeout=300,
                        )
                        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                        if r.status_code != 200:
                            err = data.get("error", r.text or f"HTTP {r.status_code}")
                            st.error(err)
                            if data.get("hint"):
                                st.info(data["hint"])
                            st.stop()
                        answer = data.get("answer", "")
                        sources = data.get("sources", [])
                        st.subheader("Answer")
                        st.write(answer)
                        st.subheader("Sources")
                        for i, s in enumerate(sources):
                            with st.expander(f"{s.get('title', s.get('document_uid', ''))}"):
                                st.text(s.get("text", ""))
                else:
                    from app.llm.client import chat
                    answer, sources = chat(
                        question.strip(),
                        top_k=top_k,
                        tier=model_tier,
                        use_playground=use_playground,
                    )
                    st.subheader("Answer")
                    st.write(answer)
                    st.subheader("Sources")
                    for i, s in enumerate(sources):
                        with st.expander(f"{s.get('title', s.get('document_uid', ''))}"):
                            st.text(s.get("text", ""))
                    if not answer and not sources:
                        st.info("RAG retrieval works. To get answers, start Ollama or LM Studio and set the model in Config Center.")
            except Exception as e:
                err = str(e)
                st.error(err)
                if "resolve" in err.lower() or "name resolution" in err.lower() or "nodename" in err.lower():
                    st.info(
                        "Retrieval hostname could not be resolved. If the UI is running **locally** (e.g. ./deploy.sh --local), "
                        "unset `RETRIEVAL_SERVICE_URL` so Chat uses in-process retrieval, or set it to `http://localhost:8082` "
                        "and run: `kubectl port-forward -n morislex-rag svc/morislex-rag-retrieval 8082:8082`"
                    )
                elif "remote end closed" in err.lower() or "connection aborted" in err.lower() or "remotedisconnected" in err.lower() or "response ended prematurely" in err.lower() or "prematurely" in err.lower():
                    st.info(
                        "The response was cut off—often because **Ollama was still loading the model**. "
                        "Wait 30–60 seconds, then try again. If it persists, check: "
                        "`kubectl logs -n morislex-rag -l component=retrieval --tail=50` and "
                        "`kubectl logs -n morislex-rag -l component=ollama --tail=50`."
                    )
                else:
                    st.info("If the error is about connection, ensure Ollama or LM Studio is running and the base URL is correct in Config Center.")
