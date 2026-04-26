"""RAG evaluation script: runs test questions through the full pipeline and checks faithfulness.

Run from project root:
    python -m ingest.evaluate
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = ["MONGODB_URI", "GOOGLE_API_KEY"]
missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
if missing:
    sys.exit(f"Missing required environment variables: {', '.join(missing)}")

from api.rag import answer_question

# ---------------------------------------------------------------------------
# Test suite: (question, expected_keywords)
# Keywords are case-insensitive substrings that should appear in a faithful answer.
# ---------------------------------------------------------------------------
TEST_CASES: list[tuple[str, list[str]]] = [
    (
        "What source documents does this chatbot reference?",
        ["bootcamp", "learning path", "intern", "faq", "training"],
    ),
    (
        "What is PM Accelerator and what does it offer to interns?",
        ["program", "internship", "ai", "engineer", "accelerator"],
    ),
    (
        "What will interns learn during the AI engineering program?",
        ["learn", "model", "llm", "pipeline", "training", "project"],
    ),
    (
        "What tools or technologies are used in the program?",
        ["python", "api", "llm", "model", "tool", "vector"],
    ),
    (
        "How long is the PM Accelerator internship program?",
        ["week", "month", "duration", "program", "period", "bootcamp"],
    ),
]


def check_faithfulness(answer: str, keywords: list[str]) -> tuple[bool, list[str], list[str]]:
    """Returns (passed, found_keywords, missing_keywords)."""
    lower_answer = answer.lower()
    found = [kw for kw in keywords if kw.lower() in lower_answer]
    missing = [kw for kw in keywords if kw.lower() not in lower_answer]
    # Pass if at least half the expected keywords appear
    passed = len(found) >= max(1, len(keywords) // 2)
    return passed, found, missing


async def run_evaluation() -> None:
    print("\n" + "=" * 80)
    print(f"{'RAG EVALUATION REPORT':^80}")
    print("=" * 80)

    passed_count = 0

    for i, (question, expected_keywords) in enumerate(TEST_CASES, start=1):
        print(f"\n[{i}/{len(TEST_CASES)}] Question: {question}")
        print(f"         Expected keywords: {expected_keywords}")

        try:
            answer, sources, chunks_used = await answer_question(question)
        except Exception as exc:
            print(f"         ERROR running pipeline: {exc}")
            continue

        passed, found, missing = check_faithfulness(answer, expected_keywords)
        status = "PASS ✓" if passed else "FAIL ✗"

        print(f"         Retrieved sources : {sources}")
        print(f"         Chunks used       : {chunks_used}")
        print(f"         Found keywords    : {found}")
        print(f"         Missing keywords  : {missing}")
        print(f"         Faithfulness      : {status}")
        print(f"         Answer (first 200 chars): {answer[:200]!r}")

        if passed:
            passed_count += 1

    print("\n" + "=" * 80)
    print(f"RESULT: {passed_count}/{len(TEST_CASES)} tests passed")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_evaluation())
