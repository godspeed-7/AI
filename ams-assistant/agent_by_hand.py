"""The agent loop, written by hand, so every step is visible (stage A).

In:  who is asking (--as) and a question, e.g.
     uv run python agent_by_hand.py --as AMS-1015 "How many leaves do I have?"
Out: every round printed (thinking, the tool asked for, its result),
     then the answer.

Strategy: the model gets the instructions, the question and the tool
list (bind_tools). While its reply asks for a tool, our code adds who
is asking (the tool's runtime), runs the tool and appends the result;
a reply that asks for nothing is the answer. chat.py runs the same
tools and instructions (agent.py) with LangChain's create_agent().

Caveats:
- Gives up after AGENT_MAX_STEPS replies, so a confused model can't
  loop forever.
- A thinking model's reasoning is printed as "thinking", apart from
  the answer: qwen3's when AGENT_THINKING is on, or Gemma 4's
  "<thought>..." text.
- Replies are cached (llm_cache.py): asking the same question again
  replays the saved replies instantly.
"""

import argparse
import textwrap

from langchain.tools import ToolRuntime
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from ams_assistant.agent import AGENT_TOOLS, INSTRUCTIONS, split_thinking
from ams_assistant.config import (
    AGENT_MAX_STEPS,
    AGENT_MODEL,
    AGENT_PROVIDER,
    AGENT_THINKING,
)
from ams_assistant.hr_tools import HRContext, get_employee_name
from ams_assistant.llm import build_llm

# The tools the model may ask for, by name (the name the model uses).
TOOLS = {t.name: t for t in AGENT_TOOLS}


def run_tool(call: dict, employee_id: str) -> ToolMessage:
    """Run one tool call from the model and return its result message."""
    tool = TOOLS.get(call["name"])
    if tool is None:
        return ToolMessage(f"Error: there is no tool named {call['name']}.",
                           tool_call_id=call["id"])
    # The model filled in its inputs; our code adds who is asking, as
    # the tool's `runtime`. create_agent() builds this for every tool
    # call; our tools only read its context (HRContext).
    runtime = ToolRuntime(state={}, context=HRContext(employee_id),
                          config={}, stream_writer=lambda _: None,
                          tool_call_id=call["id"], store=None)
    call = {**call, "args": {**call["args"], "runtime": runtime}}
    try:
        # Given the whole call (not just the args), a tool returns a
        # ToolMessage tagged with the call's id, ready for the messages.
        return tool.invoke(call)
    except ValidationError as error:
        # A bad input (e.g. leave_type="vacation") goes back to the
        # model as the result, so it can try again.
        return ToolMessage(f"Error: invalid input. {error}",
                           tool_call_id=call["id"])


def show(label: str, text: str) -> None:
    """Print one line of the log, shortened to a few lines."""
    print(f"  {label:<9}{textwrap.shorten(text, 220, placeholder=' …')}")


def run_agent(question: str, employee_id: str) -> str | None:
    """Loop: model -> tool -> model ... until it answers (or gives up)."""
    llm = build_llm(AGENT_PROVIDER, AGENT_MODEL, temperature=0,
                    reasoning=AGENT_THINKING)
    # bind_tools: every call now also sends the tools' names,
    # descriptions and inputs (what the model sees).
    llm_with_tools = llm.bind_tools(list(TOOLS.values()))

    name = get_employee_name(employee_id)
    messages = [SystemMessage(INSTRUCTIONS.format(name=name)),
                HumanMessage(question)]

    for round_number in range(1, AGENT_MAX_STEPS + 1):
        print(f"Round {round_number}")
        # The model reads the whole conversation every time: it keeps
        # no memory of its own between calls.
        reply = llm_with_tools.invoke(messages)
        messages.append(reply)

        thinking, text = split_thinking(reply)
        if thinking:
            show("thinking", thinking)

        if not reply.tool_calls:  # it asked for nothing: the answer
            show("answer", text)
            return text

        for call in reply.tool_calls:
            args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
            show("tool", f"{call['name']}({args})")
            result = run_tool(call, employee_id)
            show("result", result.content)
            messages.append(result)

    print(f"Stopped: no answer after {AGENT_MAX_STEPS} rounds.")
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as", dest="employee_id", required=True,
                        help="who is asking, e.g. AMS-1015")
    parser.add_argument("question", nargs="?",
                        help="the question (asked for if left out)")
    args = parser.parse_args()

    try:
        name = get_employee_name(args.employee_id)
    except ValueError as error:
        parser.error(str(error))  # prints the message and exits

    question = args.question or input("Your question: ").strip()
    print(f"{name} ({args.employee_id}) asks: {question}\n"
          f"Model: {AGENT_PROVIDER} / {AGENT_MODEL}\n")
    run_agent(question, args.employee_id)


if __name__ == "__main__":
    main()
