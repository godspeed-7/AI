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
- Each question is answered on its own: no follow-ups until stage G.
- A question asked before comes back from the reply cache at once,
  without typing out.
- Everything shown goes through shown(): markdown images become text,
  so injected text can't make the browser send data out.
"""

import logging
import re
import textwrap
import time
from datetime import date

import streamlit as st
from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from ams_assistant.agent import AGENT_TOOLS, build_agent, split_thinking
from ams_assistant.config import AGENT_MAX_STEPS, AGENT_MODEL, SHOW_AGENT_STEPS
from ams_assistant.hr_tools import HRContext, get_employee_card
# CANT_ANSWER: what the user sees when a run fails; the details go to
# the log (the terminal running the app), never to the page.
from ams_assistant.middleware import CANT_ANSWER, answer_check
from ams_assistant.policy_tools import search_policies

STEP_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫"
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
    st.session_state.agent = build_agent(card["employee_id"])
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

    def __init__(self, trace: Trace, answer_box, employee_id: str):
        self.trace = trace
        self.answer_box = answer_box
        self.employee_id = employee_id
        self.started = time.perf_counter()
        self.steps = self.model_calls = self.tool_calls = 0
        self.messages_sent = 2  # the instructions + the question
        self.answer = ""

    def next_number(self) -> str:
        self.steps += 1
        return STEP_NUMBERS[self.steps - 1:self.steps] or f"{self.steps}."

    def start_model_call(self) -> None:
        """A new model call starts: header + an empty thinking part."""
        self.model_calls += 1
        if self.model_calls == 1:
            sends = "the instructions and the question"
        else:
            sends = f"all {self.messages_sent} messages so far"
        self.trace.add(f"**{self.next_number()} Model call "
                       f"{self.model_calls}** → `{AGENT_MODEL}` · sends "
                       f"{sends} + {len(AGENT_TOOLS)} tool descriptions")
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
            return
        if text:  # some models say something before asking for a tool
            self.trace.add(f"↳ says: {text}")
            self.answer_box.empty()
        calls = ", ".join(call_text(call) for call in reply.tool_calls)
        self.trace.add(f"↳ asks for: {calls} · {seconds:.1f} s")
        self.result_parts = {}
        for call in reply.tool_calls:
            self.tool_calls += 1
            if call["name"] == search_policies.name:
                where = "handbooks (Qdrant)"
            else:
                where = f"HR database ({self.employee_id})"
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

    def handle(self, mode: str, data) -> None:
        """One stream event. "messages": a token as it's written;
        "updates": a node ("model", "tools", or a middleware hook) has
        finished, with its new messages; of the middleware, only the
        answer check adds any."""
        if mode == "messages":
            chunk, _metadata = data
            if isinstance(chunk, AIMessageChunk):
                self.on_token(chunk)
            return
        for node, update in data.items():
            messages = (update or {}).get("messages", [])
            if node == "model":
                self.on_model_done(messages[-1])
            elif node == "tools":
                self.on_tools_done(messages)
                self.start_model_call()
            elif node.startswith(answer_check.name) and messages:
                self.on_answer_check(messages[-1])

    def summary(self) -> str:
        seconds = time.perf_counter() - self.started
        calls = "call" if self.model_calls == 1 else "calls"
        tools = "tool" if self.tool_calls == 1 else "tools"
        return (f"{self.model_calls} model {calls} · {self.tool_calls} "
                f"{tools} · {seconds:.1f} s")


def ask(question: str) -> dict:
    """Run the agent on one question, drawing it live; return the turn
    for the history."""
    card = st.session_state.card
    trace = Trace(st.empty() if SHOW_AGENT_STEPS else None)
    run = Run(trace, st.empty(), card["employee_id"])
    run.start_model_call()
    try:
        for mode, data in st.session_state.agent.stream(
            {"messages": [HumanMessage(question)]},
            context=HRContext(employee_id=card["employee_id"]),
            stream_mode=["messages", "updates"],
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
    summary = run.summary()
    trace.add(f"**Done** · {summary}")
    return {"question": question, "answer": run.answer,
            "steps": trace.text(), "summary": summary}


def chat_screen() -> None:
    profile_card(st.session_state.card)

    # Earlier questions: steps folded away, answer shown.
    for turn in st.session_state.history:
        with st.chat_message("user"):
            st.markdown(shown(turn["question"]))
        with st.chat_message("assistant"):
            if SHOW_AGENT_STEPS:
                with st.expander(f"Steps · {turn['summary']}"):
                    st.markdown(shown(turn["steps"]))
            st.markdown(shown(turn["answer"]))

    question = st.chat_input("Ask a question…")
    if not question:
        return
    with st.chat_message("user"):
        st.markdown(shown(question))
    with st.chat_message("assistant"):
        if SHOW_AGENT_STEPS:
            turn = ask(question)
        else:
            with st.spinner("Working…"):
                turn = ask(question)
    st.session_state.history.append(turn)


st.set_page_config(page_title="AMS HR Assistant", page_icon="💼")
if "card" in st.session_state:
    chat_screen()
else:
    sign_in_screen()
