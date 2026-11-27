"""Every setting of the AMS agent, in one place, grouped by job.

In:  nothing; edit the values here, and only here.
Out: the constants the other files import; `uv run python -m
     ams_agent.config` prints the overview: which model each job uses,
     where it runs, its time limit and retries, and the limits.

Strategy: code asks for a job (AGENT, GUARD, ...), never a provider or
a model name (models.py makes the clients), so moving a job to another
model is a change here only. No secrets here: PROVIDER_KEYS names each
provider's key; the keys stay in the environment (~/.zshrc). Each eval
run saves settings() with its results, so runs compare fairly.

Caveats: the handbook search's settings are ams-assistant's (its
config.py): shown here and in the overview, changed there. Handbook
rules (e.g. probation limits) stay next to the code that applies them,
with their section numbers: they change with the handbook.
"""

import os
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from ams_assistant import config as search

ROOT = Path(__file__).resolve().parents[2]  # ams-agent/


# ── Models: one entry per job ───────────────────────────────────────

@dataclass(frozen=True)
class Pace:
    """Client-side throttling: calls a minute, and how many may go at
    once (a token bucket). Jobs with the same Pace share one limiter."""
    per_minute: float
    burst: int


@dataclass(frozen=True)
class Model:
    """One job's model. Like Object.freeze({...}) in JS, with types."""
    provider: str  # "google" (the Gemini API) or "ollama" (this Mac)
    name: str
    timeout: float  # seconds per call
    retries: int = 0  # more tries after a failed call
    thinking: str | bool | None = None  # None: the model's own default
    temperature: float | None = None  # None: the model's own default
    pace: Pace | None = None  # None: not throttled


# Each provider's key, by name only: the keys stay in ~/.zshrc.
PROVIDER_KEYS = {"google": "GOOGLE_API_KEY", "ollama": None}

# Gemini's free tier: 15 calls a minute per model, counted across all
# jobs on it. A burst of 3 lets one question's calls (guard, model,
# model) go at once: 3 + 12 refills = 15 a minute at most.
FREE_TIER = Pace(per_minute=12, burst=3)

# The agent: picks the tools and writes the answer. Temperature: the
# default (Google advises against lowering it for Gemini 3). Thinking:
# None (the default, minimal), "low", "medium" or "high": "low" scored
# no better on our evals (15 vs 15 on Q01-Q32), so the default stays.
# Its retries are middleware (resilience.py): one retry layer, and
# never a bad key, a bad request or the daily quota.
AGENT = Model("google", "gemini-3.5-flash-lite", timeout=60, retries=2,
              pace=FREE_TIER)
# The topic guard (topic_guard.py): one small check per question, before the
# agent. A short time limit: it runs on every question, and lets the
# question through if it fails.
GUARD = Model("google", "gemini-3.5-flash-lite", timeout=20, retries=2,
              pace=FREE_TIER)
# The reviewer (review.py): a second look at each draft answer.
REVIEWER = Model("google", "gemini-3.5-flash-lite", timeout=30, retries=2,
                 pace=FREE_TIER)
# Summarises the old part of a long chat.
SUMMARY = AGENT
# The backup when the agent's or the guard's model keeps failing
# (resilience.py): local, free, no daily quota; slow (measured: ~100 s
# a step on this laptop); thinking on, as always for qwen3. Ollama's
# client has no retries. Not in the evals.
BACKUP = Model("ollama", "qwen3:8b", timeout=120, thinking=True)
# The LLM judge (judge.py, evals with --judge): another model family than
# the agent, its own free quota (14,400 a day), paced under 30 a minute.
JUDGE = Model("google", "gemma-4-26b-a4b-it", timeout=60, retries=2,
              temperature=0, pace=Pace(per_minute=6, burst=1))

# What each job does and when it runs, for the overview.
JOBS = {
    "agent": (AGENT, "tools + answer; ~2 calls a question"),
    "guard": (GUARD, "on-topic check; every question"),
    "reviewer": (REVIEWER, "checks each draft answer"),
    "summary": (SUMMARY, "long chats only (the app)"),
    "backup": (BACKUP, "only when a call fails (the app)"),
    "judge": (JUDGE, "evals with --judge only"),
}

# The handbook search (policy_search.py): ams-assistant's tuned
# pipeline, all on this Mac, no LLM (its rewrite switches are off).
# Shown here only.
SEARCH = {
    "embeddings": f"ollama {search.EMBEDDING_MODEL}",
    "reranker": search.RERANKER_MODEL,
    "keeps": f"top {search.TOP_K} of {search.CANDIDATE_K} candidates",
    "vector store": f"Qdrant {search.QDRANT_URL} {search.COLLECTION_NAME}",
}
SEARCH_TIMEOUT = 30  # seconds for one search (policy_search.py)
SEARCH_QUERY_CHARS = 300  # a search text, not a document


# ── When something fails (resilience.py) ────────────────────────────

BREAKER_FAILURES = 3  # agent-model failures in a row open the breaker
BREAKER_SECONDS = 600  # then backup only for this long, then try again
TOOL_RETRIES = 1  # a tool that raises gets one more try, then a message


# ── Checks on the way in and out ────────────────────────────────────

# Request limits, checked in code before the agent (limits.py).
MAX_MESSAGE_CHARS = 2000  # a question longer than this is refused
MAX_QUESTIONS_PER_MINUTE = 10  # per employee, in any 60 seconds
GUARD_MESSAGES = 5  # the guard reads the question + the 2 turns before
REVIEW_ROUNDS = 1  # the reviewer's extra rounds, at most
LEAK_WORDS = 8  # output check: words in a row that quote the prompt


# ── The budget per question (budget.py) ─────────────────────────────

# Past any of these the agent stops with a fixed reply. Measured use
# plus headroom (38 questions, on Gemini): 1-2 model calls, 1 tool call,
# 19 seconds at most (81 once, with retries), 1,008 tokens at most.
# Tokens get the most room: the whole chat is resent each question.
MAX_MODEL_CALLS = 5  # the step limit
MAX_TOOL_CALLS = 8  # more are refused; the model answers with what it has
MAX_SECONDS = 90  # checked before each model call
# The local backup is far slower (measured with Gemini refusing): the
# guard 24-35 s, one agent step ~100 s on this laptop.
BACKUP_MAX_SECONDS = 300
MAX_TOKENS = 30_000  # input + output, as the model reports them


# ── What's kept (memory.py) ─────────────────────────────────────────

CHATS_DB_PATH = ROOT / "data" / "chats.sqlite"
PREFERENCES_DB_PATH = ROOT / "data" / "preferences.sqlite"
CHAT_KEEP_DAYS = 30  # a chat unused this long is deleted (HR data)
SUMMARY_AT_TOKENS = 8_000  # a longer chat: its old part is summarised
SUMMARY_KEEP_MESSAGES = 20  # the newest messages kept word for word


# ── Measuring (evals/, quality.py) ──────────────────────────────────

QUESTIONS = ROOT / "evals" / "questions.csv"
RESULTS_DIR = ROOT / "evals" / "results"
# The eval runner's own database, rebuilt from the CSVs for each run and
# reset before each question, so bookings never leak between tests.
EVAL_DB_PATH = ROOT / "data" / "hr-eval.sqlite"
# Seconds between eval questions. 0: each job's Pace already keeps the
# calls under the free tier's per-minute limit.
EVAL_PAUSE = 0
EVAL_MAX_CONFIRMS = 3  # Confirm steps answered per question, at most
# Safety gates: one failure fails the run (exit 1), never averaged.
GATE_CATEGORIES = {"attack", "refuse"}
JUDGE_KEY = ROOT / "evals" / "judge_key.csv"  # a person's grades
# Tracing every live run in our local Langfuse (tracing.py): OFF until
# you switch it on; the evals never trace.
TRACING = False
# Live answers, their online checks and thumbs (quality.py).
QUALITY_DB_PATH = ROOT / "data" / "quality.sqlite"
QUALITY_KEEP_DAYS = 30
REVIEW_SAMPLE = 2  # random answers a day that a person also reviews
CANDIDATES = ROOT / "evals" / "candidates.csv"  # new test cases, drafted


# ── The HR data ─────────────────────────────────────────────────────

CSV_DIR = ROOT.parent / "ams-data" / "db"  # the 12 HR tables, as CSV
DB_PATH = ROOT / "data" / "hr.sqlite"  # built from them by load_data.py
SQLITE_WAIT = 5  # seconds to wait for a database another call has locked
# The office holiday calendar: Employee Handbook, chapter 6 (load_data).
HANDBOOK = ROOT.parent / "ams-data" / "policies" / "people" / \
    "employee_handbook.txt"
HOLIDAY_SECTIONS = {"Bengaluru": "6.3.1", "Pune": "6.4.1", "Austin": "6.6.1"}
# The HR data is a snapshot of this day (TODAY in build_hr_data.py), so
# the agent's "today" is this date, not the computer's.
TODAY = date(2026, 11, 16)
# Its staff get the hr role at sign-in (context.py).
HR_DEPARTMENT = "People Operations"
# Payroll isn't stored; it follows the office (ams-data/db/README.md).
PAYROLL = {"Bengaluru": "India", "Pune": "India", "Austin": "US"}


# ── The overview ────────────────────────────────────────────────────

def settings() -> dict:
    """Every job's model and the search, as saved with each eval run."""
    return {"models": {job: asdict(model) for job, (model, _) in
                       JOBS.items()},
            "search": SEARCH}


def overview() -> str:
    """What runs where, as text (uv run python -m ams_agent.config)."""
    def thinking(model: Model) -> str:
        return {None: "default", True: "on", False: "off"}.get(
            model.thinking, str(model.thinking))
    rows = [("job", "runs on", "model", "timeout", "retries", "thinking",
             "when")]
    rows += [(job, model.provider, model.name, f"{model.timeout:g} s",
              str(model.retries), thinking(model), when)
             for job, (model, when) in JOBS.items()]
    widths = [max(len(row[i]) for row in rows) for i in range(6)]
    lines = ["Models"] + ["  " + "  ".join(
        [cell.ljust(width) for cell, width in zip(row, widths)] + [row[6]])
        for row in rows]
    keys = [f"{key} ({'set' if os.environ.get(key) else 'MISSING'})"
            for key in PROVIDER_KEYS.values() if key]
    lines += ["", "Keys, from the environment: " + ", ".join(keys),
              "", "Handbook search (ams-assistant's config.py; this Mac):"]
    lines += [f"  {name:<13} {value}" for name, value in SEARCH.items()]
    limits = {
        "Per question": (
            f"at most {MAX_MODEL_CALLS} model calls, {MAX_TOOL_CALLS} tool"
            f" calls, {MAX_SECONDS} s ({BACKUP_MAX_SECONDS} s on the"
            f" backup), {MAX_TOKENS:,} tokens"),
        "When something fails": (
            f"breaker: {BREAKER_FAILURES} failures in a row -> backup only"
            f" for {BREAKER_SECONDS} s; tools: {TOOL_RETRIES} retry;"
            f" search: {SEARCH_TIMEOUT} s"),
        "Checks": (
            f"questions up to {MAX_MESSAGE_CHARS:,} characters,"
            f" {MAX_QUESTIONS_PER_MINUTE} a minute; reviewer:"
            f" {REVIEW_ROUNDS} round; prompt leak: {LEAK_WORDS} words in"
            " a row"),
        "Memory": (
            f"chats kept {CHAT_KEEP_DAYS} days; summarised past"
            f" {SUMMARY_AT_TOKENS:,} tokens, newest"
            f" {SUMMARY_KEEP_MESSAGES} messages kept"),
        "Measuring": (
            f"safety gates: {', '.join(sorted(GATE_CATEGORIES))}; tracing"
            f" {'on' if TRACING else 'off'}; live answers kept"
            f" {QUALITY_KEEP_DAYS} days"),
    }
    lines.append("")
    for heading, text in limits.items():
        lines += [f"{heading}:", f"  {text}"]
    return "\n".join(lines)


if __name__ == "__main__":
    print(overview())
