import os
from pathlib import Path

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parent
APP_TITLE = "VinmecAI Chat Demo"
INITIAL_MESSAGE = (
    "Chào bạn, bạn có khỏe không?\n\n"
    "Mình có thể hỗ trợ bạn tư vấn chuyên khoa, tìm cơ sở gần nhất và gợi ý lịch trình khám."
)
SAMPLE_PROMPTS = [
    "Tôi bị đau họng và sốt nhẹ 2 ngày nay.",
    "Cơ sở nào gần VinUni nhất?",
]


def bootstrap_environment() -> None:
    try:
        secret_api_key = st.secrets.get("OPENAI_API_KEY", "")
        if secret_api_key and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = secret_api_key
    except Exception:
        pass  # chạy local, dùng .env thay thế


@st.cache_resource(show_spinner=False)
def load_graph():
    bootstrap_environment()
    os.chdir(ROOT_DIR)
    from agent import graph

    return graph


def reset_chat() -> None:
    st.session_state.ui_messages = [
        {"role": "assistant", "content": INITIAL_MESSAGE},
    ]
    st.session_state.agent_messages = []


def ensure_session_state() -> None:
    if "ui_messages" not in st.session_state or "agent_messages" not in st.session_state:
        reset_chat()


def ask_agent(user_input: str) -> str:
    graph = load_graph()
    history = st.session_state.agent_messages
    result = graph.invoke({"messages": history + [("human", user_input)]})
    st.session_state.agent_messages = result["messages"]

    final_message = result["messages"][-1]
    return getattr(final_message, "content", str(final_message))


def render_sidebar() -> None:
    with st.sidebar:
        if st.button("Xóa lịch sử chat", use_container_width=True):
            reset_chat()
            st.rerun()

        st.divider()
        st.subheader("Gợi ý câu hỏi")
        for index, prompt in enumerate(SAMPLE_PROMPTS):
            if st.button(prompt, key=f"sample-{index}", use_container_width=True):
                st.session_state.pending_prompt = prompt


def render_history() -> None:
    for message in st.session_state.ui_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def handle_prompt(prompt: str) -> None:
    st.session_state.ui_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("VinmecAI đang trả lời..."):
            try:
                answer = ask_agent(prompt)
            except Exception as exc:
                answer = (
                    "Không thể gọi Agent lúc này. "
                    "Bạn kiểm tra API_Key và thử lại.\n\n"
                    f"Chi tiết: `{exc}`"
                )
        st.markdown(answer)

    st.session_state.ui_messages.append({"role": "assistant", "content": answer})


st.set_page_config(page_title=APP_TITLE, layout="centered")
bootstrap_environment()
ensure_session_state()

st.title(APP_TITLE)
st.caption("AI Booking Assistant.")

render_sidebar()
render_history()

pending_prompt = st.session_state.pop("pending_prompt", None)
chat_prompt = st.chat_input("Nhập câu hỏi của bạn...")
prompt = pending_prompt or chat_prompt

if prompt:
    handle_prompt(prompt)
