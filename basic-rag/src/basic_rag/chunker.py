"""Ingestion step 2: split one document into section-aware chunks.

ingest.py calls chunk_text() once per document. Every document is
organised by numbered headings (in the India leave policy, for example,
"3. ANNUAL LEAVE", "3.1 Standard entitlement", ...). Chunking happens in
two phases:

  Phase 1 - Split into sections
      Every numbered heading starts a new section. Each section
      remembers its id ("3.1"), title, and parent ("3. ANNUAL LEAVE").

  Phase 2 - Split long sections into chunks
      A section longer than chunk_size characters is cut into pieces.
      Cuts only happen at the end of a line or a sentence (or, for a
      single sentence longer than chunk_size, between words), so each
      piece starts and ends on a complete thought. With `overlap` > 0,
      a piece also repeats the last whole lines/sentences of the
      previous one, up to `overlap` characters.

Every chunk also carries the document's title and version, read from
the file's own header (e.g. "EMPLOYEE LEAVE POLICY (INDIA), Version
2.1"). Otherwise only the INTRODUCTION chunk would say which document,
country, or version a rule belongs to, and "4.1 Standard carry-over
limit" would look the same in the India, US, and old v2.0 policies.

The chunker doesn't know the file name; ingest.py adds it as `source`
when storing the chunk. Title and section metadata are stored in Qdrant
with the chunk, are added to the embedding text (embedder.py), and are
shown to the LLM (prompts.py). The evals use source + section to check
which part of which document was retrieved.
"""

import re

from basic_rag.config import CHUNK_OVERLAP, CHUNK_SIZE


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """Split text into chunks that know which section they came from.

    Returns a list of dicts, each with:
        document_title  "EMPLOYEE LEAVE POLICY (INDIA), Version 2.1"
                        ("" if the file has no recognisable header)
        section         "3.1 Standard entitlement"
        section_id      "3.1"  ("" for text before the first heading)
        section_title   "Standard entitlement"
        parent_section  "3. ANNUAL LEAVE"
        chunk_index     0, 1, 2 ... position within its section
        text            the chunk text itself (heading line excluded)
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size"
        )

    # --- Phase 1: split the document into sections -------------------

    # Match headings such as:
    # 3. ANNUAL LEAVE
    # 3.1 Standard entitlement
    # 3.1.1 Additional rules
    # Group 1 is the number, group 2 is the title. Note: any line that
    # starts with a number and a space matches, so body text like
    # "5 days ..." at the start of a line would be treated as a heading.
    heading_pattern = re.compile(
        r"(?m)^[ \t]*(\d+(?:\.\d+)*\.?)[ \t]+(.+?)[ \t]*$"
    )

    headings = list(heading_pattern.finditer(text))
    sections = []

    if not headings:
        # No headings at all: treat the whole document as one section.
        sections.append({
            "section": "INTRODUCTION",
            "section_id": "",
            "section_title": "INTRODUCTION",
            "parent_section": "",
            "text": text.strip(),
        })
    else:
        # Preserve text before the first heading.
        introduction = text[:headings[0].start()].strip()

        if introduction:
            sections.append({
                "section": "INTRODUCTION",
                "section_id": "",
                "section_title": "INTRODUCTION",
                "parent_section": "",
                "text": introduction,
            })

        # The most recent top-level heading, e.g. "3. ANNUAL LEAVE".
        # Sub-sections like 3.1 and 3.2 inherit it as their parent.
        current_parent = ""

        for i, heading in enumerate(headings):
            heading_number = heading.group(1).rstrip(".")
            heading_title = heading.group(2).strip()

            # A section's text runs from the end of its heading line to
            # the start of the next heading (or the end of the document).
            section_end = (
                headings[i + 1].start()
                if i + 1 < len(headings)
                else len(text)
            )

            section_text = text[heading.end():section_end].strip()

            # A single-number heading, e.g. "3.", is a parent section.
            if "." not in heading_number:
                current_parent = f"{heading_number}. {heading_title}"
                section_id = heading_number
                parent_section = current_parent
            else:
                section_id = heading_number
                parent_section = current_parent

            # Parent headings with no body text of their own (like
            # "3. ANNUAL LEAVE") get an empty text and are skipped in
            # phase 2.
            sections.append({
                "section": f"{section_id} {heading_title}",
                "section_id": section_id,
                "section_title": heading_title,
                "parent_section": parent_section,
                "text": section_text,
            })

    # --- Phase 2: split each section into chunks ---------------------

    chunks = []
    document_title = _read_document_title(text)

    for section in sections:
        if not section["text"]:
            continue

        # Short sections become exactly one piece.
        units = _split_into_units(section["text"], chunk_size)
        pieces = _pack_units(units, chunk_size, overlap)

        for chunk_index, piece in enumerate(pieces):
            chunks.append({
                "document_title": document_title,
                "section": section["section"],
                "section_id": section["section_id"],
                "section_title": section["section_title"],
                "parent_section": section["parent_section"],
                "chunk_index": chunk_index,
                "text": piece,
            })

    return chunks


def _read_document_title(text: str) -> str:
    """Return "<title>, Version <n>" from the document's header.

    Every AMS file starts with the company name, then the title, then
    an ID line containing "Version: <n>":
        AMS
        EMPLOYEE LEAVE POLICY (INDIA)
        Policy ID: HR-LEAVE-IN-2026 | Version: 2.1 | ...
    Returns "" if the first lines don't follow that layout.
    """
    lines = [
        line.strip() for line in text.splitlines()[:10] if line.strip()
    ]

    for i, line in enumerate(lines):
        match = re.search(r"Version:\s*([\w.]+)", line)

        # The title is the line just above the version line.
        if match and i > 0:
            return f"{lines[i - 1]}, Version {match.group(1)}"

    return ""


def _split_into_units(text: str, chunk_size: int) -> list[tuple[str, str]]:
    """Break a section's text into the units a cut may fall between.

    Tries the largest natural unit first: a whole line. A line longer
    than chunk_size is broken into sentences, and a sentence that is
    still too long into words (rare).

    Each unit is (separator, text). The separator is "\\n" when the unit
    starts a new line and " " when it continues the previous one, so
    _join() can rebuild the original layout.
    """
    units = []

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            continue

        if len(line) <= chunk_size:
            units.append(("\n", line))
        else:
            units.extend(_split_long_line(line, chunk_size))

    return units


def _split_long_line(line: str, chunk_size: int) -> list[tuple[str, str]]:
    """Units for a line longer than chunk_size: its sentences, or the
    words of any sentence that is itself longer than chunk_size."""
    units = []

    # A sentence ends at . ! or ? followed by whitespace.
    for sentence in re.split(r"(?<=[.!?])\s+", line):
        if len(sentence) <= chunk_size:
            units.append((" ", sentence))
        else:
            units.extend((" ", word) for word in sentence.split())

    # The line's first unit starts a new line.
    units[0] = ("\n", units[0][1])
    return units


def _join(units: list[tuple[str, str]]) -> str:
    """Rebuild text from units, e.g. [("\\n", "A."), (" ", "B.")] ->
    "A. B."."""
    text = "".join(separator + unit for separator, unit in units)
    # Drop the first unit's separator; a chunk never starts with one.
    return text[1:]


def _pack_units(
    units: list[tuple[str, str]],
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Group consecutive units into pieces of at most chunk_size chars.

    A piece is closed when the next unit doesn't fit. The next piece
    then starts with the closed piece's last whole units, up to
    `overlap` characters in total (overlap = 0 means no repetition).
    """
    pieces = []
    current = []

    for unit in units:
        if current and len(_join(current + [unit])) > chunk_size:
            pieces.append(_join(current))

            # Carry trailing units, newest first, while they fit in the
            # overlap budget.
            carried = []

            for previous in reversed(current):
                if len(_join([previous] + carried)) > overlap:
                    break
                carried.insert(0, previous)

            # Drop the carry if it would leave no room for this unit.
            if len(_join(carried + [unit])) > chunk_size:
                carried = []

            current = carried

        current.append(unit)

    if current:
        pieces.append(_join(current))

    return pieces
