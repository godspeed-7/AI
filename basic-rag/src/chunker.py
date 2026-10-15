import re


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[dict]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size"
        )

    # Find numbered section headings, e.g.:
    # 1. PURPOSE AND SCOPE
    # 2. LEAVE YEAR AND GENERAL RULES
    heading_pattern = re.compile(
        r"(?m)^\s*(\d+)\.\s+(.+?)\s*$"
    )

    headings = list(heading_pattern.finditer(text))
    sections = []
    chunks = []

    # Keep the text before the first numbered heading.
    if headings and headings[0].start() > 0:
        introduction = text[:headings[0].start()].strip()

        if introduction:
            sections.append({
                "section": "INTRODUCTION",
                "text": introduction,
            })

    # Extract the text belonging to each section.
    for i, heading in enumerate(headings):
        section_start = heading.end()

        section_end = (
            headings[i + 1].start()
            if i + 1 < len(headings)
            else len(text)
        )

        sections.append({
            "section": heading.group(2).strip(),
            "text": text[section_start:section_end].strip(),
        })

    # Chunk each section independently.
    for section in sections:
        section_text = section["text"]
        start = 0
        chunk_index = 0

        while start < len(section_text):
            end = min(start + chunk_size, len(section_text))

            # Move the end backward to avoid cutting a word.
            if end < len(section_text):
                boundary = section_text.rfind(" ", start, end)

                if boundary > start:
                    end = boundary

            chunk = section_text[start:end].strip()

            if chunk:
                chunks.append({
                    "section": section["section"],
                    "chunk_index": chunk_index,
                    "text": chunk,
                })
                chunk_index += 1

            # Stop when the end of the section is reached.
            if end >= len(section_text):
                break

            # Calculate the next starting position with overlap.
            next_start = max(start + 1, end - overlap)

            # Start at a word boundary near the overlap position.
            next_space = section_text.find(" ", next_start, end)

            if next_space != -1:
                start = next_space + 1
            else:
                start = end

    return chunks
