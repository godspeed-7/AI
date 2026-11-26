"""Runs the eval questions through the agent and grades them with code.

In:  uv run python evals/run_evals.py [--only Q01,Q27]
     (after load_data.py); the questions are evals/questions.csv.
Out: a line per question (✅ pass, ❌ fail, ⚪ needs a judge), the
     score, and evals/results/run-<time>.json with every answer, tool
     call, tool result and grade.

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
guess: right, but not from the data).
A follow-up (previous_question) runs after that question, in its chat.

Caveats: keyword checks can't see meaning ("not 7" passes "7"); one
run each, so a flaky question can pass or fail by chance; one question
at a time, with EVAL_PAUSE between them.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime

from langchain.messages import AIMessage, HumanMessage, ToolMessage

from ams_agent.agent import build_agent, final_answer
from ams_agent.config import AGENT_MODEL, EVAL_PAUSE, QUESTIONS, RESULTS_DIR
from ams_agent.context import context_for
from ams_agent.db import count_rows
from ams_agent.output_check import is_check_reply
from ams_agent.topic_guard import is_guard_reply

DATA_CATEGORIES = {"data", "data+policy"}  # need a tool to answer
SECTION = re.compile(r"\d+(\.\d+)+")  # 4.4, 3.4.1
MARK = {"pass": "✅", "fail": "❌", "judge": "⚪"}


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


def grade(question: dict, answer: str, rows_added: dict) -> list[dict]:
    """The question's code checks, each {check, ok, detail}."""
    checks = []
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
    started = time.perf_counter()
    try:
        state = agent.invoke({"messages": sent},
                             context=context_for(question["employee_id"]))
        new, error = state["messages"][len(sent):], None
    # Any failure is recorded as a fail, and the run goes on.
    except Exception as e:  # noqa: BLE001
        new, error = [], hide_key(f"{type(e).__name__}: {e}")
    seconds = round(time.perf_counter() - started, 1)
    answer = final_answer(new)
    rows_added = {t: count_rows(t) - before[t] for t in tables}
    checks = grade(question, answer, rows_added)
    if error:
        checks.append({"check": "error", "ok": False, "detail": error})
    calls = tool_calls(new)
    if not checks:
        verdict = "judge"
    else:
        verdict = "pass" if all(c["ok"] for c in checks) else "fail"
    warnings = []
    if (verdict == "pass" and not calls
            and question["category"] in DATA_CATEGORIES):
        warnings.append("passed without a tool call (a lucky guess?)")
    result = {
        "id": question["id"], "employee_id": question["employee_id"],
        "question": question["question"], "answer": answer,
        "expected": question["expected_answer"], "verdict": verdict,
        "checks": checks, "warnings": warnings, "tool_calls": calls,
        "blocked_by_guard": any(is_guard_reply(m) for m in new),
        "replaced_by_output_check": any(is_check_reply(m) for m in new),
        "model_calls": sum(isinstance(m, AIMessage) for m in new),
        "seconds": seconds,
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
    print(f"{result['id']} {MARK[result['verdict']]}  {tools}"
          f"  ({result['seconds']}s)")
    for check in result["checks"]:
        if not check["ok"]:  # in full in the results file
            print(f"     {check['check']}: {check['detail'][:200]}")
    for warning in result["warnings"]:
        print(f"     ⚠ {warning}")
    if result["verdict"] != "pass":
        print(f"     answer: {result['answer'][:160]!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="question IDs, e.g. Q01,Q27")
    args = parser.parse_args()
    # Each line as it happens, even when the output goes to a file.
    sys.stdout.reconfigure(line_buffering=True)
    with QUESTIONS.open(newline="", encoding="utf-8") as f:
        questions = chosen(list(csv.DictReader(f)), args.only)

    agent = build_agent()
    results, chats = [], {}
    for n, question in enumerate(questions):
        if n:
            time.sleep(EVAL_PAUSE)
        earlier = chats.get(question["previous_question"], [])
        result, chats[question["id"]] = run_one(agent, question, earlier)
        results.append(result)
        show(result)

    counts = {v: sum(r["verdict"] == v for r in results) for v in MARK}
    print(f"\nPassed {counts['pass']} / {len(results)}"
          f"  (failed {counts['fail']}, needs a judge {counts['judge']})")
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"run-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(
        {"run_at": datetime.now().isoformat(timespec="seconds"),
         "model": AGENT_MODEL, "only": args.only, "counts": counts,
         "results": results}, indent=2, ensure_ascii=False))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
