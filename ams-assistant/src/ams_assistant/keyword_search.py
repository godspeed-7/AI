"""Keyword search (BM25) over a collection's points, held in memory.

In:  a collection name and a search text.
Out: keyword_search(collection, text, k) -> the k Documents whose words
     best match the text, best first.

Strategy: BM25 scores a point by the question words it contains: a word
counts more when it is rare across the collection (e.g. "teams" vs
"leave") and when it appears often in the point, less for long points.
Vector search matches meaning; this matches exact words, so the two
miss different questions. pipeline.py merges both rankings (RRF).
Hand-written (Okapi BM25) so the quick test needs no new library: 370
points fit in memory, and scoring them all takes milliseconds.

Caveats:
- Exact words only: "freelance" never matches "outside work".
- The index is built from Qdrant once per collection per run: after
  re-ingesting, start a new run.
- A test version: in production, BM25 vectors would be stored in
  Qdrant next to the dense ones (fastembed) and merged there.
"""

import math
import re
from collections import Counter
from functools import cache

from langchain_core.documents import Document

from ams_assistant.vector_store import get_vector_store

# BM25's usual settings: K1 limits how much repeating a word helps,
# B how much a long point is marked down.
K1 = 1.5
B = 0.75

# Words, keeping codes and hyphenated terms whole: "HR-LEAVE-IN-2026",
# "co-working", "l5".
WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def words(text: str) -> list[str]:
    """The text's words, lowercased."""
    return WORD.findall(text.lower())


class KeywordIndex:
    """Word counts for every point, ready for BM25 scoring."""

    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs
        self.counts = [Counter(words(doc.page_content)) for doc in docs]
        self.lengths = [sum(count.values()) for count in self.counts]
        self.average_length = sum(self.lengths) / len(docs)
        # How many points contain each word (for its rarity, "idf").
        self.points_with = Counter(
            word for count in self.counts for word in count
        )

    def idf(self, word: str) -> float:
        """A word's weight: high when few points contain it."""
        n = self.points_with[word]
        return math.log(1 + (len(self.docs) - n + 0.5) / (n + 0.5))

    def score(self, query: list[str], i: int) -> float:
        """BM25 score of point i for the query words."""
        count, length = self.counts[i], self.lengths[i]
        total = 0.0
        for word in query:
            tf = count[word]
            if tf:
                norm = K1 * (1 - B + B * length / self.average_length)
                total += self.idf(word) * tf * (K1 + 1) / (tf + norm)
        return total

    def search(self, text: str, k: int) -> list[Document]:
        """The k best-scoring points, best first."""
        query = words(text)
        scores = [self.score(query, i) for i in range(len(self.docs))]
        best = sorted(range(len(self.docs)), key=lambda i: scores[i],
                      reverse=True)[:k]
        return [self.docs[i] for i in best]


@cache
def get_keyword_index(collection: str) -> KeywordIndex:
    """Every point in the collection, read from Qdrant once."""
    store = get_vector_store(collection)
    points, _next_page = store.client.scroll(
        collection_name=collection, limit=10_000, with_payload=True,
    )
    return KeywordIndex([
        Document(page_content=point.payload["page_content"],
                 metadata=point.payload["metadata"])
        for point in points
    ])


def keyword_search(collection: str, text: str, k: int) -> list[Document]:
    """The k points of the collection whose words best match the text.
    Each is a copy, so callers can change its metadata safely."""
    return [Document(page_content=doc.page_content,
                     metadata=dict(doc.metadata))
            for doc in get_keyword_index(collection).search(text, k)]
