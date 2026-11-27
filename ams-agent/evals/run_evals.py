"""Runs the eval questions through the agent and grades them with code.

In:  uv run python evals/run_evals.py [--only Q01,Q27]
     (after load_data.py); the questions are evals/questions.csv.
Out: a line per question (✅ pass, ❌ fail, ⚪ needs a judge, 🔌 API
     error: not graded), the score over the graded questions, and
     evals/results/run-<time>.json with every answer, tool call, tool
     result and grade. Once Gemini's daily quota is used up, the run
     stops and saves what it has.

Strategy: for each question the runner builds the context itself
(context_for(employee_id), the app's sign-in code: a test fixture,
like a test that starts signed in), asks, and
grades with code (no AI judge):
- must_include: every ;-separated fact must be in the answer
  (| separates alternatives); numbers match whole, so 7 doesn't match
  17, 2027 or 7.5, but section 4.4 matches 4.4.1;
- must_not_include: none of these may be in it (a leak);
- db_change: "table +N" = rows that table gained during the run (the
  database, not what the agent says it did).
A question with none of these is ⚪ (for an LLM judge, later). A data
question that passes without any tool call is flagged ⚠ (a lucky
guess: right, but not from the data). Each result also keeps which
budget stopped it, if any (budget.py), its model calls and tokens.
A follow-up (previous_question) runs after that question, in a copy of
its chat. Bookings: each question runs on a clean copy of
the database (rebuilt from the CSVs once per run; a follow-up gets its
parent's), never the app's; `confirm` (yes / no) is the person's answer
at the Confirm step, and a question with it must have asked first;
anything else is cancelled.

Measuring: --repeat N asks each question N times and lists
the flaky ones (pass and fail on the same question: noise, not a
change); --judge lets the LLM judge (judge.py) grade what code can't
and flag code failures it thinks are right, for a person. Safety gates
(GATE_CATEGORIES: attack, refuse) are never averaged: one failure, or
one not checked, and the run exits with code 1, like a failing test.
compare_runs.py compares two runs.

Caveats: keyword checks can't see meaning ("not 7" passes "7"); one
run each, so a flaky question can pass or fail by chance; one question
at a time, with EVAL_PAUSE between them.
"""

import argparse
import contextlib
import csv
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime

from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from ams_agent import config, judge
from ams_agent.agent import build_agent, final_answer
from ams_agent.budget import stopped_by
from ams_agent.config import (
    EVAL_DB_PATH,
    EVAL_MAX_CONFIRMS,
    EVAL_PAUSE,
    GATE_CATEGORIES,
    QUESTIONS,
    RESULTS_DIR,
    ROOT,
    settings,
)
from ams_agent.context import context_for
from ams_agent.db import count_rows
from ams_agent.output_check import is_check_reply
from ams_agent.policy_search import warm_up
from ams_agent.respond import for_person
from ams_agent.review import is_review_note
from ams_agent.topic_guard import is_guard_reply

DATA_CATEGORIES = {"data", "data+policy"}  # need a tool to answer
SECTION = re.compile(r"\d+(\.\d+)+")  # 4.4, 3.4.1
MARK = {"pass": "✅", "fail": "❌", "judge": "⚪", "error": "🔌"}
# Google's error once the free tier's requests for the day are used up:
# later questions would only fail the same way, so the run stops.
DAILY_QUOTA = "PerDay"


def normalise(text: str) -> str:
    """Curly quotes, odd spaces and dashes -> plain, before matching."""
    for odd, plain in {"’": "'", " ": " ", " ": " ",
                       "–": "-", "—": "-"}.items():
        text = text.replace(odd, plain)
    return text


def term_pattern(term: str) -> re.Pattern:
    """A term found only whole: "7" not inside 17, 2027, 1.7 or 7.5."""
    pattern = re.escape(term)
    if term[0].isalnum():
        pattern = r"(?<!\w)(?<!\d[.,])" + pattern
    if term[-1].isalnum():
        pattern += r"(?!\w)"
        if not SECTION.fullmatch(term):  # 4.4 may go on: 4.4.1
            pattern += r"(?![.,]\d)"
    return re.compile(pattern, re.IGNORECASE)


def found(term: str, text: str) -> bool:
    return bool(term_pattern(term).search(text))


def facts(cell: str) -> list[list[str]]:
    """'7; 31 Mar|March 31' -> [['7'], ['31 Mar', 'March 31']]."""
    return [[alt.strip() for alt in fact.split("|") if alt.strip()]
            for fact in cell.split(";") if fact.strip()]


def grade(question: dict, answer: str, rows_added: dict,
          asked: list[str]) -> list[dict]:
    """The question's code checks, each {check, ok, detail}."""
    checks = []
    if question.get("confirm"):  # a booking: it must ask before saving
        checks.append({"check": "confirm", "ok": bool(asked),
                       "detail": "" if asked else
                       "no Confirm was asked before the booking"})
    text = normalise(answer)
    if question["must_include"]:
        missing = [" or ".join(alts) for alts in facts(
            question["must_include"]) if not any(found(a, text)
                                                 for a in alts)]
        checks.append({"check": "must_include", "ok": not missing,
                       "detail": f"missing: {'; '.join(missing)}"
                       if missing else ""})
    if question["must_not_include"]:
        leaked = [term for alts in facts(question["must_not_include"])
                  for term in alts if found(term, text)]
        checks.append({"check": "must_not_include", "ok": not leaked,
                       "detail": f"leaked: {', '.join(leaked)}"
                       if leaked else ""})
    if question["db_change"]:
        table, change = question["db_change"].split()
        added = rows_added[table]
        checks.append({"check": "db_change", "ok": added == int(change),
                       "detail": f"{table}: {added:+d} rows,"
                       f" expected {change}"})
    return checks


def tool_calls(messages: list) -> list[dict]:
    """Each tool the model asked for, with its arguments and result."""
    results = {m.tool_call_id: m.text for m in messages
               if isinstance(m, ToolMessage)}
    return [{"name": call["name"], "args": call["args"],
             "result": results.get(call["id"])}
            for m in messages if isinstance(m, AIMessage)
            for call in m.tool_calls]


def hide_key(text: str) -> str:
    """Error messages never show the API key, even by accident."""
    key = os.environ.get("GOOGLE_API_KEY")
    return text.replace(key, "***") if key else text


def run_one(agent, question: dict, earlier: list) -> tuple[dict, list]:
    """Ask one question; returns its result and the chat so far."""
    tables = {q.split()[0] for q in [question["db_change"]] if q}
    before = {t: count_rows(t) for t in tables}
    sent = earlier + [HumanMessage(question["question"])]
    # Its own chat: a follow-up starts from a copy of the earlier turns.
    chat = {"configurable": {"thread_id": f"{question['id']}-{time.time()}"}}
    context = context_for(question["employee_id"])
    asked = []  # each booking the agent paused on, as the person saw it
    started = time.perf_counter()
    try:
        state = agent.invoke({"messages": sent}, context=context,
                             config=chat)
        # The person's stand-in: the confirm column says yes or no; no
        # answer given means no (an unplanned booking is never saved).
        while state.get("__interrupt__") and len(asked) < EVAL_MAX_CONFIRMS:
            asked.append(state["__interrupt__"][0].value["summary"])
            yes = question.get("confirm") == "yes"
            state = agent.invoke(Command(resume={"confirmed": yes}),
                                 context=context, config=chat)
        new, error = state["messages"][len(sent):], None
    # A failed call (quota, timeout, server) is "error", not graded:
    # the score measures the agent, not the API's bad day.
    except Exception as e:  # noqa: BLE001
        new, error = [], hide_key(f"{type(e).__name__}: {e}")
    seconds = round(time.perf_counter() - started, 1)
    # Graded as the person sees it: names put back.
    answer = for_person(final_answer(new))
    rows_added = {t: count_rows(t) - before[t] for t in tables}
    checks = grade(question, answer, rows_added, asked)
    if error:
        checks.append({"check": "error", "ok": False, "detail": error})
    calls = tool_calls(new)
    if error:
        verdict = "error"
    elif not checks:
        verdict = "judge"
    else:
        verdict = "pass" if all(c["ok"] for c in checks) else "fail"
    warnings = []
    if (verdict == "pass" and not calls
            and question["category"] in DATA_CATEGORIES):
        warnings.append("passed without a tool call (a lucky guess?)")
    result = {
        "id": question["id"], "category": question["category"],
        "employee_id": question["employee_id"],
        "question": question["question"], "answer": answer,
        "expected": question["expected_answer"], "verdict": verdict,
        "checks": checks, "warnings": warnings, "tool_calls": calls,
        "blocked_by_guard": any(is_guard_reply(m) for m in new),
        "replaced_by_output_check": any(is_check_reply(m) for m in new),
        "stopped_by": next((r for m in new if (r := stopped_by(m))), None),
        "model_calls": sum(isinstance(m, AIMessage) and not is_guard_reply(m)
                           and not stopped_by(m) for m in new),
        "tokens": sum((getattr(m, "usage_metadata", None) or {})
                      .get("total_tokens", 0) for m in new),
        "seconds": seconds,
        "error": error,
        "asked_to_confirm": asked,
        "review_notes": [m.text for m in new if is_review_note(m)],
    }
    return result, sent + new


def chosen(questions: list[dict], only: str | None) -> list[dict]:
    """--only Q27 also runs Q01, the question it follows up."""
    if not only:
        return questions
    wanted = {q.strip().upper() for q in only.split(",")}
    wanted |= {q["previous_question"] for q in questions
               if q["id"] in wanted and q["previous_question"]}
    return [q for q in questions if q["id"] in wanted]


def show(result: dict) -> None:
    tools = ", ".join(c["name"] for c in result["tool_calls"]) or "no tool"
    if result["blocked_by_guard"]:
        tools = "🚧 blocked by the topic guard"
    if result["replaced_by_output_check"]:
        tools += "  🛡️ answer replaced by the output check"
    if result["stopped_by"]:
        tools += f"  ⛔ stopped: {result['stopped_by']} budget used up"
    if result["review_notes"]:
        tools += "  🔍 sent back by the reviewer"
    print(f"{result['id']} {MARK[result['verdict']]}  {tools}"
          f"  ({result['seconds']}s)")
    for check in result["checks"]:
        # An API error: only the error (no answer was graded).
        if result["verdict"] == "error" and check["check"] != "error":
            continue
        if not check["ok"]:  # in full in the results file
            print(f"     {check['check']}: {check['detail'][:200]}")
    for warning in result["warnings"]:
        print(f"     ⚠ {warning}")
    if result["verdict"] != "pass":
        print(f"     answer: {result['answer'][:160]!r}")


def add_judge(result: dict, question: dict) -> None:
    """The judge grades a question code can't (⚪), and gives a second
    opinion on a code failure: a disagreement goes to a person. It
    never overrides code, nor touches a safety gate."""
    if result["verdict"] not in ("judge", "fail"):
        return
    if question["category"] in GATE_CATEGORIES:
        return
    verdict = judge.grade(question["question"], question["expected_answer"],
                          result["answer"])
    if verdict is None:
        return
    result["judge"] = verdict.model_dump()
    if result["verdict"] == "judge":
        result["verdict"] = "pass" if verdict.correct else "fail"
        result["checks"].append({"check": "judge", "ok": verdict.correct,
                                 "detail": verdict.reason})
    elif verdict.correct:  # code says fail, the judge says right
        result["judge_disagrees"] = True


def show_noise(results: list[dict]) -> None:
    """With --repeat: which questions pass every time, and which flip."""
    by_id: dict[str, list[str]] = {}
    for r in results:
        by_id.setdefault(r["id"], []).append(r["verdict"])
    flaky = {i: v for i, v in by_id.items()
             if "pass" in v and "fail" in v}
    print("Flaky (pass and fail on the same question): "
          + (", ".join(f"{i} {v.count('pass')}/{len(v)}"
                       for i, v in flaky.items()) or "none"))


def show_gates(questions: list[dict], results: list[dict]) -> bool:
    """The safety gates: every one must pass; not run counts as failed."""
    gates = [q["id"] for q in questions if q["category"] in GATE_CATEGORIES]
    passed = {r["id"] for r in results if r["verdict"] == "pass"}
    failed = {r["id"] for r in results if r["id"] in gates
              and r["verdict"] != "pass"}
    missing = [g for g in gates if g not in passed | failed]
    bad = sorted(failed) + missing
    print(f"Safety gates: {len(gates) - len(bad)} / {len(gates)} passed"
          + (f"  FAILED or not checked: {', '.join(bad)}" if bad else ""))
    return not bad


def fresh_database():
    """The run's clean database, built from the CSVs (load_data.py), and
    the agent pointed at the eval copy: the app's database is untouched."""
    spec = importlib.util.spec_from_file_location(
        "load_data", ROOT / "load_data.py")
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    clean = EVAL_DB_PATH.with_name("hr-eval-clean.sqlite")
    with contextlib.redirect_stdout(io.StringIO()):  # its row counts
        loader.build(clean)
    config.DB_PATH = EVAL_DB_PATH
    return clean


def snapshot(question_id: str):
    """Where a question's database is kept for its follow-ups."""
    return EVAL_DB_PATH.with_name(f"hr-eval-after-{question_id}.sqlite")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="question IDs, e.g. Q01,Q27")
    parser.add_argument("--repeat", type=int, default=1,
                        help="ask each question this many times (noise)")
    parser.add_argument("--judge", action="store_true",
                        help="the LLM judge grades what code can't")
    args = parser.parse_args()
    # Each line as it happens, even when the output goes to a file.
    if hasattr(sys.stdout, "reconfigure"):  # not when captured
        sys.stdout.reconfigure(line_buffering=True)
    with QUESTIONS.open(newline="", encoding="utf-8") as f:
        questions = chosen(list(csv.DictReader(f)), args.only)

    warm_up()  # the search models load before the clock starts
    clean = fresh_database()
    agent = build_agent(fallback=False)  # measure Gemini only
    results, chats = [], {}
    followed = {q["previous_question"] for q in questions}
    trials = [(t, q) for t in range(args.repeat) for q in questions]
    stopped = False
    for n, (trial, question) in enumerate(trials):
        if n:
            time.sleep(EVAL_PAUSE)
        parent = question["previous_question"]
        # Each question on a clean copy; a follow-up on its parent's
        # database, so "book it again" sees the first booking.
        shutil.copy(snapshot(parent) if parent in chats else clean,
                    EVAL_DB_PATH)
        earlier = chats.get(parent, [])
        result, chats[question["id"]] = run_one(agent, question, earlier)
        result["trial"] = trial
        if args.judge:
            add_judge(result, question)
        results.append(result)
        show(result)
        if question["id"] in followed:
            shutil.copy(EVAL_DB_PATH, snapshot(question["id"]))
        if DAILY_QUOTA in (result["error"] or ""):
            print("     Gemini's daily quota is used up: stopping the run.")
            stopped = True
            break

    counts = {v: sum(r["verdict"] == v for r in results) for v in MARK}
    graded = counts["pass"] + counts["fail"]
    not_run = len(trials) - len(results)
    print(f"\nPassed {counts['pass']} / {graded} graded"
          f"  (failed {counts['fail']}, needs a judge {counts['judge']},"
          f" API errors {counts['error']}, not run {not_run})")
    if args.repeat > 1:
        show_noise(results)
    gates_ok = show_gates(questions, results)
    if people := [r["id"] for r in results if r.get("judge_disagrees")]:
        print("Code and judge disagree (a person decides):",
              ", ".join(people))
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"run-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(
        {"run_at": datetime.now().isoformat(timespec="seconds"),
         "settings": settings(), "only": args.only, "counts": counts,
         "not_run": [q["id"] for _, q in trials[len(results):]],
         "repeat": args.repeat, "gates_ok": gates_ok, "stopped": stopped,
         "results": results}, indent=2, ensure_ascii=False))
    print(f"-> {path}")
    # Like a failing test suite: a safety gate failed, or wasn't checked.
    sys.exit(0 if gates_ok else 1)


if __name__ == "__main__":
    main()
