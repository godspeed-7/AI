"""Settings for the AMS agent: paths, the model, limits, the data's date.

Every path, model name and limit lives here, so the other files never
hard-code one.
"""

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # ams-agent/
CSV_DIR = ROOT.parent / "ams-data" / "db"  # the 12 HR tables, as CSV
DB_PATH = ROOT / "data" / "hr.sqlite"  # built from them by load_data.py
QUESTIONS = ROOT / "evals" / "questions.csv"
RESULTS_DIR = ROOT / "evals" / "results"
# The eval runner's own database, rebuilt from the CSVs for each run and
# reset before each question, so bookings never leak between tests.
EVAL_DB_PATH = ROOT / "data" / "hr-eval.sqlite"
# The office holiday calendar: Employee Handbook, chapter 6 (load_data).
HANDBOOK = ROOT.parent / "ams-data" / "policies" / "people" / \
    "employee_handbook.txt"
HOLIDAY_SECTIONS = {"Bengaluru": "6.3.1", "Pune": "6.4.1", "Austin": "6.6.1"}

# The HR data is a snapshot of this day (TODAY in build_hr_data.py), so
# the agent's "today" is this date, not the computer's.
TODAY = date(2026, 11, 16)

# Its staff get the hr role at sign-in (walk 4, context.py).
HR_DEPARTMENT = "People Operations"
# Payroll isn't stored; it follows the office (ams-data/db/README.md).
PAYROLL = {"Bengaluru": "India", "Pune": "India", "Austin": "US"}

# The agent's model: picks the tools and writes the answer. Needs the
# internet and GOOGLE_API_KEY. Temperature stays at Gemini's default:
# Google advises against lowering it for Gemini 3 models.
AGENT_MODEL = "gemini-3.5-flash-lite"
# How much it thinks before each step: None (the model's default,
# minimal), "low", "medium" or "high". Walk 7, run 1 (26 Nov): "low"
# vs the default gave the same score (15 vs 15 on Q01-Q32), time and
# tokens, so the default stays.
AGENT_THINKING = None
AGENT_TIMEOUT = 60  # seconds per model call
AGENT_RETRIES = 2  # the topic guard's client retries (429, 500, 503)

# When a call fails (walk 11, resilience.py). The agent's retries are
# middleware (one layer; never a bad key, request or the daily quota).
MODEL_RETRIES = 2  # per model call, waiting longer each time
# The backup when Gemini keeps failing: local, free, no daily quota;
# slower (~13 s a round), thinking on as always for qwen3. Not in evals.
BACKUP_MODEL = "qwen3:8b"
BACKUP_TIMEOUT = 120  # seconds per call: local thinking is slow
BREAKER_FAILURES = 3  # Gemini failures in a row that open the breaker
BREAKER_SECONDS = 600  # then backup only for this long, then try Gemini
SEARCH_TIMEOUT = 30  # seconds for one handbook search (policy_search.py)
TOOL_RETRIES = 1  # a tool that raises gets one more try, then a message

# What's kept (walk 14, memory.py): chats and preferences, on disk.
CHATS_DB_PATH = ROOT / "data" / "chats.sqlite"
PREFERENCES_DB_PATH = ROOT / "data" / "preferences.sqlite"
CHAT_KEEP_DAYS = 30  # a chat unused this long is deleted (HR data)
SUMMARY_AT_TOKENS = 8_000  # a longer chat: its old part is summarised
SUMMARY_KEEP_MESSAGES = 20  # the newest messages kept word for word

# Measuring (walk 15). The LLM judge: another model family than the
# agent, its own free quota (14,400 a day), paced under 30 a minute.
JUDGE_MODEL = "gemma-4-26b-a4b-it"
JUDGE_PER_MINUTE = 6
JUDGE_TIMEOUT = 60
JUDGE_KEY = ROOT / "evals" / "judge_key.csv"  # a person's grades
# Tracing every live run in our local Langfuse (tracing.py): OFF until
# you switch it on; the evals never trace.
TRACING = False
# Live answers, their online checks and thumbs (quality.py).
QUALITY_DB_PATH = ROOT / "data" / "quality.sqlite"
QUALITY_KEEP_DAYS = 30
REVIEW_SAMPLE = 2  # random answers a day that a person also reviews
CANDIDATES = ROOT / "evals" / "candidates.csv"  # new test cases, drafted
# Questions that are safety gates: one failure fails the run (exit 1),
# never averaged into the score.
GATE_CATEGORIES = {"attack", "refuse"}

# The reviewer (walk 12, review.py): a second look at each draft.
REVIEW_ROUNDS = 1  # extra rounds after a "not approved", at most
REVIEW_TIMEOUT = 30  # seconds for the review call
# All Gemini calls together (agent + topic guard), paced in models.py:
# the free tier allows 15 a minute per model; 12 leaves room.
CALLS_PER_MINUTE = 12
# The budget per question (walk 6, budget.py): past any of these the
# agent stops with a fixed reply. Measured use plus headroom (26 Nov,
# 38 questions): 1-2 model calls, 1 tool call, 19 seconds at most (81
# once, with retries), 1,008 tokens at most. Tokens get the most room:
# the whole chat is resent each question, and walk 7's tools add text.
MAX_MODEL_CALLS = 5  # the step limit
MAX_TOOL_CALLS = 8  # more are refused; the model answers with what it has
MAX_SECONDS = 90  # checked before each model call
# The local backup (walk 11) is far slower: measured 27 Nov, Gemini
# refused: the guard 24-35 s, one agent step ~100 s on this laptop.
BACKUP_MAX_SECONDS = 300
MAX_TOKENS = 30_000  # input + output, as Gemini reports them

# The topic guard (walk 3, topic_guard.py): one small check per
# question, before the agent. The same model, given only the allow-list
# and the last few messages; a short time limit, as it runs on every
# question (and lets the question through if it fails).
GUARD_MODEL = AGENT_MODEL
GUARD_TIMEOUT = 20  # seconds
GUARD_MESSAGES = 5  # the new question + the 2 turns before it

# Request limits, checked in code before the agent (walk 3, limits.py).
MAX_MESSAGE_CHARS = 2000  # a question longer than this is refused
MAX_QUESTIONS_PER_MINUTE = 10  # per employee, in any 60 seconds

# Seconds between eval questions. 0: the shared pace in models.py
# already keeps every call under the free tier's per-minute limit.
EVAL_PAUSE = 0
