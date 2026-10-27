"""Shared settings for ingestion and querying.

Every path (and later every URL, model name, and size) lives here, so
changing a setting means editing one line. Import what you need, e.g.
`from ams_assistant.config import POLICIES_DIR`.
"""

from pathlib import Path


# --- Paths -----------------------------------------------------------
# Anchored to the project root (two folders up from this file), so
# scripts work no matter which directory you run them from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# The data lives next to this project in AI-demos/ams-data/, shared
# with basic-rag so both are measured on the same questions.
DATA_ROOT = PROJECT_ROOT.parent / "ams-data"
# Every .txt file in this folder is ingested as one document.
POLICIES_DIR = DATA_ROOT / "policies"
