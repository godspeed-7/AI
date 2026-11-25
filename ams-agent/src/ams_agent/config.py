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

# The HR data is a snapshot of this day (TODAY in build_hr_data.py), so
# the agent's "today" is this date, not the computer's.
TODAY = date(2026, 11, 16)

# The agent's model: picks the tools and writes the answer. Needs the
# internet and GOOGLE_API_KEY. Temperature stays at Gemini's default:
# Google advises against lowering it for Gemini 3 models.
AGENT_MODEL = "gemini-3.5-flash-lite"
AGENT_TIMEOUT = 60  # seconds per model call
AGENT_RETRIES = 2  # on errors that can pass (429 too busy, 500, 503)
# Model calls per question before the agent loop stops (the step limit).
MAX_MODEL_CALLS = 5

# Seconds between eval questions, to stay under the free tier's
# per-minute limit.
EVAL_PAUSE = 4
