"""Agent evaluation: run every agent question and score it (stage C).

In:  ams-data/agent_questions.csv (who asks, the question, the expected
     answer, the tools it must use) and the agent's model: config.py's,
     or --provider / --model / --thinking to compare others.
Out: evals/agent_results_<model>.csv (one row per question, written as
     the run goes) and a summary: answer score, tool score, cost.

Strategy: per question, build_agent() (agent.py, the same agent as
chat.py and the app) answers as that employee. Three scores:
- answer: the judge (judge.py), 0-6, with the sign-in facts (about(),
  agent.py) and every tool result as its "retrieved context";
- tools: were all the tools the question needs called? (code, no LLM;
  extra calls aren't penalised, only counted; "a|b" in required_tools
  means either will do);
- cost: model calls, tool calls and seconds (the agent only, not the
  judge).

Usage (from ams-assistant/):
    uv run python evals/evaluate_agent.py --limit 3    # quick check
    uv run python evals/evaluate_agent.py              # config's model
    uv run python evals/evaluate_agent.py --thinking off
    uv run python evals/evaluate_agent.py --provider google \\
        --model gemini-3.5-flash-lite
    uv run python evals/evaluate_agent.py --only X2,X3 # some questions

Caveats:
- Starts by rebuilding the HR database from the CSVs (build_hr_db.py),
  so every run sees the same data: leave booked in the app is wiped.
- Replies and grades are cached (llm_cache.py): a rerun only calls the
  models for questions whose input changed.
- Hosted seconds include Google's pacing (GOOGLE_CALLS_PER_MINUTE).
- Questions run one at a time (one local model at a time on this Mac).
- A question that fails is logged and skipped, so a run isn't lost.
"""

import argparse
import csv
import runpy
import time
from collections import defaultdict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from ams_assistant.agent import (
    RECURSION_LIMIT,
    about,
    build_agent,
    split_thinking,
)
from ams_assistant.config import (
    AGENT_MAX_STEPS,
    AGENT_MODEL,
    AGENT_PROVIDER,
    AGENT_QUESTIONS_FILE,
    AGENT_THINKING,
    EVALS_DIR,
    JUDGE_MODEL,
    JUDGE_PROVIDER,
    PROJECT_ROOT,
)
from ams_assistant.hr_tools import HRContext, get_employee_card
from ams_assistant.judge import build_judge

FIELDNAMES = [
    "id", "category", "employee_id", "question", "expected_answer",
    "required_tools", "tools_called", "missing_tools", "tools_ok",
    "generated_answer", "correctness", "context_support", "completeness",
    "total_score", "explanation", "model_calls", "tool_calls", "seconds",
]


def run_agent(item: dict, provider: str, model: str,
              thinking: bool) -> dict:
    """Answer one question as its employee; return what happened."""
    agent = build_agent(item["employee_id"], provider, model, thinking)
    messages = []
    start = time.perf_counter()
    stopped = False
    try:
        # Collect the messages step by step, so a run that hits the step
        # limit still shows which tools it called.
        for step in agent.stream(
            {"messages": [HumanMessage(item["question"])]},
            context=HRContext(employee_id=item["employee_id"]),
            config={"recursion_limit": RECURSION_LIMIT},
            stream_mode="updates",
        ):
            for update in step.values():
                messages.extend((update or {}).get("messages", []))
    except GraphRecursionError:
        stopped = True
    seconds = time.perf_counter() - start

    replies = [m for m in messages if isinstance(m, AIMessage)]
    results = [m for m in messages if isinstance(m, ToolMessage)]
    if stopped or not replies:
        answer = f"(no answer: stopped after {AGENT_MAX_STEPS} rounds)"
    else:
        answer = split_thinking(replies[-1])[1]
    # What the judge checks the answer against: what the model knew
    # from the start (the sign-in facts), then every tool result under
    # the tool's name (handbook chunks keep their [source]).
    facts = about(get_employee_card(item["employee_id"]))
    return {
        "answer": answer,
        "called": [c["name"] for r in replies for c in r.tool_calls],
        "context": "\n\n".join([f"[sign-in facts]\n{facts}"]
                               + [f"[{m.name}]\n{m.content}"
                                  for m in results]),
        "model_calls": len(replies),
        "tool_calls": len(results),
        "seconds": round(seconds, 1),
    }


def evaluate(item: dict, run: dict, judge) -> dict:
    """Score one run: the judge for the answer, code for the tools."""
    scores = judge.invoke({
        "question": item["question"],
        "expected_answer": item["expected_answer"],
        "retrieved_context": run["context"],
        "generated_answer": run["answer"],
    })
    required = [t.strip() for t in item["required_tools"].split(";")
                if t.strip()]
    # "a|b": either tool is a right way in (M1: the team list, or the
    # report's profile).
    missing = [t for t in required
               if not any(option.strip() in run["called"]
                          for option in t.split("|"))]
    return {
        **{key: item[key] for key in ("id", "category", "employee_id",
                                      "question", "expected_answer",
                                      "required_tools")},
        "tools_called": "; ".join(run["called"]),
        "missing_tools": "; ".join(missing),
        "tools_ok": "no" if missing else "yes",
        "generated_answer": run["answer"],
        "correctness": scores.correctness,
        "context_support": scores.context_support,
        "completeness": scores.completeness,
        "total_score": scores.total,
        "explanation": scores.explanation,
        "model_calls": run["model_calls"],
        "tool_calls": run["tool_calls"],
        "seconds": run["seconds"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=AGENT_PROVIDER,
                        choices=["ollama", "google", "nvidia"])
    parser.add_argument("--model", default=AGENT_MODEL)
    parser.add_argument("--thinking", choices=["on", "off"],
                        help="Ollama thinking models only (default: "
                             "AGENT_THINKING in config.py)")
    parser.add_argument("--limit", type=int,
                        help="only the first N questions (a quick check)")
    parser.add_argument("--only", help="question ids, e.g. X2,X3")
    args = parser.parse_args()

    thinking = AGENT_THINKING if args.thinking is None \
        else args.thinking == "on"
    with open(AGENT_QUESTIONS_FILE, encoding="utf-8", newline="") as f:
        questions = list(csv.DictReader(f))
    if args.only:
        wanted = {q.strip() for q in args.only.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    questions = questions[:args.limit]

    # One results file per model (and thinking setting), so runs can be
    # compared side by side.
    label = args.model.replace(":", "-").replace("/", "-")
    if args.provider == "ollama":
        label += f"_thinking-{'on' if thinking else 'off'}"
    output_file = EVALS_DIR / f"agent_results_{label}.csv"
    print(f"Agent: {args.provider} {args.model} ({label}), "
          f"judge: {JUDGE_PROVIDER} {JUDGE_MODEL}, "
          f"{len(questions)} questions")

    # A fresh HR database from the CSVs: leave booked in the app (the
    # agent can write now) would change the answers.
    print("Rebuilding the HR database:")
    runpy.run_path(str(PROJECT_ROOT / "build_hr_db.py"),
                   run_name="__main__")

    judge = build_judge()
    rows, failed = [], []
    start = time.perf_counter()
    with open(output_file, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for index, item in enumerate(questions, start=1):
            print(f"[{index}/{len(questions)}] {item['id']} "
                  f"{item['employee_id']}: {item['question']}")
            try:
                run = run_agent(item, args.provider, args.model, thinking)
                row = evaluate(item, run, judge)
            except Exception as error:  # keep going; report at the end
                print(f"    FAILED: {error}")
                failed.append(item["id"])
                continue
            print(f"    {row['total_score']}/6 · tools {row['tools_ok']}"
                  f" ({row['tools_called'] or 'none'}) · "
                  f"{row['seconds']} s · {row['generated_answer'][:90]}")
            rows.append(row)
            writer.writerow(row)
            file.flush()  # keep the file current during a long run

    print_summary(rows, failed)
    minutes = (time.perf_counter() - start) / 60
    print(f"\nTook {minutes:.1f} minutes (agent + judge)")
    print(f"Per-question results: {output_file}")


def print_summary(rows: list[dict], failed: list[str]) -> None:
    """Answer score, tool score and cost: overall and per category."""
    total = len(rows)
    if not total:
        print("\nNo questions were scored.")
        return

    def percent(group: list[dict]) -> float:
        return sum(r["total_score"] for r in group) / (6 * len(group)) * 100

    tools_ok = sum(r["tools_ok"] == "yes" for r in rows)
    perfect = sum(r["total_score"] == 6 for r in rows)
    print(f"\nScored {total} questions ({len(failed)} failed: "
          f"{', '.join(failed) or 'none'})")
    print(f"  answers       : {percent(rows):.1f}%  "
          f"({perfect}/{total} perfect, 6/6)")
    print(f"  tools         : {tools_ok}/{total} called every tool needed")
    for field in ("model_calls", "tool_calls", "seconds"):
        average = sum(float(r[field]) for r in rows) / total
        print(f"  {field:14}: {average:.1f} per question")

    groups = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)
    print("\nBy category:")
    for name, group in groups.items():
        ok = sum(r["tools_ok"] == "yes" for r in group)
        print(f"  {name:12} answers {percent(group):5.1f}% · tools "
              f"{ok}/{len(group)} · {len(group)} questions")

    misses = [r for r in rows
              if r["total_score"] < 6 or r["tools_ok"] == "no"]
    if misses:
        print("\nNot perfect:")
        for r in misses:
            missing = (f" · missing {r['missing_tools']}"
                       if r["missing_tools"] else "")
            print(f"  {r['id']:4} {r['total_score']}/6{missing}")


if __name__ == "__main__":
    main()
