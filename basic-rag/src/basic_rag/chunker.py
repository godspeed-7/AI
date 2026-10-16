
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

    # Match headings such as:
    # 3. ANNUAL LEAVE
    # 3.1 Standard entitlement
    # 3.1.1 Additional rules
    heading_pattern = re.compile(
        r"(?m)^[ \t]*(\d+(?:\.\d+)*\.?)[ \t]+(.+?)[ \t]*$"
    )

    headings = list(heading_pattern.finditer(text))
    sections = []

    if not headings:
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

        current_parent = ""

        for i, heading in enumerate(headings):
            heading_number = heading.group(1).rstrip(".")
            heading_title = heading.group(2).strip()

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

            sections.append({
                "section": f"{section_id} {heading_title}",
                "section_id": section_id,
                "section_title": heading_title,
                "parent_section": parent_section,
                "text": section_text,
            })

    chunks = []

    for section in sections:
        section_text = section["text"]

        if not section_text:
            continue

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

            next_start = max(start + 1, end - overlap)
            next_space = section_text.find(" ", next_start, end)

            start = next_space + 1 if next_space != -1 else end

    return chunks
