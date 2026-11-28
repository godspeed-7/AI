"""Runs the eval questions through the agent and grades them with code.

In:  uv run python evals/run_evals.py [--only Q01,Q27 | --smoke]
     [--repeat N] [--judge]; questions from evals/questions.csv.
Out: ✅ / ❌ / ⚪ / 🔌 per question, the score, and
     evals/results/run-<time>.json; a full run is also a Langfuse
     experiment. Exit code 1 if a safety gate fails.

How: each question runs signed in as its employee, on a clean copy of
the database, graded by must_include, must_not_include and db_change.

Watch out: keyword checks can't see meaning ("not 7" passes "7").
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
from langfuse import Evaluation
from langgraph.types import Command

from ams_agent import config, judge, tracing
from ams_agent.agent import build_agent, final_answer
from ams_agent.budget import stopped_by
from ams_agent.config import (
    AGENT,
    EVAL_DB_PATH,
    EVAL_MAX_CONFIRMS,
    EVAL_PAUSE,
    EXPERIMENT_NAME,
    GATE_CATEGORIES,
    PROVIDER_KEYS,
    QUESTIONS,
    RESULTS_DIR,
    ROOT,
    SMOKE_SET,
    TRACE_FULL_EVALS,
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
# Errors after which later questions would only fail the same way, so
# the run stops: Gemini's daily quota, an empty Claude credit balance.
STOP_ERRORS = {"PerDay": "Gemini's daily quota is used up",
               "credit balance": "The Claude credit balance is used up"}


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
    """Error messages never show an API key, even by accident."""
    for name in filter(None, PROVIDER_KEYS.values()):
        if key := os.environ.get(name):
            text = text.replace(key, "***")
    return text


def run_one(agent, question: dict, earlier: list,
            traced: bool = False) -> tuple[dict, list]:
    """Ask one question; returns its result and the chat so far.
    traced: recorded in Langfuse, inside its experiment item's trace."""
    tables = {q.split()[0] for q in [question["db_change"]] if q}
    before = {t: count_rows(t) for t in tables}
    sent = earlier + [HumanMessage(question["question"])]
    # Its own chat: a follow-up starts from a copy of the earlier turns.
    chat = tracing.run_config(question["employee_id"],
                              f"{question['id']}-{time.time()}", traced,
                              tags=("eval",))
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


def experiment_item(question: dict) -> dict:
    """A question as Langfuse shows it. Runs line up item by item by
    their input, so the input is only what was asked (and after which
    question); the ID and category go in the metadata."""
    asked = {"employee_id": question["employee_id"],
             "question": question["question"]}
    if question["previous_question"]:
        asked["follows"] = question["previous_question"]
    return {"input": asked, "expected_output": question["expected_answer"],
            "metadata": {"id": question["id"],
                         "category": question["category"]}}


def scores(result: dict) -> list[Evaluation]:
    """A question's scores on its trace: passed (every check, with what
    failed), safety (a gate, the same yes / no), judge (with --judge).
    An ungraded question (⚪) gets none."""
    found = []
    if result["verdict"] in ("pass", "fail"):
        ok = int(result["verdict"] == "pass")
        notes = [f"{c['check']}: {c['detail']}" for c in result["checks"]
                 if not c["ok"]] + [f"⚠ {w}" for w in result["warnings"]]
        found.append(Evaluation(name="passed", value=ok, data_type="BOOLEAN",
                                comment="; ".join(notes)[:500]
                                or "every check passed"))
        if result["category"] in GATE_CATEGORIES:
            found.append(Evaluation(name="safety", value=ok,
                                    data_type="BOOLEAN"))
    if verdict := result.get("judge"):
        found.append(Evaluation(name="judge", value=int(verdict["correct"]),
                                comment=verdict["reason"][:500],
                                data_type="BOOLEAN"))
    return found


class EvalRun:
    """The questions, asked in order: each on its own copy of the
    database, a follow-up after its parent's chat. Keeps the results,
    and why the run stopped early (quota, credit), if it did."""

    def __init__(self, questions: list[dict], judged: bool,
                 traced: bool) -> None:
        self.questions, self.judged, self.traced = questions, judged, traced
        self.clean = fresh_database()
        self.agent = build_agent(fallback=False)  # the main model only
        self.followed = {q["previous_question"] for q in questions}
        self.results: list[dict] = []
        self.chats: dict[str, list] = {}
        self.stopped: str | None = None

    def ask(self, question: dict, trial: int) -> dict | None:
        """One question, shown and kept; None once the run has stopped."""
        if self.stopped:
            return None
        if self.results:
            time.sleep(EVAL_PAUSE)
        parent = question["previous_question"]
        # Each question on a clean copy; a follow-up on its parent's
        # database, so "book it again" sees the first booking.
        shutil.copy(snapshot(parent) if parent in self.chats
                    else self.clean, EVAL_DB_PATH)
        result, self.chats[question["id"]] = run_one(
            self.agent, question, self.chats.get(parent, []), self.traced)
        result["trial"] = trial
        if self.judged:
            add_judge(result, question)
        self.results.append(result)
        show(result)
        if question["id"] in self.followed:
            shutil.copy(EVAL_DB_PATH, snapshot(question["id"]))
        if why := next((why for found, why in STOP_ERRORS.items()
                        if found in (result["error"] or "")), None):
            print(f"     {why}: stopping the run.")
            self.stopped = why
        return result

    def experiment(self, trial: int, name: str, metadata: dict) -> dict:
        """One pass as a Langfuse experiment: each question an item (its
        trace, its scores), in order, one at a time, since a follow-up
        needs its parent's chat. Returns the run's name and page."""
        by_id = {q["id"]: q for q in self.questions}
        done: dict[str, dict] = {}

        def task(*, item, **_):
            result = self.ask(by_id[item["metadata"]["id"]], trial)
            if result is None:
                raise RuntimeError(f"not run: {self.stopped}")
            done[result["id"]] = result
            if result["error"]:  # Langfuse counts it as an error
                raise RuntimeError(result["error"])
            return result["answer"]

        def grade(*, metadata, **_):
            return scores(done[metadata["id"]])

        found = tracing.client().run_experiment(
            name=EXPERIMENT_NAME, run_name=name,
            description=f"{len(self.questions)} questions",
            data=[experiment_item(q) for q in self.questions],
            task=task, evaluators=[grade], max_concurrency=1,
            metadata=metadata)
        return {"name": found.run_name, "url": found.experiment_url}

    def every_try(self, repeat: int, name: str,
                  metadata: dict) -> list[dict]:
        """Every question, repeat times. Traced, each try is an
        experiment, `name` (+ "try 2/3"); returns their names and pages."""
        experiments = []
        for trial in range(repeat):
            if self.traced:
                experiments.append(self.experiment(
                    trial, name if repeat == 1
                    else f"{name} · try {trial + 1}/{repeat}", metadata))
            else:  # once stopped, ask() skips the rest
                for question in self.questions:
                    self.ask(question, trial)
            if self.stopped:
                break
        return experiments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="question IDs, e.g. Q01,Q27")
    parser.add_argument("--repeat", type=int, default=1,
                        help="ask each question this many times (noise)")
    parser.add_argument("--judge", action="store_true",
                        help="the LLM judge grades what code can't")
    parser.add_argument("--smoke", action="store_true",
                        help="only the smoke set (SMOKE_SET, config.py)")
    args = parser.parse_args()
    if args.smoke:  # the smoke set is an --only run: never traced
        args.only = ",".join(SMOKE_SET)
    # Each line as it happens, even when the output goes to a file.
    if hasattr(sys.stdout, "reconfigure"):  # not when captured
        sys.stdout.reconfigure(line_buffering=True)
    with QUESTIONS.open(newline="", encoding="utf-8") as f:
        questions = chosen(list(csv.DictReader(f)), args.only)

    started = datetime.now()
    path = RESULTS_DIR / f"run-{started:%Y%m%d-%H%M%S}.json"
    # Only a full run is traced: --only runs are building, not measuring.
    traced = bool(TRACE_FULL_EVALS and not args.only and tracing.client())
    print(f'Traced in Langfuse: experiments "{EXPERIMENT_NAME}"' if traced
          else "Not traced (an --only run, or Langfuse is down)")
    warm_up()  # the search models load before the clock starts
    run = EvalRun(questions, args.judge, traced)
    experiments = run.every_try(
        args.repeat, f"{AGENT.name} · {started:%-d %b %H:%M}",
        {"results": f"evals/results/{path.name}",
         "judge": "on" if args.judge else "off"})

    results = run.results
    trials = [(t, q) for t in range(args.repeat) for q in questions]
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
    if traced:
        tracing.flush()  # every trace sent before the process ends
        for found in experiments:
            print(f"In Langfuse (scores, cost, traces):"
                  f" {found['url'] or found['name']}")
    RESULTS_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(
        {"run_at": datetime.now().isoformat(timespec="seconds"),
         "settings": settings(), "only": args.only, "counts": counts,
         "not_run": [q["id"] for _, q in trials[len(results):]],
         "repeat": args.repeat, "gates_ok": gates_ok,
         "stopped": run.stopped is not None,
         "langfuse_experiments": experiments,
         "results": results}, indent=2, ensure_ascii=False))
    print(f"-> {path}")
    # Like a failing test suite: a safety gate failed, or wasn't checked.
    sys.exit(0 if gates_ok else 1)


if __name__ == "__main__":
    main()
