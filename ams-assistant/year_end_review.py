"""Run the year-end leave review and watch it work (DEEP_AGENTS_PLAYBOOK
stage A).

In:  who is asking (--as, People Operations; Neha Kulkarni by default)
     and --department (one, or "all"; Sales by default), e.g.
     uv run python year_end_review.py --department all
Out: each step as it happens (the tool asked for, its result), then
     every memo with its check against the records (year_end.py), and
     what the run took: model calls, prompt size per call, time.

Strategy: run_review() (year_end.py) runs the lead agent; "all" asks
for every department in one conversation, the case stage A measures.

Caveats:
- Gemini is paced at 6 calls a minute (config.py): all 6 departments
  take a few minutes. Replies are cached: a second run is instant.
- With LANGFUSE_TRACING (config.py), the run is recorded in Langfuse.
"""

import argparse
import textwrap

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from ams_assistant.year_end import check_memo, memo_path, run_review
from ams_assistant.year_end_tools import DEPARTMENTS


def show(message: AnyMessage) -> None:
    """Print one step: the tools the lead asks for, a result, or its
    last reply."""
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items()
                             if k != "content")
            print(f"  → {call['name']}({args})")
        if not message.tool_calls and message.text:
            print(f"  reply   {textwrap.shorten(message.text, 300)}")
    elif isinstance(message, ToolMessage):
        print(f"  ← {message.name}: "
              f"{textwrap.shorten(str(message.content), 100)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as", dest="employee_id", default="AMS-1005",
                        help="a People Operations employee's ID")
    parser.add_argument("--department", default="Sales",
                        choices=[*DEPARTMENTS, "all"])
    args = parser.parse_args()
    departments = (list(DEPARTMENTS) if args.department == "all"
                   else [args.department])

    print(f"Year-end review of {', '.join(departments)}, "
          f"as {args.employee_id}\n")
    run = run_review(args.employee_id, departments, on_message=show)

    for department in departments:
        path = memo_path(department)
        memo = run["memos"].get(path)
        print(f"\n{'─' * 70}\n{path}")
        if memo is None:
            print("  (no memo written)")
            continue
        print(textwrap.indent(memo.strip(), "  "))
        check = check_memo(memo, department, run["seen"])
        people = len(check["right"]) + len(check["wrong"]) + len(
            check["missing"])
        print(f"\n  Check: people right {len(check['right'])}/{people}"
              f" · wrong {check['wrong'] or 'none'}"
              f" · missing {check['missing'] or 'none'}"
              f" · pending requests missing "
              f"{check['pending_missing'] or 'none'}"
              f" · total {'right' if check['total_right'] else 'WRONG'}"
              f" · invented numbers {check['invented'] or 'none'}")

    tokens = run["prompt_tokens"]
    print(f"\n{'─' * 70}\nModel calls {run['model_calls']} · tool calls "
          f"{len(run['tool_calls'])} ({', '.join(run['tool_calls'])})")
    if tokens:
        print(f"Prompt tokens per call: first {tokens[0]:,}, last "
              f"{tokens[-1]:,}, largest {max(tokens):,}, all "
              f"{sum(tokens):,} · output {run['output_tokens']:,}")
    print(f"Time {run['seconds']} s"
          + (f" · {run['stopped']}" if run["stopped"] else ""))


if __name__ == "__main__":
    main()
