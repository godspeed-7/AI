"""Agent evaluation: run every agent question and score it (stage C).

In:  ams-data/agent_questions.csv (who asks, the question, the expected
     answer, the tools it must use; for a chat, the message before it:
     previous_question; for an action question, the request it must
     save: expected_request = "type start end") and the agent's model:
     config.py's, or --provider / --model / --thinking to compare
     others.
Out: evals/agent_results_<model>.csv (one row per question, written as
     the run goes) and a summary: answer score, tool score, actions,
     cost.

Strategy: per question, build_agent() (agent.py, the same agent as
chat.py and the app) answers as that employee. A chat (category
"chat") is two messages in one conversation, as in the app: the
earlier one first, answered but not scored, then the question, whose
reply is scored (the judge sees both messages). Four scores:
- answer: the judge (judge.py), 0-6, with the sign-in facts (about(),
  agent.py) and every tool result as its "retrieved context";
- tools: were all the tools the question needs called? (code, no LLM;
  extra calls aren't penalised, only counted; "a|b" in required_tools
  means either will do);
- actions (action questions only): it answers "Confirm?" with yes, as
  the person would; then code reads the database: asked first, and
  exactly one new request saved, the expected one, pending;
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
  With action questions it rebuilds it again at the end, so their
  bookings don't stay.
- Replies and grades are cached (llm_cache.py): a rerun only calls the
  models for questions whose input changed.
- Hosted seconds include Google's pacing (GOOGLE_CALLS_PER_MINUTE).
- Questions run one at a time (one local model at a time on this Mac).
- A question that fails is logged and skipped, so a run isn't lost.
- Booking leave pauses to ask the person (Confirm?). An action
  question confirms (with the chat's memory, without saved
  preferences); any other question doesn't, so the answer recorded is
  that question, and nothing is saved.
- A chat's tools, calls and seconds count both messages: a tool used
  for the earlier one counts for the question too.
- With LANGFUSE_TRACING (config.py), each question's agent run is
  recorded in Langfuse ("eval <id>", tagged with the model;
  tracing.py); the judge's calls aren't.
"""

import argparse
import csv
import runpy
import time
import uuid
from collections import defaultdict
from contextlib import closing

from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from ams_assistant.agent import about, build_agent, split_thinking
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
from ams_assistant.hr_tools import HRContext, connect, get_employee_card
from ams_assistant.judge import build_judge
from ams_assistant.tracing import run_config

FIELDNAMES = [
    "id", "category", "employee_id", "previous_question", "question",
    "expected_answer",
    "required_tools", "expected_request", "tools_called",
    "missing_tools", "tools_ok", "actions", "actions_ok",
    "generated_answer", "correctness", "context_support", "completeness",
    "total_score", "explanation", "model_calls", "tool_calls", "seconds",
]


def collect_steps(agent, item: dict, message: str, config: dict,
                  confirm: bool) -> tuple[list, bool, str | None, bool]:
    """Run the agent on one message of the item's chat, collecting the
    messages step by step, so a run that stops early still shows which
    tools it called. At a pause (booking asks "Confirm?"): with
    `confirm`, say yes and carry on, as the person would; otherwise
    the run ends there, and nothing is saved. Returns the messages,
    whether the call limit stopped it, what a paused tool asked (None
    if nothing) and whether the run ended at that question."""
    messages, asked = [], None
    agent_input = {"messages": [HumanMessage(message)]}
    try:
        while True:
            pauses = stream_once(agent, agent_input, item, config, messages)
            if not pauses:
                return messages, False, asked, False
            asked = pauses[0].value["question"]
            if not confirm:
                return messages, False, asked, True
            # The same reply as the app's Confirm button (app.py).
            agent_input = Command(resume=dict.fromkeys(
                [pause.id for pause in pauses], "confirm"))
    except ModelCallLimitExceededError:
        return messages, True, asked, False


def stream_once(agent, agent_input, item: dict, config: dict,
                messages: list) -> list:
    """One agent.stream() (a question, or a reply to a pause): its
    messages go into `messages`; returns its pauses (none if none)."""
    pauses = []
    for step in agent.stream(
        agent_input,
        context=HRContext(employee_id=item["employee_id"]),
        config=config,
        stream_mode="updates",
    ):
        for node, update in step.items():
            if node == "__interrupt__":  # a tool asks the person
                pauses.extend(update)
            else:
                messages.extend((update or {}).get("messages", []))
    return pauses


def leave_requests(employee_id: str) -> dict[str, dict]:
    """Their leave requests in the HR database, by request ID."""
    with closing(connect()) as db:
        rows = db.execute("SELECT * FROM leave_requests "
                          "WHERE employee_id = ?", (employee_id,))
        return {row["request_id"]: dict(row) for row in rows}


def run_agent(item: dict, provider: str, model: str,
              thinking: bool) -> dict:
    """Answer one question (a chat: both messages) as its employee;
    return what happened."""
    # An action question answers "Confirm?" and a chat's question
    # follows the earlier message: both need the chat's memory (a run
    # carries on from it); never their saved preferences, so the
    # instructions are the same every run.
    confirm = item["category"] == "action"
    turns = [m for m in (item.get("previous_question"), item["question"])
             if m]
    memory = confirm or len(turns) > 1
    # No fallback: a failed call stays a failure, so a score is one
    # model's.
    agent = build_agent(item["employee_id"], provider, model, thinking,
                        fallback=False, memory=memory, preferences=False)
    # With LANGFUSE_TRACING: the run in Langfuse, as "eval <id>"; a
    # confirmed booking or a chat is two runs, in one session.
    chat = f"eval {item['id']} {uuid.uuid4().hex[:8]}" if memory else None
    config = run_config(item["employee_id"], "eval", thread_id=chat,
                        session_id=chat, trace_name=f"eval {item['id']}",
                        tags=(model,))
    before = leave_requests(item["employee_id"])
    start = time.perf_counter()
    messages, stopped, asked, paused = [], False, None, False
    for turn in turns:
        new, stopped, asked, paused = collect_steps(agent, item, turn,
                                                    config, confirm)
        messages += new
        if stopped or paused:  # the chat can't go on
            break
    seconds = time.perf_counter() - start
    after = leave_requests(item["employee_id"])

    replies = [m for m in messages if isinstance(m, AIMessage)]
    results = [m for m in messages if isinstance(m, ToolMessage)]
    if paused:
        answer = f"(paused to ask them: {asked})"
    elif stopped or not replies:
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
        "asked": asked,
        "saved": [row for key, row in after.items() if key not in before],
    }


def check_actions(item: dict, run: dict) -> tuple[str, str]:
    """For an action question (expected_request = "type start end"):
    did it ask "Confirm?" first, then save exactly that request,
    pending? Returns ("yes" or "no", what happened); ("", "") for
    other questions."""
    if not item.get("expected_request"):
        return "", ""
    expected = (*item["expected_request"].split(), "pending")
    done = ["asked to confirm" if run["asked"] else "never asked"]
    done += [f"saved {r['request_id']}: {r['leave_type']} "
             f"{r['start_date']} to {r['end_date']}, {r['status']}"
             for r in run["saved"]] or ["nothing saved"]
    ok = (run["asked"] is not None and len(run["saved"]) == 1
          and tuple(run["saved"][0][key] for key in (
              "leave_type", "start_date", "end_date", "status")) == expected)
    return ("yes" if ok else "no"), "; ".join(done)


def evaluate(item: dict, run: dict, judge) -> dict:
    """Score one run: the judge for the answer, code for the tools and
    the actions."""
    # A chat's question ("How much did it cost?") needs the message
    # before it to make sense, to the judge too.
    question = item["question"]
    if item.get("previous_question"):
        question = (f"(Earlier in the chat: {item['previous_question']})"
                    f"\n{question}")
    scores = judge.invoke({
        "question": question,
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
    actions_ok, actions = check_actions(item, run)
    return {
        **{key: item[key] for key in ("id", "category", "employee_id",
                                      "previous_question", "question",
                                      "expected_answer", "required_tools",
                                      "expected_request")},
        "tools_called": "; ".join(run["called"]),
        "missing_tools": "; ".join(missing),
        "tools_ok": "no" if missing else "yes",
        "actions": actions,
        "actions_ok": actions_ok,
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
    try:
        with open(output_file, "w", encoding="utf-8",
                  newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()
            for index, item in enumerate(questions, start=1):
                print(f"[{index}/{len(questions)}] {item['id']} "
                      f"{item['employee_id']}: {item['question']}")
                try:
                    run = run_agent(item, args.provider, args.model,
                                    thinking)
                    row = evaluate(item, run, judge)
                except Exception as error:  # keep going; report at end
                    print(f"    FAILED: {error}")
                    failed.append(item["id"])
                    continue
                actions = (f" · actions {row['actions_ok']}"
                           if row["actions_ok"] else "")
                print(f"    {row['total_score']}/6 · tools "
                      f"{row['tools_ok']} ({row['tools_called'] or 'none'})"
                      f"{actions} · {row['seconds']} s · "
                      f"{row['generated_answer'][:90]}")
                rows.append(row)
                writer.writerow(row)
                file.flush()  # keep the file current during a long run
    finally:
        # Action questions saved requests: back to the CSVs' data.
        if any(item["category"] == "action" for item in questions):
            print("Rebuilding the HR database (undoing the bookings):")
            runpy.run_path(str(PROJECT_ROOT / "build_hr_db.py"),
                           run_name="__main__")

    print_summary(rows, failed)
    minutes = (time.perf_counter() - start) / 60
    print(f"\nTook {minutes:.1f} minutes (agent + judge)")
    print(f"Per-question results: {output_file}")


def print_summary(rows: list[dict], failed: list[str]) -> None:
    """Answer score, tool score, actions and cost: overall and per
    category."""
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
    acted = [r for r in rows if r["actions_ok"]]
    if acted:
        done = sum(r["actions_ok"] == "yes" for r in acted)
        print(f"  actions       : {done}/{len(acted)} did exactly what "
              f"was asked (confirmed, saved, pending)")
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
    print_misses(rows)


def print_misses(rows: list[dict]) -> None:
    """The questions with a score below 6, a missing tool or a wrong
    action, and what went wrong."""
    misses = [r for r in rows
              if r["total_score"] < 6 or r["tools_ok"] == "no"
              or r["actions_ok"] == "no"]
    if misses:
        print("\nNot perfect:")
    for r in misses:
        missing = (f" · missing {r['missing_tools']}"
                   if r["missing_tools"] else "")
        actions = (f" · actions: {r['actions']}"
                   if r["actions_ok"] == "no" else "")
        print(f"  {r['id']:4} {r['total_score']}/6{missing}{actions}")


if __name__ == "__main__":
    main()
