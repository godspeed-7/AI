"""The HR assistant in the browser: sign in, ask, watch every step.

In:  uv run streamlit run app.py, then open http://localhost:8501;
     sign in with the 4 digits of an employee ID (AMS-1014 -> 1014).
Out: a chat locked to that employee; under each question, the agent's
     steps live (model calls, thinking, tools, times), then the answer.

Strategy: the same agent as chat.py (build_agent, agent.py). Its
stream gives two kinds of events: "messages" (each token the model
writes: thinking and answer, shown as they arrive) and "updates" (a
model call or a tool run has finished: its tool request or answer,
its results, its time). SHOW_AGENT_STEPS (config.py) hides the steps.

Caveats:
- Not a real login: no password. The ID comes from the app (HRContext),
  never from the chat, so the model can't switch person.
- Streamlit re-runs this whole script on every click; who is signed in
  and the chat live in st.session_state (per browser tab, so a refresh
  signs you out).
- Follow-ups work: the agent keeps this chat's messages (agent.py,
  memory=True) under a chat ID the server makes at sign-in, never
  taken from the user. Signing out or a refresh starts a new chat.
- Booking leave pauses for Confirm / Cancel (leave_tools.py); the
  chat box is off until one is clicked.
- The reflection check (stage I) shows as a step after the answer;
  when it sends the model back to look something up, the first answer
  is cleared and the new one replaces it.
- A question asked before comes back from the reply cache at once,
  without typing out.
- Everything shown goes through shown(): markdown images become text,
  so injected text can't make the browser send data out.
"""

import logging
import re
import textwrap
import time
import uuid
from datetime import date

import streamlit as st
from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import Command

from ams_assistant.agent import build_agent, split_thinking, tools_for
from ams_assistant.config import AGENT_MAX_STEPS, AGENT_MODEL, SHOW_AGENT_STEPS
from ams_assistant.hr_tools import HRContext, get_employee_card
# CANT_ANSWER: what the user sees when a run fails; the details go to
# the log (the terminal running the app), never to the page.
from ams_assistant.middleware import (
    CANT_ANSWER,
    REFLECTION,
    Reflection,
    answer_check,
)
from ams_assistant.policy_tools import search_policies
from ams_assistant.preferences import forget_preferences, remember_preference

STEP_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"
# Where a tool looks, as the steps show it; every other tool reads the
# HR database.
WHERE = {
    search_policies.name: "handbooks (Qdrant)",
    remember_preference.name: "your preferences (memory)",
    forget_preferences.name: "your preferences (memory)",
}
logger = logging.getLogger(__name__)
# A markdown image, ![text](address) or ![text][ref]. The browser loads
# images by itself, so text injected into the data (e.g. a claim's
# description) could make the model hide private data in an image's
# address and send it out the moment the answer is shown.
IMAGE = re.compile(r"!\[([^\]]*)\]\s*(\([^)]*\)|\[[^\]]*\])")


def shown(text: str) -> str:
    """Model, tool or user text, made safe to show as markdown: images
    become plain text. (Raw HTML is already off: st.markdown escapes
    it unless unsafe_allow_html=True.)"""
    return IMAGE.sub(r"[image removed: \1]", text)


def nice_date(iso: str) -> str:
    """'2027-01-20' -> '20 Jan 2027'."""
    return date.fromisoformat(iso).strftime("%-d %b %Y")


def quote(text: str) -> str:
    """Markdown block quote, so thinking stands apart from the steps."""
    return "\n".join(f"> {line}" for line in text.splitlines())


def call_text(call: dict) -> str:
    """A tool call as code: get_leave_balance(leave_type='annual')."""
    args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
    return f"`{call['name']}({args})`"


# --- Screen 1: sign in ----------------------------------------------

def sign_in_screen() -> None:
    """Ask for the 4 digits; on a known ID, remember who signed in."""
    st.title("AMS HR Assistant")
    with st.form("sign_in"):
        st.markdown("**Employee ID**")
        prefix, box = st.columns([1, 6], vertical_alignment="center")
        prefix.markdown("**AMS-**")
        digits = box.text_input("Employee ID", max_chars=4,
                                placeholder="1014",
                                label_visibility="collapsed")
        submitted = st.form_submit_button("Sign in")  # or press Enter

    if not submitted:
        return
    digits = digits.strip()
    if len(digits) != 4 or not digits.isdigit():
        st.error("Enter the 4 digits of your employee ID, e.g. 1014.")
        return
    card = get_employee_card(f"AMS-{digits}")
    if card is None:
        st.error(f"No employee with ID AMS-{digits}.")
        return
    st.session_state.card = card
    st.session_state.agent = build_agent(card["employee_id"], memory=True)
    # This chat's ID: made here, on the server, so no one can name
    # another person's chat.
    st.session_state.chat_id = uuid.uuid4().hex
    st.session_state.history = []
    st.rerun()  # draw the chat screen


# --- Screen 2: chat ---------------------------------------------------

def profile_card(card: dict) -> None:
    """Who is signed in, their role, and the Sign out button."""
    with st.container(border=True):
        text, button = st.columns([5, 1], vertical_alignment="top")
        text.markdown(f"**{card['name']}** · {card['employee_id']}")
        text.caption(f"{card['job_title']} · {card['department']} · "
                     f"{card['office']} · {card['grade']}")
        if card["direct_reports"]:
            role = f"Role: Manager ({card['direct_reports']} direct reports)"
        else:
            role = "Role: Employee"
            if "manager_name" in card:
                role += f" · manager: {card['manager_name']}"
        text.caption(role)
        if card["status"] == "probation":
            text.caption("On probation until "
                         f"{nice_date(card['probation_end_date'])}")
        elif card["status"] == "notice_period":
            text.caption("On notice period · last working day "
                         f"{nice_date(card['last_working_day'])}")
        if button.button("Sign out"):
            st.session_state.clear()  # forget who and the chat
            st.rerun()


class Trace:
    """The steps of one question as markdown parts, redrawn into one
    placeholder whenever a part changes (box=None: steps hidden)."""

    def __init__(self, box):
        self.box = box
        self.parts: list[str] = []

    def add(self, text: str) -> int:
        """Add a part and return its index, for set()."""
        self.parts.append(text)
        self.draw()
        return len(self.parts) - 1

    def set(self, index: int, text: str) -> None:
        self.parts[index] = text
        self.draw()

    def text(self) -> str:
        return "\n\n".join(part for part in self.parts if part)

    def draw(self) -> None:
        if self.box is not None:
            self.box.markdown(shown(self.text()))


class Run:
    """Turns the agent's stream events into steps and the answer."""

    def __init__(self, trace: Trace, answer_box, card: dict,
                 earlier: int = 0, asking: bool = True):
        self.trace = trace
        self.answer_box = answer_box
        self.employee_id = card["employee_id"]
        # Sent with every model call: this person's tools (managers
        # have more, agent.py).
        self.tool_count = len(tools_for(card))
        # step_started: also set here, for a run that carries on after a
        # pause, whose first step is the paused tool, not a model call.
        self.started = self.step_started = time.perf_counter()
        self.steps = self.model_calls = self.tool_calls = 0
        # The chat's earlier messages (memory) go with every call, plus
        # the instructions, and the question (unless this run carries
        # on after a pause).
        self.earlier, self.asking = earlier, asking
        self.messages_sent = 1 + earlier + asking
        self.answer = ""
        self.result_parts = {}
        # What paused tools ask the person, and their pauses' IDs.
        self.question, self.pause_ids = None, []

    def next_number(self) -> str:
        self.steps += 1
        return STEP_NUMBERS[self.steps - 1:self.steps] or f"{self.steps}."

    def start_model_call(self) -> None:
        """A new model call starts: header + an empty thinking part."""
        self.model_calls += 1
        first = self.model_calls == 1 and self.asking
        if first and not self.earlier:
            sends = "the instructions and the question"
        elif first:
            sends = (f"the instructions, the chat so far ({self.earlier} "
                     "messages) and the question")
        else:
            sends = f"all {self.messages_sent} messages so far"
        self.trace.add(f"**{self.next_number()} Model call "
                       f"{self.model_calls}** → `{AGENT_MODEL}` · sends "
                       f"{sends} + {self.tool_count} tool descriptions")
        self.thinking_part = self.trace.add("")
        self.thinking = self.text = ""
        self.step_started = time.perf_counter()

    def on_token(self, chunk: AIMessageChunk) -> None:
        """One piece of the model's thinking or text, as it's written."""
        piece = chunk.additional_kwargs.get("reasoning_content", "")
        if piece:
            self.thinking += piece
            self.trace.set(self.thinking_part, quote(f"💭 {self.thinking}"))
        # .text: the text whether content is a string (Ollama) or a
        # list of parts (Gemini).
        if chunk.text:
            self.text += chunk.text
            self.answer_box.markdown(shown(self.text) + " ▌")

    def on_model_done(self, reply: AIMessage) -> None:
        """The model call finished: a tool request or the answer."""
        seconds = time.perf_counter() - self.step_started
        self.messages_sent += 1
        # The full reply replaces the pieces (and covers a cached reply,
        # which arrives whole, without tokens).
        thinking, text = split_thinking(reply)
        self.trace.set(self.thinking_part,
                       quote(f"💭 {thinking}") if thinking else "")
        if not reply.tool_calls:
            self.trace.add(f"↳ answer · {seconds:.1f} s")
            self.answer = text
            self.answer_box.markdown(shown(text))
            self.step_started = time.perf_counter()  # the reflection's
            return
        if text:  # some models say something before asking for a tool
            self.trace.add(f"↳ says: {text}")
            self.answer_box.empty()
        calls = ", ".join(call_text(call) for call in reply.tool_calls)
        self.trace.add(f"↳ asks for: {calls} · {seconds:.1f} s")
        self.result_parts = {}
        for call in reply.tool_calls:
            self.tool_calls += 1
            where = WHERE.get(call["name"],
                              f"HR database ({self.employee_id})")
            self.trace.add(f"**{self.next_number()} Tool** "
                           f"{call_text(call)} → {where}")
            self.result_parts[call["id"]] = self.trace.add("↳ running…")
        self.step_started = time.perf_counter()

    def on_tools_done(self, results: list) -> None:
        """The tools finished: show what each returned."""
        seconds = time.perf_counter() - self.step_started
        for result in results:
            self.messages_sent += 1
            short = textwrap.shorten(str(result.content), 240,
                                     placeholder=" …")
            index = self.result_parts.get(result.tool_call_id)
            line = f"↳ returned: {short} · {seconds:.2f} s"
            if index is None:
                self.trace.add(line)
            else:
                self.trace.set(index, line)

    def on_pause(self, interrupts) -> None:
        """Tools paused the run to ask the person (booking leave,
        deciding requests: every check passed; Confirm or Cancel). The
        model should ask once, but if it paused several tools at once,
        they're asked together and one answer goes to all."""
        for index in self.result_parts.values():
            self.trace.set(index, "↳ checked · waiting for your answer")
        self.trace.add("⏸ **Paused** · nothing is saved until you answer")
        self.question = self.answer = "\n\n".join(
            pause.value["question"] for pause in interrupts)
        self.pause_ids = [pause.id for pause in interrupts]
        self.answer_box.markdown(shown(self.question))

    def on_answer_check(self, message) -> None:
        """The answer check found an empty answer: it asks the model
        again (its note), or, the second time, gives CANT_ANSWER."""
        if isinstance(message, HumanMessage):
            self.messages_sent += 1
            self.trace.add("↳ answer check: empty answer, asking again")
            self.start_model_call()
        else:
            self.trace.add("↳ answer check: empty again, no answer")
            self.answer = message.text
            self.answer_box.markdown(self.answer)

    def on_reflection(self, missing: str | None) -> None:
        """The reflection check read the answer: nothing missing, or a
        records tool it still needs (the model is sent back)."""
        seconds = time.perf_counter() - self.step_started
        if missing is None:
            self.trace.add(f"↳ reflection: nothing missing · "
                           f"{seconds:.1f} s")
            return
        self.trace.add(f"↳ reflection: it still needs `{missing}()` · "
                       f"{seconds:.1f} s; back to the model")
        self.answer = ""
        self.answer_box.empty()

    def on_node_done(self, node: str, update) -> None:
        """A node ("model", "tools", or a middleware hook) has finished,
        with its new messages; of the middleware, only the answer check
        and the reflection add any (their notes to the model)."""
        if node == "__interrupt__":  # a tool asks the person
            self.on_pause(update)
            return
        messages = (update or {}).get("messages", [])
        if node == "model":
            self.on_model_done(messages[-1])
        elif node == "tools":
            self.on_tools_done(messages)
            self.start_model_call()
        elif node.startswith(answer_check.name) and messages:
            self.on_answer_check(messages[-1])
        elif node.startswith(Reflection.__name__) and messages:
            self.messages_sent += 1  # its note
            self.start_model_call()

    def handle(self, mode: str, data) -> None:
        """One stream event. "messages": a token as it's written;
        "custom": the reflection's verdict; "updates": nodes that have
        finished."""
        if mode == "messages":
            chunk, _metadata = data
            if isinstance(chunk, AIMessageChunk):
                self.on_token(chunk)
        elif mode == "custom":
            if REFLECTION in data:
                self.on_reflection(data[REFLECTION])
        else:
            for node, update in data.items():
                self.on_node_done(node, update)

    def summary(self) -> str:
        seconds = time.perf_counter() - self.started
        calls = "call" if self.model_calls == 1 else "calls"
        tools = "tool" if self.tool_calls == 1 else "tools"
        return (f"{self.model_calls} model {calls} · {self.tool_calls} "
                f"{tools} · {seconds:.1f} s")


def run_agent(said: str, reply: str | None = None) -> dict:
    """Run the agent, drawing it live: on a new question (`said`), or,
    after a pause, on the person's reply ("confirm" or "cancel"), which
    the paused tool carries on with. Return the turn for the history;
    st.session_state.pending holds what a paused tool asks."""
    card = st.session_state.card
    agent = st.session_state.agent
    # thread_id: this chat; the agent adds its earlier messages.
    config = {"configurable": {"thread_id": st.session_state.chat_id}}
    earlier = len(agent.get_state(config).values.get("messages", []))
    trace = Trace(st.empty() if SHOW_AGENT_STEPS else None)
    run = Run(trace, st.empty(), card, earlier,
              asking=reply is None)
    if reply is None:
        agent_input = {"messages": [HumanMessage(said)]}
        run.start_model_call()
    else:
        # The reply goes to every paused tool, by its pause's ID.
        agent_input = Command(resume=dict.fromkeys(
            st.session_state.pause_ids, reply))
        trace.add(f"**You:** {said} · the paused tool carries on")
    try:
        for mode, data in agent.stream(
            agent_input,
            context=HRContext(employee_id=card["employee_id"]),
            config=config,
            stream_mode=["messages", "updates", "custom"],
        ):
            run.handle(mode, data)
    except ModelCallLimitExceededError:
        run.answer = f"Stopped: no answer after {AGENT_MAX_STEPS} rounds."
        run.answer_box.markdown(run.answer)
    except Exception:
        # A model call failed after its retries, timed out, or a tool
        # broke: a plain message, never a stack trace.
        logger.exception("Agent run failed")
        run.answer = CANT_ANSWER
        run.answer_box.markdown(run.answer)
    st.session_state.pending = run.question
    st.session_state.pause_ids = run.pause_ids
    summary = run.summary()
    trace.add(f"**{'Paused' if run.question else 'Done'}** · {summary}")
    return {"question": said, "answer": run.answer,
            "steps": trace.text(), "summary": summary}


def show_history() -> None:
    """Earlier questions: steps folded away, answer shown."""
    for turn in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(shown(turn["question"]))
        with st.chat_message("assistant"):
            if SHOW_AGENT_STEPS:
                with st.expander(f"Steps · {turn['summary']}"):
                    st.markdown(shown(turn["steps"]))
            st.markdown(shown(turn["answer"]))


def confirm_buttons() -> str | None:
    """Under a paused tool's question (the last answer): "confirm" or
    "cancel" when clicked, else None."""
    confirm, cancel, _ = st.columns([1, 1, 4])
    if confirm.button("Confirm", key="confirm", type="primary"):
        return "confirm"
    if cancel.button("Cancel", key="cancel"):
        return "cancel"
    return None


def chat_screen() -> None:
    profile_card(st.session_state.card)
    show_history()
    # While a tool waits, only its two buttons go on: a new question
    # would leave the tool call unanswered.
    pending = st.session_state.get("pending")
    reply = confirm_buttons() if pending else None
    question = st.chat_input(
        "Confirm or cancel above first" if pending else "Ask a question…",
        disabled=bool(pending))
    if not (question or reply):
        return
    said = reply.capitalize() if reply else question
    with st.chat_message("user"):
        st.markdown(shown(said))
    with st.chat_message("assistant"):
        if SHOW_AGENT_STEPS:
            turn = run_agent(said, reply)
        else:
            with st.spinner("Working…"):
                turn = run_agent(said, reply)
    st.session_state.history.append(turn)
    if pending or st.session_state.pending:
        st.rerun()  # draw the buttons, or take them away


st.set_page_config(page_title="AMS HR Assistant", page_icon="💼")
if "card" in st.session_state:
    chat_screen()
else:
    sign_in_screen()
