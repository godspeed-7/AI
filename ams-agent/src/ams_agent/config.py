"""Every setting of the AMS agent, in one place, grouped by job.

In:  nothing; edit the values here, and only here.
Out: the constants the other files import; `uv run python -m
     ams_agent.config` prints the overview: which model each job uses,
     where it runs, its time limit and retries, and the limits.

Strategy: code asks for a job (AGENT, GUARD, ...), never a provider or
a model name (models.py makes the clients), so moving a job to another
model is a change here only. No secrets here: PROVIDER_KEYS names each
provider's key; the keys stay in the environment (~/.zshrc) or in
ams-agent/.env (git ignores it). Each eval run saves settings() with
its results, so runs compare fairly.

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
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]  # ams-agent/

# The Anthropic key lives in ams-agent/.env, not ~/.zshrc: Claude Code
# uses an ANTHROPIC_API_KEY it finds in the shell instead of the Claude
# subscription. A variable already set in the shell wins over the file.
load_dotenv(ROOT / ".env")


# ── Models: one entry per job ───────────────────────────────────────

@dataclass(frozen=True)
class Pace:
    """Client-side throttling: calls a minute, and how many may go at
    once (a token bucket). Jobs with the same Pace share one limiter."""
    per_minute: float
    burst: int


@dataclass(frozen=True)
class Price:
    """US dollars per 1 million tokens, as the provider lists them."""
    input: float
    output: float  # thinking tokens are billed as output
    # A cached prompt (Claude): reading it back, and writing it (5 minutes)
    cache_read: float | None = None
    cache_write: float | None = None


@dataclass(frozen=True)
class Model:
    """One job's model. Like Object.freeze({...}) in JS, with types."""
    # "anthropic" (the Claude API), "google" (the Gemini API) or
    # "ollama" (this Mac)
    provider: str
    name: str
    timeout: float  # seconds per call
    retries: int = 0  # more tries after a failed call
    # None: the model's own default. Claude: "adaptive" or "disabled";
    # Gemini: "low", "medium" or "high"; Ollama: True or False.
    thinking: str | bool | None = None
    temperature: float | None = None  # None: the model's own default
    pace: Pace | None = None  # None: not throttled
    price: Price | None = None  # Langfuse's cost per call comes from it
    # The most tokens one reply may use, thinking included; None: the
    # model's own limit (128,000 on Haiku 5.5). A cap on one call's cost.
    max_output: int | None = None


# Each provider's key, by name only: the keys stay in ~/.zshrc or .env.
PROVIDER_KEYS = {"anthropic": "ANTHROPIC_API_KEY",
                 "google": "GOOGLE_API_KEY", "ollama": None}

# Claude Haiku 5.5, prompts up to 100,000 tokens (ours stay under
# MAX_TOKENS); longer prompts cost 5 times as much.
HAIKU = "claude-haiku-5-5"
# A cached prompt costs a tenth to read back, 1.25 times to write.
HAIKU_PRICE = Price(input=0.10, output=0.50, cache_read=0.01,
                    cache_write=0.125)
# The agent's prompt caching: each call marks the tools, the prompt and
# the chat so far, and the next call within this time reads them back
# at the cache price. A question's calls come seconds apart. Claude
# only (the backup isn't cached); below 512 tokens nothing is cached.
PROMPT_CACHE_TTL = "5m"
# Gemini's free tier: 15 calls a minute per model, counted across all
# jobs on it. A burst of 3 lets one question's calls go at once.
FREE_TIER = Pace(per_minute=12, burst=3)
# Flash-Lite's paid list price. On the free tier we pay nothing, but the
# traces show what the same calls would cost.
FLASH_LITE_PRICE = Price(input=0.30, output=2.50)
FREE = Price(input=0, output=0)  # local, or a free quota

# The agent: picks the tools and writes the answer. Thinking: adaptive
# (Haiku 5.5's default; it decides how much a step needs, at "medium"
# effort), the same in the app and the evals. Thinking is billed as
# output. Its retries are middleware (resilience.py): one retry layer,
# and never a bad key, a bad request or an empty credit balance.
AGENT = Model("anthropic", HAIKU, timeout=60, retries=2,
              thinking="adaptive", price=HAIKU_PRICE, max_output=16_000)
# The topic guard (topic_guard.py): one small check per question, before
# the agent. A short time limit: it runs on every question, and lets the
# question through if it fails. No thinking: a yes/no check, and its
# forced structured output.
GUARD = Model("anthropic", HAIKU, timeout=20, retries=2,
              thinking="disabled", price=HAIKU_PRICE, max_output=1_000)
# The reviewer (review.py): a second look at each draft answer. No
# thinking, for the same reasons as the guard.
REVIEWER = Model("anthropic", HAIKU, timeout=30, retries=2,
                 thinking="disabled", price=HAIKU_PRICE, max_output=2_000)
# Summarises the old part of a long chat.
SUMMARY = AGENT
# The backup when the agent's or the guard's model keeps failing
# (resilience.py): another company, so one outage can't stop both;
# Gemini's free tier (500 calls a day, plenty for a backup). Free-tier
# content may be used by Google to improve its products: fine for our
# made-up data, not for real HR data. Not in the evals.
BACKUP = Model("google", "gemini-3.5-flash-lite", timeout=60, retries=2,
               pace=FREE_TIER, price=FLASH_LITE_PRICE)
# The LLM judge (judge.py, evals with --judge): another model family than
# the agent, its own free quota (14,400 a day), paced under 30 a minute.
JUDGE = Model("google", "gemma-4-26b-a4b-it", timeout=60, retries=2,
              temperature=0, pace=Pace(per_minute=6, burst=1), price=FREE)

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
# The backup gets its own limit, in case it's slower; the hosted one is
# as fast as the main model.
BACKUP_MAX_SECONDS = MAX_SECONDS
MAX_TOKENS = 30_000  # input + output (thinking too), as reported


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
# Google's free models are sometimes overloaded (503 "high demand, try
# again later"): the judge then waits and tries again, a few times.
JUDGE_BUSY_WAIT = 20  # seconds
JUDGE_BUSY_TRIES = 3
# The smoke set (run_evals.py --smoke): a dozen questions, one or two per
# kind, after a change; the full set once per batch of changes. About
# 1.5 cents; not traced. Data, rules, a rule behind a date, a follow-up
# (with Q01), a booking, the name, a manager's view, and 4 safety gates
# (another's pay, impersonation, prompt leak, and a mirror that must not
# be blocked).
SMOKE_SET = ("Q01", "Q05", "Q12", "Q20", "Q21", "Q23", "Q27", "Q28",
             "Q30", "Q31", "Q37", "Q40")
# Tracing in our local Langfuse (tracing.py): only the runs worth
# keeping, so its views hold no test noise. Quick runs (--only), the
# code checks and scripts never trace.
TRACE_APP = True  # each question asked in the app: one trace
TRACE_FULL_EVALS = True  # each full golden-set run: one session
# 127.0.0.1, not localhost: another dev server (node) also listens on
# port 3000, and "localhost" reaches it instead of Langfuse.
LANGFUSE_URL = "http://127.0.0.1:3000"
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

    def price(model: Model) -> str:
        if model.price is None:
            return "-"
        if model.price == FREE:
            return "free"
        text = f"{model.price.input:g} / {model.price.output:g}"
        if model.price.cache_read is not None:
            text += f" (cached {model.price.cache_read:g})"
        return text
    rows = [("job", "runs on", "model", "timeout", "retries", "thinking",
             "$ per 1M in/out", "when")]
    rows += [(job, model.provider, model.name, f"{model.timeout:g} s",
              str(model.retries), thinking(model), price(model), when)
             for job, (model, when) in JOBS.items()]
    widths = [max(len(row[i]) for row in rows) for i in range(7)]
    lines = ["Models"] + ["  " + "  ".join(
        [cell.ljust(width) for cell, width in zip(row, widths)] + [row[7]])
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
        "Prompt cache": (
            f"the agent's tools, prompt and chat so far, kept"
            f" {PROMPT_CACHE_TTL} (Claude only)"),
        "Measuring": (
            f"smoke set: {len(SMOKE_SET)} questions (--smoke); safety"
            f" gates: {', '.join(sorted(GATE_CATEGORIES))}; judge"
            f" busy (503): {JUDGE_BUSY_TRIES} more tries,"
            f" {JUDGE_BUSY_WAIT} s apart; live answers kept"
            f" {QUALITY_KEEP_DAYS} days"),
        "Traced in Langfuse": (
            f"app questions {'on' if TRACE_APP else 'off'}, full eval runs"
            f" {'on' if TRACE_FULL_EVALS else 'off'} ({LANGFUSE_URL});"
            " --only runs, checks and scripts never"),
    }
    lines.append("")
    for heading, text in limits.items():
        lines += [f"{heading}:", f"  {text}"]
    return "\n".join(lines)


if __name__ == "__main__":
    print(overview())
