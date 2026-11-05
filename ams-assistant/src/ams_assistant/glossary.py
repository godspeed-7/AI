"""Glossary: company facts as "if the text mentions X, also add Y"
rules, applied to chunks (at ingestion) or to questions (at search).

In:  ams-data/glossary.csv, one rule per row:
         term   add                            skip
         Austin "United States, US payroll"
     skip lists "source#section" keys the rule must not touch
     ("employee_handbook.txt#5" = all of chapter 5), separated by ";".
Out: additions(text, key) -> the words to add, e.g. ["Austin office"];
     enrich_chunk(doc) -> the chunk with a "Glossary: ..." line;
     expand_question(q) -> "q (United States, US payroll)".

Strategy: a plain synonym map, like Elasticsearch synonym sets. Terms
match as whole words, any case. Only the matching rows count, their
additions are merged in order, and words already in the text are
dropped, so a chunk gets only what it is missing.

Caveats:
- A rule sees words, not meaning: a chunk that names India only to say
  "not this policy" still matches. Preview where rules fire
  (experiments/evaluate_glossary.py --preview) and add skips.
- The rows come from the handbooks' definitions, never from eval
  questions.
"""

import csv
import re
from functools import cache

from langchain_core.documents import Document

from ams_assistant.config import GLOSSARY_FILE


@cache
def load_glossary() -> list[dict]:
    """Read the CSV once; each rule gets a compiled whole-word pattern,
    its additions as a list, and its skip keys as a list."""
    with open(GLOSSARY_FILE, encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    return [
        {
            "term": row["term"],
            "pattern": re.compile(rf"\b{re.escape(row['term'])}\b",
                                  re.IGNORECASE),
            "add": [part.strip() for part in row["add"].split(",")],
            "skip": [s.strip() for s in row["skip"].split(";")
                     if s.strip()],
        }
        for row in rows
    ]


def is_skipped(key: str, skip: list[str]) -> bool:
    """True if key ("file#3.4") is a skip entry or inside one
    ("file#3" covers "file#3.4")."""
    return any(key == s or key.startswith(s + ".") for s in skip)


def additions(text: str, key: str | None = None) -> list[str]:
    """The words every matching rule adds, in order, without repeats
    and without words the text already contains. key is the chunk's
    "source#section" (None for a question: nothing is skipped)."""
    result = []
    for rule in load_glossary():
        if key and is_skipped(key, rule["skip"]):
            continue
        if not rule["pattern"].search(text):
            continue
        for word in rule["add"]:
            already = re.search(rf"\b{re.escape(word)}\b", text,
                                re.IGNORECASE)
            if word not in result and not already:
                result.append(word)
    return result


def enrich_chunk(doc: Document) -> Document:
    """Return the chunk with a "Glossary: ..." line at the end, or
    unchanged if no rule matches."""
    key = f"{doc.metadata['source']}#{doc.metadata['section']}"
    words = additions(doc.page_content, key)
    if not words:
        return doc
    return Document(
        page_content=doc.page_content + "\nGlossary: " + ", ".join(words),
        metadata=doc.metadata,
    )


def expand_question(question: str) -> str:
    """Return the question with the glossary's additions in brackets,
    or unchanged if no rule matches."""
    words = additions(question)
    if not words:
        return question
    return f"{question} ({', '.join(words)})"
