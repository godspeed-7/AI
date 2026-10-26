"""Quick manual check: print one sample context under each compression
strategy (none, extractive, abstractive), to eyeball what
basic_rag/compressor.py keeps. Needs Ollama running; no Qdrant.
"""

from basic_rag.compressor import compress_context


def main():
    """Compress one fixed sample context with every strategy."""
    question = "How many annual leave days can an employee carry forward?"

    context = """
    Employees receive annual leave according to their employment terms.
    Unused annual leave may be carried forward subject to the policy limits.
    A maximum of five unused annual leave days may be carried forward.
    Any carry-forward is subject to the applicable eligibility conditions.
    Employees should consult the leave policy for further details.
    This policy also describes sick leave and parental leave entitlements.
    """

    for strategy in ["none", "extractive", "abstractive"]:
        print(f"\n{'=' * 20} {strategy.upper()} {'=' * 20}")

        compressed_context = compress_context(
            question=question,
            context=context,
            strategy=strategy,
            keep_sentences=3,
        )

        print(compressed_context)


if __name__ == "__main__":
    main()
