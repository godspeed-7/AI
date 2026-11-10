"""Ask the HR agent one question and watch every step (stage B).

In:  who is asking (--as) and a question, e.g.
     uv run python chat.py --as AMS-1015 "How many leaves do I have?"
Out: every round printed (thinking, the tool asked for, its result),
     then the answer: the same log as agent_by_hand.py.

Strategy: build_agent() (agent.py) runs the loop. stream_mode="updates"
hands us each step as it finishes, "model" (a reply) or "tools" (the
results), and we print its messages.

Caveats:
- Gives up after AGENT_MAX_STEPS model replies (RECURSION_LIMIT).
- Needs AGENT_MODEL reachable (GOOGLE_API_KEY for Google, or Ollama
  with the model pulled), and the HR database (build_hr_db.py).
"""

import argparse
import textwrap

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from ams_assistant.agent import RECURSION_LIMIT, build_agent, split_thinking
from ams_assistant.config import AGENT_MAX_STEPS, AGENT_MODEL, AGENT_PROVIDER
from ams_assistant.hr_tools import HRContext, get_employee_name


def show(label: str, text: str) -> None:
    """Print one line of the log, shortened to a few lines."""
    print(f"  {label:<9}{textwrap.shorten(text, 220, placeholder=' …')}")


def print_message(message, round_number: int) -> None:
    """Print one message from a step: a model reply or a tool result."""
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

    agent = build_agent(args.employee_id)
    round_number = 0
    try:
        # Each step is {node name: its update}; both nodes ("model",
        # "tools") update the conversation with new messages.
        for step in agent.stream(
            {"messages": [HumanMessage(question)]},
            context=HRContext(employee_id=args.employee_id),
            config={"recursion_limit": RECURSION_LIMIT},
            stream_mode="updates",
        ):
            for update in step.values():
                for message in (update or {}).get("messages", []):
                    if isinstance(message, AIMessage):
                        round_number += 1
                    print_message(message, round_number)
    except GraphRecursionError:
        print(f"Stopped: no answer after {AGENT_MAX_STEPS} rounds.")


if __name__ == "__main__":
    main()
