"""Ask the HR agent one question and watch every step (stage B).

In:  who is asking (--as) and a question, e.g.
     uv run python chat.py --as AMS-1015 "How many leaves do I have?"
Out: every round printed (thinking, the tool asked for, its result),
     then the answer: the same log as agent_by_hand.py.

Strategy: build_agent() (agent.py) runs the loop. stream_mode="updates"
hands us each step as it finishes, "model" (a reply) or "tools" (the
results), and we print its messages.

Caveats:
- Gives up after AGENT_MAX_STEPS model replies (agent.py's limit).
- Booking leave asks "Confirm? [y/N]" here (leave_tools.py); anything
  but y cancels.
- Needs AGENT_MODEL reachable (GOOGLE_API_KEY for Google, or Ollama
  with the model pulled), and the HR database (build_hr_db.py).
"""

import argparse
import textwrap

from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from ams_assistant.agent import build_agent, split_thinking
from ams_assistant.config import AGENT_MAX_STEPS, AGENT_MODEL, AGENT_PROVIDER
from ams_assistant.hr_tools import HRContext, get_employee_name


def show(label: str, text: str) -> None:
    """Print one line of the log, shortened to a few lines."""
    print(f"  {label:<9}{textwrap.shorten(text, 220, placeholder=' …')}")


def print_message(message, round_number: int) -> None:
    """Print one message from a step: a model reply, a tool result or
    the answer check's note."""
    if isinstance(message, AIMessage):
        print(f"Round {round_number}")
        thinking, text = split_thinking(message)
        if thinking:
            show("thinking", thinking)
        for call in message.tool_calls:
            args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items())
            show("tool", f"{call['name']}({args})")
        if not message.tool_calls:  # it asked for nothing: the answer
            show("answer", text)
    elif isinstance(message, ToolMessage):
        show("result", message.content)
    elif isinstance(message, HumanMessage):  # the answer check's note
        show("check", message.content)


def run_steps(agent, agent_input, context: HRContext, config: dict,
              round_number: int) -> tuple[int, list]:
    """Run the agent, printing each step's messages; return the round
    number and the pauses of tools that ask the person (none if the
    run finished)."""
    pauses = []
    # Each step is {node name: its update}; "model" and "tools" add
    # messages, middleware steps (e.g. the call counter) add none.
    for step in agent.stream(agent_input, context=context, config=config,
                             stream_mode="updates"):
        for node, update in step.items():
            if node == "__interrupt__":
                pauses = list(update)
                continue
            for message in (update or {}).get("messages", []):
                if isinstance(message, AIMessage):
                    round_number += 1
                print_message(message, round_number)
    return round_number, pauses


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

    # memory: a paused tool (booking leave) carries on in this chat.
    agent = build_agent(args.employee_id, memory=True)
    config = {"configurable": {"thread_id": "chat"}}
    context = HRContext(employee_id=args.employee_id)
    agent_input = {"messages": [HumanMessage(question)]}
    round_number = 0
    try:
        while agent_input is not None:
            round_number, pauses = run_steps(agent, agent_input, context,
                                             config, round_number)
            agent_input = None
            if pauses:  # tools paused: one answer for all of them
                for pause in pauses:
                    print(f"  {pause.value['question']}")
                yes = input("  Confirm? [y/N] ").strip().lower() == "y"
                reply = "confirm" if yes else "cancel"
                agent_input = Command(resume=dict.fromkeys(
                    [pause.id for pause in pauses], reply))
    except ModelCallLimitExceededError:
        print(f"Stopped: no answer after {AGENT_MAX_STEPS} rounds.")


if __name__ == "__main__":
    main()
