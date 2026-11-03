"""Ingestion pipeline (LangChain version): policies -> searchable vectors.

Steps:
    1. Load            read every .txt file in ams-data/policies/ and its
                       department folders as a Document
    2. Chunk           one chunk per handbook section (e.g. 6.2), with a
                       header naming its handbook, chapter and section
                       and a one-line summary of its chapter
    3. Embed + store   recreate the Qdrant collection, embed every chunk
                       with EMBEDDING_MODEL, and store it
                       (QdrantVectorStore.from_documents)

Strategy: same steps as basic-rag/ingest.py, but every step passes
LangChain Document objects (text + metadata) instead of plain strings
and dicts.

Caveats:
- Each file type has its own loader in LOADERS; only .txt exists so far
  (plain pathlib, no LangChain loader). A file with no loader stops
  ingestion with an error instead of being skipped silently.
- Chunking relies on the handbook layout: numbered chapters and
  sections, a blank line after every section. There is no size limit
  (today's largest section is 1,500 characters); tiny sections such as
  "CONTACT" join the chunk before them. Details: split_documents.
- Each subfolder is a department (policies/finance/...); its name is
  stored as "department". A file whose owner line names another
  department prints a warning (it is probably in the wrong folder).
- The header is part of the stored chunk text, so the LLM sees it too
  (basic-rag adds its header to the embedded text only). Embedding
  adds nomic's prefix (vector_store.py).
- Step 3 deletes everything in COLLECTION_NAME before storing. Re-run
  this script whenever a document, the chunking, or the model changes.
- Qdrant stores each chunk as {"page_content": ..., "metadata": {...}},
  so filters use "metadata.source" (basic-rag's payload is flat).
- Needs Ollama (with EMBEDDING_MODEL pulled) and Qdrant running.
"""

import re
from collections import Counter
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

from ams_assistant.config import COLLECTION_NAME, POLICIES_DIR, QDRANT_URL
from ams_assistant.vector_store import get_embeddings


def read_title(text: str) -> str:
    """Return the document title: the line just above the first line
    containing "Version:", or "" if there is none.

    Every AMS file starts like this:
        AMS
        FINANCE HANDBOOK
        Document ID: FIN-HBK-2026 | Version: 1.0 | ...
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for i, line in enumerate(lines[:10]):
        if "Version:" in line and i > 0:
            return lines[i - 1]

    return ""


def load_text_file(path: Path) -> list[Document]:
    """Load a UTF-8 text file as one Document.

    page_content holds the full text; metadata holds the file name
    ("source") and the title, so every chunk made from it later knows
    where it came from.
    """
    text = path.read_text(encoding="utf-8")
    return [
        Document(
            page_content=text,
            metadata={"source": path.name, "title": read_title(text)},
        )
    ]


# File extension -> loader. Every loader returns list[Document], since
# some formats give several (a PDF loader gives one per page). To
# support a new format, add one line here (and its package).
LOADERS = {
    ".txt": load_text_file,
}


# Owner line -> department folder, e.g. "Policy owner: Finance" ->
# "finance". First matching prefix wins, so the L&D line comes before
# plain "People Operations". Used only to spot a misplaced file.
OWNER_FOLDERS = [
    ("People Operations (Learning and Development)",
     "learning_and_development"),
    ("People Operations", "people"),
    ("IT and Security", "it_and_security"),
    ("Facilities", "administration_and_facilities"),
    ("Finance", "finance"),
    ("Legal and Compliance", "legal_and_compliance"),
]
OWNER_PATTERN = re.compile(r"(?:Policy|Document) owner: ([^|\n]+)")


def owner_folder(text: str) -> str | None:
    """Return the department folder named by the document's owner line,
    or None if there is no owner line or it is not in OWNER_FOLDERS."""
    match = OWNER_PATTERN.search(text)
    if match is None:
        return None

    owner = match.group(1).strip()
    for prefix, folder in OWNER_FOLDERS:
        if owner.startswith(prefix):
            return folder
    return None


def load_documents(folder: Path = POLICIES_DIR) -> list[Document]:
    """Load every file in the folder and its subfolders, sorted by path,
    with its loader. The subfolder name becomes metadata["department"]
    ("" for a file directly in the folder).

    Hidden files (.DS_Store, ...) are skipped. Raises ValueError for a
    file type with no loader.
    """
    documents = []

    # rglob("*") walks every subfolder too (like a recursive readdir).
    for path in sorted(folder.rglob("*")):
        if path.name.startswith(".") or not path.is_file():
            continue

        loader = LOADERS.get(path.suffix.lower())

        if loader is None:
            supported = ", ".join(LOADERS)
            raise ValueError(
                f"No loader for {path.name}; supported: {supported}"
            )

        department = path.parent.name if path.parent != folder else ""

        for doc in loader(path):
            expected = owner_folder(doc.page_content)
            if department and expected and expected != department:
                print(f"WARNING: {path.name} is in '{department}/' but "
                      f"its owner line says '{expected}'")
            doc.metadata["department"] = department
            documents.append(doc)

    return documents


# Handbook layout (see any file in ams-data/policies/):
#   "6. PARKING AND TRANSPORT POLICY"          chapter heading
#   "Reference: FAC-TRN-2026 | Version: ..."   chapter reference line
#   "6.2 PARKING IN BENGALURU"                 section heading
#   "6.2.1 Two-wheelers"                       subsection heading
CHAPTER_PATTERN = re.compile(r"(\d+)\. [A-Z]")
SECTION_PATTERN = re.compile(r"(\d+\.\d+) (.+)")
SUBSECTION_PATTERN = re.compile(r"\d+\.\d+\.\d+ ")
# Section 1.3 "How this handbook is organised": "Chapter 6: Parking ...".
TOC_PATTERN = re.compile(r"(?m)^Chapter (\d+): (.+)$")
# "Document ID: FAC-HBK-2026" (handbook) or "Reference: FAC-TRN-2026"
# (chapter).
REFERENCE_PATTERN = re.compile(r"(?:Document ID|Reference): ([^ |]+)")

# A section shorter than this (e.g. "6.6 CONTACT") joins the chunk
# before it instead of becoming a chunk of its own.
MIN_SECTION_CHARS = 150
# The chapter summary takes whole sentences until it is this long.
MIN_SUMMARY_CHARS = 80

# Title Case rules for upper-case headings.
SMALL_WORDS = {"a", "an", "and", "at", "by", "for", "in", "of", "on",
               "or", "the", "to"}
ACRONYMS = {"AI": "AI", "AMS": "AMS", "CCTV": "CCTV", "MFA": "MFA",
            "NDAS": "NDAs", "PTO": "PTO", "SERVICEDESK": "ServiceDesk",
            "VPN": "VPN"}


def nice_title(title: str) -> str:
    """Turn an upper-case heading into Title Case:
    "PARKING IN BENGALURU" -> "Parking in Bengaluru". A heading that
    is already mixed case ("Who this handbook applies to") is kept.
    """
    if not title.isupper():
        return title

    words = title.split()
    result = []

    for i, word in enumerate(words):
        core = word.strip("(),:")
        following = words[i + 1] if i + 1 < len(words) else ""

        if core in ACRONYMS:
            result.append(word.replace(core, ACRONYMS[core]))
        # "IT" is the department ("IT AND ACCESS", "OFFICE IT DESKS"),
        # otherwise the word "it" ("HOW IT WORKS").
        elif core == "IT" and following in ("AND", "DESKS"):
            result.append(word)
        elif i > 0 and core.lower() in SMALL_WORDS:
            result.append(word.lower())
        elif not any(char.isalpha() for char in word):
            result.append(word)  # a number such as "2026"
        else:
            # Capitalise the first letter, even after a "(".
            word = word.lower()
            first = next(j for j, char in enumerate(word) if char.isalpha())
            result.append(word[:first] + word[first].upper()
                          + word[first + 1:])

    return " ".join(result)


def chapter_summary(lines: list[str]) -> str:
    """Return the opening sentences of a chapter's first block (its
    first section, or an intro paragraph), until at least
    MIN_SUMMARY_CHARS long. Heading lines are skipped.

    Most chapters open with one sentence that sums them up: "This
    policy gives the detailed rules for AMS corporate cards." Some
    first sentences are short ("AMS provides a safe and healthy
    workplace."), so a second one is added.
    """
    body = [
        line for line in lines
        if not (SECTION_PATTERN.match(line) or SUBSECTION_PATTERN.match(line))
    ]
    sentences = re.split(r"(?<=\.)\s+", " ".join(body))
    summary = ""

    for sentence in sentences:
        summary = f"{summary} {sentence}".strip()
        if len(summary) >= MIN_SUMMARY_CHARS:
            break

    return summary


def split_documents(documents: list[Document]) -> list[Document]:
    """One chunk per section ("6.2 PARKING IN BENGALURU" and its
    subsections). In these handbooks a blank line ends every section.

    Every chunk starts with a header that places it in its handbook:
        Administration and Facilities Handbook > Chapter 6: Parking
        and Transport Policy > 6.2 Parking in Bengaluru
        About this chapter: This policy explains parking at each AMS
        office and the company cab service in India.
    Most sections never repeat what they are about ("5.3 LIMITS" never
    says "card"), so the header carries that context. The section the
    summary is taken from gets no "About" line (it would repeat itself).

    Also:
    - Text before chapter 1 (title block, TRAINING NOTE) is dropped.
    - A section under MIN_SECTION_CHARS joins the chunk before it, in
      the same chapter; the chunk keeps that earlier section's metadata.
    - Metadata: source, department, handbook, reference, chapter,
      chapter_title, section, section_title. Chapter 1 has no
      Reference line, so it uses the handbook's Document ID.

    Plain Python, not RecursiveCharacterTextSplitter: that splitter
    merges blocks up to its chunk_size regardless of sections.
    """
    chunks = []

    for doc in documents:
        text = doc.page_content
        handbook = nice_title(doc.metadata["title"])
        chapter_titles = {
            int(number): title for number, title in TOC_PATTERN.findall(text)
        }
        handbook_id = REFERENCE_PATTERN.search(text).group(1)
        chapter = None

        # \n\s*\n = a blank line (even one holding stray spaces).
        for block in re.split(r"\n\s*\n", text):
            lines = block.strip().splitlines()
            if not lines:
                continue

            # A new chapter: read its heading and reference line, then
            # its summary from the section that follows them.
            heading = CHAPTER_PATTERN.match(lines[0])
            if heading:
                chapter = int(heading.group(1))
                chapter_title = chapter_titles.get(
                    chapter, nice_title(lines[0].split(" ", 1)[1])
                )
                lines = lines[1:]
                reference = handbook_id
                if lines[0].startswith("Reference:"):
                    reference = REFERENCE_PATTERN.match(lines[0]).group(1)
                    lines = lines[1:]
                summary = chapter_summary(lines)
                is_first_section = True

                # An intro paragraph before the first section (only the
                # HR FAQ has one) is the summary itself, not a chunk.
                if not SECTION_PATTERN.match(lines[0]):
                    is_first_section = False
                    continue

            if chapter is None:
                continue

            section = SECTION_PATTERN.match(lines[0])
            if section is None:
                raise ValueError(
                    f"{doc.metadata['source']}: block does not start "
                    f"with a section heading: {lines[0]!r}"
                )
            body = "\n".join(lines)
            previous = chunks[-1].metadata if chunks else {}

            if (len(body) < MIN_SECTION_CHARS
                    and previous.get("source") == doc.metadata["source"]
                    and previous.get("chapter") == chapter):
                chunks[-1].page_content += "\n\n" + body
                continue

            number, title = section.group(1), nice_title(section.group(2))
            header = (f"{handbook} > Chapter {chapter}: {chapter_title} "
                      f"> {number} {title}\n")
            if not is_first_section:
                header += f"About this chapter: {summary}\n"
            is_first_section = False

            chunks.append(Document(
                page_content=header + body,
                metadata={
                    "source": doc.metadata["source"],
                    "department": doc.metadata["department"],
                    "handbook": handbook,
                    "reference": reference,
                    "chapter": chapter,
                    "chapter_title": chapter_title,
                    "section": number,
                    "section_title": title,
                },
            ))

    return chunks


def main():
    """Run the three ingestion steps and print what they made."""
    # Step 1: Load
    documents = load_documents()
    total_characters = sum(len(doc.page_content) for doc in documents)
    print(f"Loaded {len(documents)} documents ({total_characters} characters)")

    # Step 2: Chunk
    chunks = split_documents(documents)
    print(f"\nCreated {len(chunks)} chunks")

    # Chunks per document; Counter counts how often each source appears.
    for source, count in Counter(c.metadata["source"] for c in chunks).items():
        print(f"  {source}: {count} chunks")

    # Step 3: Embed + store. from_documents does it all in one call:
    # deletes the old collection (force_recreate=True), creates a new one,
    # calls embeddings.embed_documents on every chunk (in batches), and
    # stores each vector with its chunk's text and metadata.
    print(f"\nEmbedding and storing {len(chunks)} chunks "
          f"in '{COLLECTION_NAME}'...")
    embeddings = get_embeddings()
    vector_store = QdrantVectorStore.from_documents(
        chunks,
        embeddings,
        url=QDRANT_URL,
        collection_name=COLLECTION_NAME,
        force_recreate=True,
    )

    # Count what Qdrant actually stored; it should equal the chunk count.
    count = vector_store.client.count(
        collection_name=COLLECTION_NAME,
        exact=True,
    ).count
    print(f"Points in Qdrant: {count}")


if __name__ == "__main__":
    main()
