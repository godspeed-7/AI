"""The AMS agent in the browser: sign in, ask, see each step.

In:  uv run streamlit run app.py (after load_data.py), then open
     http://localhost:8501 and sign in with the 4 digits of an ID
     (AMS-1015 -> 1015).
Out: a chat for the signed-in employee; under each question, the
     agent's steps as they finish (the tool it asked for, the tool's
     result), then the answer.

Strategy: sign-in puts the employee, their context (ID and roles,
context.py) and their chat ID (memory.py) in st.session_state; every question
first passes the request limits (limits.py: length, and questions a
minute per person), then runs the agent with that context, never one
from the chat (inside the agent, the topic guard runs first). Only the
new message is sent: the agent's checkpointer keeps the chat under its
ID, so follow-ups work. stream_mode="updates" gives one event per
finished step. A booking pauses: the app shows the exact
action with Confirm / Cancel, and the click resumes the run.

Caveats:
- DEV-ONLY sign-in: an ID box, no password, so anyone can be anyone.
  Production: st.login() with the company's OpenID Connect provider
  (SSO), and st.user's email mapped to the employee ID; the agent and
  tools don't change.
- A refresh signs you out (session_state lives per browser tab); sign
  in again and the chat comes back, with a booking still waiting for
  Confirm. Chats unused for 30 days are deleted.
- The answer appears once it has passed the checks (reviewer, output
  check), never word by word: streamed text can't be un-shown if a
  check replaces it. The steps stream as they happen.
- Employee IDs are shown with names (respond.py); the model sees IDs only.
- Under each answer: thumbs up / down; each answer is kept 30 days for
  review with its background checks (quality.py); each question is
  traced in our local Langfuse while TRACE_APP is on (tracing.py), one
  trace per question (a booking's Confirm joins it), the chat as its
  session, its thumbs and checks as scores.
"""

import streamlit as st
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from ams_agent.agent import build_agent, final_answer
from ams_agent.budget import stopped_by
from ams_agent.config import (
    BACKUP,
    MAX_MESSAGE_CHARS,
    MAX_QUESTIONS_PER_MINUTE,
    TRACE_APP,
)
from ams_agent.context import context_for, role_names
from ams_agent.db import find_employee
from ams_agent.limits import RateLimiter, too_long
from ams_agent.memory import (
    chat_id,
    delete_old_chats,
    history,
    new_chat,
    open_memory,
    pending,
    touch,
)
from ams_agent.output_check import is_check_reply
from ams_agent.policy_search import warm_up
from ams_agent.quality import delete_old as delete_old_answers
from ams_agent.quality import feedback, record
from ams_agent.resilience import answered_by
from ams_agent.respond import error_message, for_person
from ams_agent.review import REVIEWER, is_review_note
from ams_agent.topic_guard import is_guard_reply
from ams_agent.tracing import new_trace_id, run_config


@st.cache_resource
def memory():
    """The durable chats and preferences (memory.py), opened once; old
    chats are deleted when the app starts."""
    saver, store = open_memory()
    delete_old_chats(saver)
    delete_old_answers()  # the review log's 30 days too
    return saver, store


@st.cache_resource
def agent():
    """Built once and shared: each person's state is in memory(), under
    their chat ID. The handbook search's models load here, not during
    the first question."""
    warm_up()
    saver, store = memory()
    return build_agent(checkpointer=saver, store=store)


@st.cache_resource
def limiter() -> RateLimiter:
    """One for the whole server, so every tab of a person shares it."""
    return RateLimiter(MAX_QUESTIONS_PER_MINUTE)


def refused(question: str, employee_id: str) -> str | None:
    """Why a question is stopped before the agent, or None."""
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
    if is_review_note(message):
        return [f"🔍 Reviewer: {message.text} → one more round"]
    if isinstance(message, AIMessage) and message.name == REVIEWER:
        return ["🔍 Reviewer: the answer was empty, so a fixed reply"]
    if is_check_reply(message):
        return [("🛡️ Output check: the answer quoted the instructions,"
                 " so it was replaced")]
    who = ("Backup model (main model unavailable)"
           if answered_by(message) == BACKUP.name else "Model")
    if isinstance(message, AIMessage) and message.tool_calls:
        return [f"🛠️ {who} asks for `{call['name']}` {call['args'] or ''}"
                for call in message.tool_calls]
    if isinstance(message, ToolMessage):
        return [(f"📄 `{message.name}` returned:\n```json\n"
                 f"{message.text[:1500]}\n```")]
    if isinstance(message, AIMessage) and message.text.strip():
        return [f"✍️ {who} writes the answer"]
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
    if node == "__interrupt__":  # a tool paused for the person's yes
        return [], ["⏸️ Waiting for your Confirm or Cancel"]
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
    # The ID and roles every question runs with, set once, by code. The
    # chat ID comes from the sign-in too, so their chat comes back,
    # and nobody can open anyone else's.
    employee_id = person["employee_id"]
    delete_old_chats(memory()[0])
    turns = history(agent(), employee_id)
    st.session_state.update(person=person, context=context_for(employee_id),
                            chat_id=chat_id(employee_id), turns=turns)
    if ask_again := pending(agent(), employee_id):  # a booking still waits
        question = turns.pop()["question"] if turns else ""
        st.session_state.pending = {
            "ask": ask_again, "turn": {"question": question, "steps": []}}
    st.rerun()


def run(payload, turn: dict) -> None:
    """Run (or resume) the agent, showing each step as it ends. A booking
    that pauses for a yes is kept in st.session_state.pending."""
    new, paused = [], None
    # The turn's trace, named before it runs: the thumbs and online
    # checks go on it later, and a resumed booking joins it.
    if TRACE_APP:
        turn.setdefault("trace", new_trace_id())
    with st.chat_message("assistant"):
        with st.status("Working…", expanded=True) as status:
            try:
                context = st.session_state.context
                chat = st.session_state.chat_id
                for update in agent().stream(
                        payload, context=context,
                        config=run_config(context.employee_id, chat,
                                          traced=TRACE_APP, session=chat,
                                          tags=("app",),
                                          trace_id=turn.get("trace")),
                        stream_mode="updates"):
                    for node, change in update.items():
                        if node == "__interrupt__":
                            paused = change[0].value
                        messages, found = read_update(node, change)
                        new = merged(new, messages)
                        turn["steps"].extend(found)
                        for step in found:
                            st.markdown(step)
            # Any failure: a plain message, never the exception.
            except Exception as e:  # noqa: BLE001
                status.update(label="Failed", state="error")
                st.error(error_message(e))
                return
            status.update(label=f"{len(turn['steps'])} steps",
                          state="complete", expanded=False)
        if paused:  # shown as Confirm / Cancel on the next rerun
            st.session_state.pending = {"ask": paused, "turn": turn}
            st.rerun()
        # Names back in, for the screen only; the chat keeps IDs.
        turn["answer"] = for_person(
            final_answer(new) or "Sorry, I couldn't answer that.")
        st.markdown(turn["answer"])
        # Kept for review, checked in the background.
        turn["row"] = record(st.session_state.context.employee_id,
                             turn["question"], turn["answer"], new,
                             turn.get("trace"))
    st.session_state.turns.append(turn)


def ask(question: str) -> None:
    """A new question: only it is sent; the chat so far is in the
    agent's checkpointer, under this chat's ID."""
    with st.chat_message("user"):
        st.markdown(question)
    touch(memory()[0], st.session_state.context.employee_id)
    run({"messages": [HumanMessage(question)]},
        {"question": question, "steps": []})


def thumbs(turn: dict) -> None:
    """Thumbs up or down under an answer, with an optional comment."""
    row, trace = turn["row"], turn.get("trace")
    key = f"thumbs-{row}"
    choice = st.feedback("thumbs", key=key,
                         on_change=lambda: feedback(
                             row, st.session_state[key], trace_id=trace))
    if choice == 0:  # down: what was wrong?
        note = st.text_input("What was wrong? (optional)", key=f"why-{row}")
        if note:
            feedback(row, 0, note, trace)


def confirm_box() -> None:
    """The paused booking: the exact action, then the person's choice."""
    pending = st.session_state.pending
    with st.chat_message("user"):
        st.markdown(pending["turn"]["question"])
    with st.chat_message("assistant"):
        with st.expander(f"{len(pending['turn']['steps'])} steps"):
            for step in pending["turn"]["steps"]:
                st.markdown(step)
        st.info(for_person(pending["ask"]["summary"]))
        if pending["ask"].get("warning"):
            st.warning(pending["ask"]["warning"])
        yes, no = st.columns(2)
        choice = (True if yes.button("Confirm", type="primary") else
                  False if no.button("Cancel") else None)
    if choice is not None:
        del st.session_state.pending  # the buttons go: one click only
        run(Command(resume={"confirmed": choice}), pending["turn"])
        st.rerun()  # redraw: the turn in the chat, no buttons


def chat_screen() -> None:
    person = st.session_state.person
    with st.sidebar:
        st.markdown(f"**{person['name']}** ({person['employee_id']})")
        st.caption(f"{person['job_title']}, {person['grade']},"
                   f" {person['office']}")
        st.caption("Roles: "
                   + ", ".join(role_names(st.session_state.context)))
        st.caption("Dev-only sign-in")
        if st.button("New chat"):  # forget this chat, start fresh
            new_chat(memory()[0], person["employee_id"])
            st.session_state.turns = []
            st.session_state.pop("pending", None)
            st.rerun()
        if st.button("Sign out"):
            st.session_state.clear()
            st.rerun()
    st.title("AMS HR assistant")
    for turn in st.session_state.turns:
        with st.chat_message("user"):
            st.markdown(turn["question"])
        with st.chat_message("assistant"):
            if turn["steps"]:  # a chat brought back has no steps
                with st.expander(f"{len(turn['steps'])} steps"):
                    for step in turn["steps"]:
                        st.markdown(step)
            st.markdown(for_person(turn["answer"]))
            if "row" in turn:
                thumbs(turn)
    if "pending" in st.session_state:  # a booking waiting for a yes
        confirm_box()
        st.chat_input("Confirm or cancel the booking first", disabled=True)
        return
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
