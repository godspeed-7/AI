"""The AMS agent in the browser: sign in, ask, see each step.

In:  uv run streamlit run app.py (after load_data.py), then open
     http://localhost:8501 and sign in with the 4 digits of an ID
     (AMS-1015 -> 1015).
Out: a chat for the signed-in employee; under each question, the
     agent's steps as they finish (the tool it asked for, the tool's
     result), then the answer.

Strategy: sign-in puts the employee and their context (ID and roles,
context.py) in st.session_state; every question first passes the
request limits (limits.py: length, and questions a minute per person),
then runs the agent with that context, never one from the chat
(inside the agent, the topic guard runs first). stream_mode="updates"
gives one event per finished step. The chat's messages stay in the
session and go with each question, so follow-ups work.

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
from ams_agent.budget import stopped_by
from ams_agent.config import MAX_MESSAGE_CHARS, MAX_QUESTIONS_PER_MINUTE
from ams_agent.context import context_for, role_names
from ams_agent.db import find_employee
from ams_agent.limits import RateLimiter, too_long
from ams_agent.output_check import is_check_reply
from ams_agent.topic_guard import is_guard_reply


@st.cache_resource
def agent():
    """Built once and shared: it keeps no per-user state."""
    return build_agent()


@st.cache_resource
def limiter() -> RateLimiter:
    """One for the whole server, so every tab of a person shares it."""
    return RateLimiter(MAX_QUESTIONS_PER_MINUTE)


def refused(question: str, employee_id: str) -> str | None:
    """Why a question is stopped before the agent (walk 3), or None."""
    if reason := too_long(question):
        return reason
    if seconds := limiter().wait(employee_id):
        return (f"You've asked {MAX_QUESTIONS_PER_MINUTE} questions in the"
                f" last minute; please wait {seconds:.0f} seconds.")
    return None


def steps_of(message) -> list[str]:
    """What one new message shows as steps, in markdown."""
    if is_guard_reply(message):
        return ["🚧 Topic check: off-topic, so a fixed reply (no agent run)"]
    if reason := stopped_by(message):
        return [f"⛔ Budget: the {reason} budget ran out, so a fixed reply"]
    if is_check_reply(message):
        return [("🛡️ Output check: the answer quoted the instructions,"
                 " so it was replaced")]
    if isinstance(message, AIMessage) and message.tool_calls:
        return [f"🛠️ Model asks for `{call['name']}` {call['args'] or ''}"
                for call in message.tool_calls]
    if isinstance(message, ToolMessage):
        return [(f"📄 `{message.name}` returned:\n```json\n"
                 f"{message.text[:1500]}\n```")]
    if isinstance(message, AIMessage) and message.text.strip():
        return ["✍️ Model writes the answer"]
    return []


def merged(messages: list, updates: list) -> list:
    """Add new messages; one with a known ID replaces that message (as
    the output check does), so a leaked answer is never kept."""
    ids = {m.id: i for i, m in enumerate(messages) if m.id}
    merged_list = list(messages)
    for m in updates:
        if m.id in ids:
            merged_list[ids[m.id]] = m
        else:
            merged_list.append(m)
    return merged_list


def read_update(node: str, change) -> tuple[list, list[str]]:
    """One streamed update -> its new messages and the steps to show."""
    if node.startswith("TopicGuard") and not change:
        return [], ["✅ Topic check: on-topic"]  # let through: no message
    messages = change.get("messages", []) if isinstance(change, dict) else []
    return messages, [step for m in messages for step in steps_of(m)]


def sign_in_screen() -> None:
    st.title("AMS HR assistant")
    st.caption("Dev-only sign-in: an employee ID, no password.")
    with st.form("sign_in"):
        st.markdown("**Employee ID**")
        prefix, box = st.columns([1, 6], vertical_alignment="center")
        prefix.markdown("**AMS-**")  # fixed: only the 4 digits are typed
        digits = box.text_input("Employee ID", max_chars=4,
                                placeholder="1015",
                                label_visibility="collapsed").strip()
        if not st.form_submit_button("Sign in"):  # or press Enter
            return
    if not (len(digits) == 4 and digits.isdigit()):
        st.error("Enter the 4 digits of your employee ID, e.g. 1015.")
        return
    person = find_employee(f"AMS-{digits}")
    if not person:
        st.error(f"No employee with the ID AMS-{digits}.")
        return
    # The ID and roles every question runs with, set once, by code.
    st.session_state.update(person=person,
                            context=context_for(person["employee_id"]),
                            messages=[], turns=[])
    st.rerun()


def ask(question: str) -> None:
    """Run the agent on one question, showing each step as it ends."""
    sent = st.session_state.messages + [HumanMessage(question)]
    new, steps = [], []
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.status("Working…", expanded=True) as status:
            try:
                for update in agent().stream(
                        {"messages": sent},
                        context=st.session_state.context,
                        stream_mode="updates"):
                    for node, change in update.items():
                        messages, found = read_update(node, change)
                        new = merged(new, messages)
                        steps.extend(found)
                        for step in found:
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
        st.caption("Roles: "
                   + ", ".join(role_names(st.session_state.context)))
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
    question = st.chat_input("Ask about your HR records",
                             max_chars=MAX_MESSAGE_CHARS)
    if not question:
        return
    if reason := refused(question, person["employee_id"]):
        with st.chat_message("user"):
            st.markdown(question[:300])
        st.warning(reason)
        return
    ask(question)


if "person" in st.session_state:
    chat_screen()
else:
    sign_in_screen()
