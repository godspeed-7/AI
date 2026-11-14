"""Agent evaluation: run every agent question and score it (stage C).

In:  ams-data/agent_questions.csv (who asks, the question, the expected
     answer, the tools it must use; for a chat, the message before it:
     previous_question; for an action question, the request it must
     save: expected_request = "type start end") and the agent's model:
     config.py's, or --provider / --model / --thinking to compare
     others.
Out: evals/agent_results_<model>.csv (one row per question, written as
     the run goes) and a summary: answer score, tool score, actions,
     cost. With LANGFUSE_TRACING, also an experiment in Langfuse: the
     run as one row, each question's trace with its scores, so runs
     can be compared (EVAL_PLAYBOOK.md, B6). --repeat N (B8): each try
     is a run; agent_results_<model>_repeatN.csv (a row per question
     per try) and which questions pass every try (pass^N), are flaky,
     or never pass.

Strategy: Langfuse's run_experiment goes through the questions:
task() runs the agent on one, grade() scores it. Per question,
build_agent() (agent.py, the same agent as
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
  exactly one new request saved, the expected one, pending; and the
  reply doesn't call it approved (C2);
- cost: model calls, tool calls and seconds (the agent only, not the
  judge).

Usage (from ams-assistant/):
    uv run python evals/evaluate_agent.py --limit 3    # quick check
    uv run python evals/evaluate_agent.py              # config's model
    uv run python evals/evaluate_agent.py --thinking off
    uv run python evals/evaluate_agent.py --provider google \\
        --model gemini-3.5-flash-lite
    uv run python evals/evaluate_agent.py --only X2,X3 # some questions
    uv run python evals/evaluate_agent.py --repeat 3   # each 3 times

Caveats:
- Starts by rebuilding the HR database from the CSVs (build_hr_db.py),
  so every run sees the same data: leave booked in the app is wiped.
  With action questions it rebuilds it again at the end, so their
  bookings don't stay.
- Replies and grades are cached (llm_cache.py): a rerun only calls the
  models for questions whose input changed. Not with --repeat: the
  agent asks afresh every try (the judge's grades stay cached), so it
  costs N full runs; the HR database is rebuilt before each try.
- Hosted seconds include Google's pacing (GOOGLE_CALLS_PER_MINUTE).
- Questions run one at a time (one local model at a time on this Mac).
- A question that fails is logged and skipped, so a run isn't lost.
- Booking leave pauses to ask the person (Confirm?). An action
  question confirms (with the chat's memory, without saved
  preferences); any other question doesn't, so the answer recorded is
  that question, and nothing is saved.
- A chat's tools, calls and seconds count both messages: a tool used
  for the earlier one counts for the question too.
- The experiment's run is named after the model, the prompt version
  and the code version (git commit; "+changes" = not committed):
  commit before a run you want to keep. Each question is one trace,
  "eval <id>", tagged with the model (tracing.py); the judge's model
  calls aren't traced, only its grade.
"""

import argparse
import csv
import re
import runpy
import time
import uuid
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path

from langchain.agents.middleware.model_call_limit import (
    ModelCallLimitExceededError,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langfuse import Evaluation
from langgraph.types import Command

from ams_assistant.agent import (
    about,
    agent_prompt,
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
from ams_assistant.hr_tools import HRContext, connect, get_employee_card
from ams_assistant.judge import build_judge
from ams_assistant.tracing import code_version, langfuse_client, run_config

# What the runs are, in each step's metadata in Langfuse; its
# Experiments page lists each run by its own name (run_name()).
EXPERIMENT_NAME = "agent eval"

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
              thinking: bool, cached: bool = True) -> dict:
    """Answer one question (a chat: both messages) as its employee;
    return what happened. cached=False: the agent asks its model afresh
    (repeat runs)."""
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
                        fallback=False, memory=memory, preferences=False,
                        cached=cached)
    # With LANGFUSE_TRACING: the steps go into the question's trace
    # (the experiment's), labelled "eval <id>"; a chat or a confirmed
    # booking has both its runs there, and a chat its session.
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


# A reply saying the leave is approved already: "has been approved",
# "it's now approved", "I've approved it" (C2)...
APPROVED_CLAIM = re.compile(
    r"\b(?:is|are|was|were|been|has|have|it['’]s|i['’]ve)\s+"
    r"(?:now\s+|already\s+|just\s+)?approved\b", re.IGNORECASE)
# ...but not one saying what will happen: "once it's approved", "after
# this is approved" (A1's reply), "as soon as Pooja has approved it".
NOT_YET = {"once", "when", "whenever", "after", "until", "till", "if",
           "unless", "before", "soon", "whether"}


def claims_approved(reply: str) -> bool:
    """Does the reply say the leave is approved already? A claim, not
    what will happen: "has been approved" yes, "once it's approved" no
    (a NOT_YET word earlier in the same sentence)."""
    for claim in APPROVED_CLAIM.finditer(reply):
        sentence = re.split(r"[.!?\n]", reply[:claim.start()])[-1]
        if not NOT_YET & set(re.findall(r"[a-z]+", sentence.lower())):
            return True
    return False


def check_actions(item: dict, run: dict) -> tuple[str, str]:
    """For an action question (expected_request = "type start end"):
    did it ask "Confirm?" first, then save exactly that request,
    pending, and not tell them it's approved? Returns ("yes" or "no",
    what happened); ("", "") for other questions."""
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
    # The database is right, but the reply mustn't claim more than it
    # (the course's refund "processed" while still pending).
    waiting = any(r["status"] == "pending" for r in run["saved"])
    if waiting and claims_approved(run["answer"]):
        done.append("reply says approved, but it's waiting")
        ok = False
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


def experiment_item(question: dict) -> dict:
    """A question as Langfuse shows it: what goes in, what should come
    out, and its labels. The same input in two runs is the same item,
    so they line up when compared."""
    asked = {"employee_id": question["employee_id"]}
    if question.get("previous_question"):
        asked["previous_question"] = question["previous_question"]
    asked["question"] = question["question"]
    expected = {"answer": question["expected_answer"],
                "required_tools": question["required_tools"]}
    if question.get("expected_request"):
        expected["request"] = question["expected_request"]
    return {"input": asked, "expected_output": expected,
            "metadata": {"id": question["id"],
                         "category": question["category"]}}


def scores(row: dict) -> list[Evaluation]:
    """A row's scores, saved on its trace: answer 0-6 (the judge),
    tools and actions yes = 1, no = 0 (code)."""
    tools = f"called: {row['tools_called'] or 'none'}"
    if row["missing_tools"]:
        tools += f"; missing: {row['missing_tools']}"
    found = [
        Evaluation(name="answer", value=row["total_score"],
                   comment=row["explanation"], data_type="NUMERIC"),
        Evaluation(name="tools", value=int(row["tools_ok"] == "yes"),
                   comment=tools, data_type="BOOLEAN"),
    ]
    if row["actions_ok"]:
        found.append(Evaluation(
            name="actions", value=int(row["actions_ok"] == "yes"),
            comment=row["actions"], data_type="BOOLEAN"))
    return found


class AgentExperiment:
    """One run of the eval, through Langfuse's run_experiment: task()
    runs the agent on a question, grade() scores what it did. Scored
    rows go into the results CSV as they come; failed questions are
    listed."""

    def __init__(self, questions: list[dict], args: argparse.Namespace,
                 thinking: bool, writer: csv.DictWriter, file,
                 attempt: int | None = None) -> None:
        self.questions = {q["id"]: q for q in questions}
        self.args, self.thinking = args, thinking
        self.writer, self.file = writer, file
        # A repeat run's try (None: a single run): its number goes into
        # each row, and the agent asks its model afresh.
        self.attempt = attempt
        self.judge = build_judge()
        self.started = 0
        self.rows: list[dict] = []
        self.failed: list[str] = []
        self.url: str | None = None  # the run's page in Langfuse

    def run(self, name: str, label: str) -> None:
        """Go through the questions as one experiment run, `name`."""
        result = langfuse_client().run_experiment(
            name=EXPERIMENT_NAME, run_name=name,
            description=f"{len(self.questions)} questions; judge "
                        f"{JUDGE_PROVIDER} {JUDGE_MODEL}",
            data=[experiment_item(q) for q in self.questions.values()],
            task=self.task, evaluators=[self.grade],
            max_concurrency=1,  # one question at a time, as before
            metadata={"model": f"{self.args.provider} {label}",
                      "code_version": code_version(),
                      "judge": f"{JUDGE_PROVIDER} {JUDGE_MODEL}"})
        self.url = result.experiment_url

    def task(self, *, item: dict, **_) -> dict:
        """Run the agent on one question (inside its trace)."""
        question = self.questions[item["metadata"]["id"]]
        self.started += 1
        print(f"[{self.started}/{len(self.questions)}] {question['id']} "
              f"{question['employee_id']}: {question['question']}")
        try:
            return run_agent(question, self.args.provider,
                             self.args.model, self.thinking,
                             cached=self.attempt is None)
        except Exception as error:  # keep going; report at the end
            self.fail(question, error)
            raise  # Langfuse marks the trace as failed

    def grade(self, *, output: dict, metadata: dict,
              **_) -> list[Evaluation]:
        """Score task()'s output; Langfuse saves the scores on the
        question's trace."""
        question = self.questions[metadata["id"]]
        try:
            row = evaluate(question, output, self.judge)
        except Exception as error:
            self.fail(question, error)
            raise
        if self.attempt:
            row = {"try": self.attempt, **row}
        print_row(row)
        self.rows.append(row)
        self.writer.writerow(row)
        self.file.flush()  # keep the file current during a long run
        return scores(row)

    def fail(self, question: dict, error: Exception) -> None:
        print(f"    FAILED: {error}")
        self.failed.append(question["id"])


def print_row(row: dict) -> None:
    """One scored question, under its "[n/N]" line."""
    actions = (f" · actions {row['actions_ok']}"
               if row["actions_ok"] else "")
    print(f"    {row['total_score']}/6 · tools {row['tools_ok']} "
          f"({row['tools_called'] or 'none'}){actions} · "
          f"{row['seconds']} s · {row['generated_answer'][:90]}")


def run_name(label: str) -> str:
    """The run's name in Langfuse: what made the agent behave as it did
    (model, prompt version, code version), and when."""
    prompt = agent_prompt()
    version = ("prompt: the code's copy" if prompt.is_fallback
               else f"prompt v{prompt.version}")
    return (f"{label} · {version} · code {code_version()} · "
            f"{datetime.now():%-d %b %H:%M}")


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
    parser.add_argument("--repeat", type=int, default=1, metavar="N",
                        help="run every question N times, the agent "
                             "asking afresh each time: which pass every "
                             "time, which are flaky (default 1)")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat needs 1 or more")

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
    if args.repeat > 1:  # its own file: the single run's stays as it is
        output_file = output_file.with_stem(
            f"{output_file.stem}_repeat{args.repeat}")
    print(f"Agent: {args.provider} {args.model} ({label}), "
          f"judge: {JUDGE_PROVIDER} {JUDGE_MODEL}, "
          f"{len(questions)} questions"
          + (f", {args.repeat} tries each" if args.repeat > 1 else ""))

    # A fresh HR database from the CSVs: leave booked in the app (the
    # agent can write now) would change the answers.
    rebuild_hr_db()
    start = time.perf_counter()
    runs = run_tries(questions, args, thinking, label, output_file)
    if len(runs) == 1:
        print_summary(runs[0].rows, runs[0].failed)
    else:
        print_repeats(runs)
    minutes = (time.perf_counter() - start) / 60
    print(f"\nTook {minutes:.1f} minutes (agent + judge)")
    print(f"Per-question results: {output_file}")
    for run in runs:
        if run.url:
            print(f"In Langfuse: {run.url}")


def rebuild_hr_db(why: str = "") -> None:
    """A fresh HR database from the CSVs (build_hr_db.py)."""
    print(f"Rebuilding the HR database{why}:")
    runpy.run_path(str(PROJECT_ROOT / "build_hr_db.py"),
                   run_name="__main__")


def run_tries(questions: list[dict], args: argparse.Namespace,
              thinking: bool, label: str,
              output_file: Path) -> list[AgentExperiment]:
    """Run the questions once, or args.repeat times (each try its own
    experiment run), writing every scored row to output_file."""
    repeat = args.repeat > 1
    name = run_name(label)
    actions = any(q["category"] == "action" for q in questions)
    runs = []
    try:
        with open(output_file, "w", encoding="utf-8",
                  newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=(["try"] if repeat else []) + FIELDNAMES)
            writer.writeheader()
            for attempt in range(1, args.repeat + 1):
                if attempt > 1 and actions:
                    # The last try's booking would change this one's
                    # answers (A1 again, D1's balance).
                    rebuild_hr_db(" (undoing the last try's bookings)")
                suffix = f" · try {attempt}/{args.repeat}" if repeat else ""
                print(f"\nExperiment run: {name}{suffix}")
                run = AgentExperiment(questions, args, thinking, writer,
                                      file, attempt if repeat else None)
                run.run(name + suffix, label)
                runs.append(run)
    finally:
        # Action questions saved requests: back to the CSVs' data.
        if actions:
            rebuild_hr_db(" (undoing the bookings)")
    return runs


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
              f"was asked (confirmed, saved, pending, not called "
              f"approved)")
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


def passed(row: dict) -> bool:
    """A pass: 6/6, every tool needed, and the action done (A1)."""
    return (row["total_score"] == 6 and row["tools_ok"] == "yes"
            and row["actions_ok"] != "no")


def outcome(row: dict) -> str:
    """One try in a few words, e.g. "5/6 missing a tool"."""
    words = f"{row['total_score']}/6"
    if row["tools_ok"] == "no":
        words += " missing a tool"
    if row["actions_ok"] == "no":
        words += " wrong action"
    return words


def print_repeats(runs: list[AgentExperiment]) -> None:
    """Each try's score, then how each question did across the tries:
    passed every try (pass^N, the τ-bench measure), some (flaky) or
    none. A question that failed with an error in a try is left out of
    those, and listed."""
    print(f"\n{len(runs)} tries:")
    percents = []
    for number, run in enumerate(runs, start=1):
        if not run.rows:
            print(f"  try {number}: nothing scored")
            continue
        percents.append(sum(r["total_score"] for r in run.rows)
                        / (6 * len(run.rows)) * 100)
        print(f"  try {number}: answers {percents[-1]:.1f}% · passed "
              f"{sum(map(passed, run.rows))}/{len(run.rows)} · failed: "
              f"{', '.join(run.failed) or 'none'}")
    if len(percents) > 1:
        print(f"  answers moved {max(percents) - min(percents):.1f} points "
              f"between tries (1-2 is noise)")

    tries = defaultdict(list)
    for run in runs:
        for row in run.rows:
            tries[row["id"]].append(row)
    every = {q: rows for q, rows in tries.items() if len(rows) == len(runs)}
    always = [q for q, rows in every.items() if all(map(passed, rows))]
    never = [q for q, rows in every.items() if not any(map(passed, rows))]
    flaky = [q for q in every if q not in always and q not in never]
    print(f"\npass^{len(runs)} (passed every try): "
          f"{len(always)}/{len(every)}")
    for title, ids in (("Flaky (passed some tries)", flaky),
                       ("Never passed", never)):
        if ids:
            print(f"{title}:")
        for q in ids:
            print(f"  {q:4} " + " · ".join(map(outcome, every[q])))
    left_out = sorted(set(runs[0].questions) - set(every))
    if left_out:
        print(f"Not scored in every try (an error): {', '.join(left_out)}")


if __name__ == "__main__":
    main()
