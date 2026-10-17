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
      Cuts happen at spaces so words stay whole, and consecutive pieces
      overlap by about `overlap` characters so a sentence split at a
      boundary still appears whole in one of them.

Every chunk carries its section metadata. The chunker doesn't know the
document's name; ingest.py adds it as `source` when storing the chunk.
Section metadata and source are stored in Qdrant with the chunk. The
section metadata also enriches the embedding text (embedder.py), and the
evals use source + section to check which part of which document was
retrieved.
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

    for section in sections:
        section_text = section["text"]

        if not section_text:
            continue

        # Slide a window of up to chunk_size characters along the
        # section. Short sections become exactly one chunk.
        start = 0
        chunk_index = 0

        while start < len(section_text):
            end = min(start + chunk_size, len(section_text))

            # Prefer a word boundary when splitting long sections.
            if end < len(section_text):
                boundary = section_text.rfind(" ", start, end)

                if boundary > start:
                    end = boundary

            chunk = section_text[start:end].strip()

            if chunk:
                chunks.append({
                    "section": section["section"],
                    "section_id": section["section_id"],
                    "section_title": section["section_title"],
                    "parent_section": section["parent_section"],
                    "chunk_index": chunk_index,
                    "text": chunk,
                })

                chunk_index += 1

            if end >= len(section_text):
                break

            # Start the next chunk `overlap` characters before this one
            # ended, moved forward to the next word boundary. The
            # max(start + 1, ...) guarantees progress, so the loop always
            # ends.
            next_start = max(start + 1, end - overlap)
            next_space = section_text.find(" ", next_start, end)

            start = next_space + 1 if next_space != -1 else end

    return chunks
