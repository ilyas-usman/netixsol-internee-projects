"""
Run (with the API already running separately):
    uvicorn api:app --reload --port 8000      # in one terminal
    streamlit run streamlit_app.py             # in another
"""
import uuid
import requests
import streamlit as st
API_URL = "http://localhost:8000/chat"
st.set_page_config(page_title="AFL Chat Assistant", page_icon="🏉")
st.title("🏉 AFL Domain-Scoped Chat Assistant")
st.caption(
    "Ask about AFL teams, players, matches, stats, rules, history, or "
    "get a match-outcome prediction. Anything outside AFL will be declined."
)

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = f"streamlit-{uuid.uuid4().hex[:8]}"
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.subheader("Session")
    st.text(f"conversation_id:\n{st.session_state.conversation_id}")
    if st.button("Start new conversation"):
        st.session_state.conversation_id = f"streamlit-{uuid.uuid4().hex[:8]}"
        st.session_state.messages = []
        st.rerun()
    st.divider()
    st.subheader("API")
    st.text_input("API URL", value=API_URL, key="api_url_display", disabled=True)
    show_meta = st.checkbox("Show tool-call / grounding metadata", value=False)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if show_meta and msg["role"] == "assistant" and msg.get("meta"):
            st.caption(
                f"tools: {msg['meta']['tools_called']} | "
                f"grounded: {msg['meta']['grounded']} | "
                f"latency: {msg['meta']['latency_ms']:.0f}ms"
            )

user_input = st.chat_input("Ask an AFL question...")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(
                    API_URL,
                    json={
                        "message": user_input,
                        "conversation_id": st.session_state.conversation_id,
                    },
                    timeout=35,
                )
                if resp.status_code == 429:
                    answer = "Rate limit reached — please wait a moment before asking again."
                    meta = {}
                elif resp.status_code != 200:
                    answer = f"API error ({resp.status_code}): {resp.text}"
                    meta = {}
                else:
                    data = resp.json()
                    answer = data["response"]
                    meta = {
                        "tools_called": data["tools_called"],
                        "grounded": data["grounded"],
                        "latency_ms": data["latency_ms"],
                    }
            except requests.exceptions.ConnectionError:
                answer = (
                    "Couldn't reach the API — make sure it's running: "
                    "`uvicorn api:app --reload --port 8000`"
                )
                meta = {}
            except requests.exceptions.Timeout:
                answer = "The request took too long and timed out. Please try again."
                meta = {}

        st.markdown(answer)
        if show_meta and meta:
            st.caption(
                f"tools: {meta['tools_called']} | grounded: {meta['grounded']} | "
                f"latency: {meta['latency_ms']:.0f}ms"
            )

    st.session_state.messages.append({"role": "assistant", "content": answer, "meta": meta})
