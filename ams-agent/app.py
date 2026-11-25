"""The AMS agent in the browser: sign in, ask, see each step.

In:  uv run streamlit run app.py (after load_data.py), then open
     http://localhost:8501 and sign in with an ID such as AMS-1015.
Out: a chat for the signed-in employee; under each question, the
     agent's steps as they finish (the tool it asked for, the tool's
     result), then the answer.

Strategy: sign-in puts the employee in st.session_state; every
question runs the agent with Context(employee_id) taken from there,
never from the chat. stream_mode="updates" gives one event per
finished step. The chat's messages stay in the session and go with
each question, so follow-ups work.

Caveats:
- DEV-ONLY sign-in: an ID box, no password, so anyone can be anyone.
  Production: st.login() with the company's OpenID Connect provider
  (SSO), and st.user's email mapped to the employee ID; the agent and
  tools don't change.
- A refresh signs you out (session_state lives per browser tab).
- The answer appears when it is complete (no word-by-word streaming).
- Answers are shown as markdown as is; guarding output comes later.
"""

import streamlit as st
from langchain.messages import AIMessage, HumanMessage, ToolMessage

from ams_agent.agent import build_agent, final_answer
from ams_agent.context import Context
from ams_agent.db import find_employee


@st.cache_resource
def agent():
    """Built once and shared: it keeps no per-user state."""
    return build_agent()


def steps_of(message) -> list[str]:
    """What one new message shows as steps, in markdown."""
    if isinstance(message, AIMessage) and message.tool_calls:
        return [f"🛠️ Model asks for `{call['name']}` {call['args'] or ''}"
                for call in message.tool_calls]
    if isinstance(message, ToolMessage):
        return [(f"📄 `{message.name}` returned:\n```json\n"
                 f"{message.text[:1500]}\n```")]
    if isinstance(message, AIMessage) and message.text.strip():
        return ["✍️ Model writes the answer"]
    return []


def sign_in_screen() -> None:
    st.title("AMS HR assistant")
    st.caption("Dev-only sign-in: an employee ID, no password.")
    with st.form("sign_in"):
        employee_id = st.text_input("Employee ID", placeholder="AMS-1015")
        if st.form_submit_button("Sign in"):
            person = find_employee(employee_id.strip().upper())
            if person:
                st.session_state.update(person=person, messages=[],
                                        turns=[])
                st.rerun()
            st.error(f"No employee with the ID {employee_id!r}.")


def ask(question: str) -> None:
    """Run the agent on one question, showing each step as it ends."""
    person = st.session_state.person
    sent = st.session_state.messages + [HumanMessage(question)]
    new, steps = [], []
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.status("Working…", expanded=True) as status:
            try:
                for update in agent().stream(
                        {"messages": sent},
                        context=Context(person["employee_id"]),
                        stream_mode="updates"):
                    for change in update.values():
                        if not isinstance(change, dict):
                            continue
                        for message in change.get("messages", []):
                            new.append(message)
                            for step in steps_of(message):
                                steps.append(step)
                                st.markdown(step)
            # Any failure: show it in the chat instead of crashing.
            except Exception as e:  # noqa: BLE001
                status.update(label="Failed", state="error")
                st.error(f"The agent failed: {type(e).__name__}")
                return
            status.update(label=f"{len(steps)} steps", state="complete",
                          expanded=False)
        answer = final_answer(new) or "Sorry, I couldn't answer that."
        st.markdown(answer)
    st.session_state.messages = sent + new
    st.session_state.turns.append(
        {"question": question, "steps": steps, "answer": answer})


def chat_screen() -> None:
    person = st.session_state.person
    with st.sidebar:
        st.markdown(f"**{person['name']}** ({person['employee_id']})")
        st.caption(f"{person['job_title']}, {person['grade']},"
                   f" {person['office']}")
        st.caption("Dev-only sign-in")
        if st.button("Sign out"):
            st.session_state.clear()
            st.rerun()
    st.title("AMS HR assistant")
    for turn in st.session_state.turns:
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant"):
            with st.expander(f"{len(turn['steps'])} steps"):
                for step in turn["steps"]:
                    st.markdown(step)
            st.markdown(turn["answer"])
    if question := st.chat_input("Ask about your HR records"):
        ask(question)


if "person" in st.session_state:
    chat_screen()
else:
    sign_in_screen()
