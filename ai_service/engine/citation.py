"""
Citation post-validation for LLM-generated answers.

Extracts ``[Sx]`` citation markers from generated text, validates them
against the set of available source chunks, and removes any citations
that reference non-existent sources.

This is a pure post-processing step — no LLM calls, no semantic checks.
"""

from __future__ import annotations

import re
from typing import Any

# Regex matching [S1], [S42], etc.
_CITATION_RE = re.compile(r"\[S(\d+)\]")


def extract_citations(answer: str) -> list[int]:
    """Extract unique, sorted citation numbers from ``[Sx]`` markers.

    Parameters
    ----------
    answer : str
        The LLM-generated answer text.

    Returns
    -------
    list[int]
        Sorted list of unique citation numbers found in the text.
        Returns an empty list when no citations are present.
    """
    if not answer:
        return []
    nums = [int(m) for m in _CITATION_RE.findall(answer)]
    return sorted(set(nums))


def validate_citations(answer: str, sources: list[dict]) -> dict[str, Any]:
    """Validate citations in an answer against the available source list.

    Each ``[Sx]`` marker in the answer is checked against the number of
    provided sources.  Citations with an index outside the valid range
    ``[1, len(sources)]`` are removed from the text.

    Parameters
    ----------
    answer : str
        The LLM-generated answer potentially containing ``[Sx]`` markers.
    sources : list[dict]
        The list of retrieved source chunks.  Source numbering in the
        context is 1-based (``S1`` = first source), so a citation is
        valid iff ``1 <= x <= len(sources)``.

    Returns
    -------
    dict
        ``{
            "answer": str,          # Cleaned answer with invalid markers removed
            "valid_count": int,     # Number of valid (kept) citations
            "invalid_count": int,   # Number of invalid (removed) citations
            "citation_report": dict # {citation_number: "valid"|"invalid", ...}
        }``
    """
    if not answer:
        return {
            "answer": answer,
            "valid_count": 0,
            "invalid_count": 0,
            "citation_report": {},
        }

    source_count = len(sources)
    citation_nums = extract_citations(answer)

    # Build per-citation status  (one entry per unique number)
    citation_report: dict[int, str] = {}
    for num in citation_nums:
        if num not in citation_report:
            citation_report[num] = "valid" if 1 <= num <= source_count else "invalid"

    # Separate valid / invalid
    invalid_nums = sorted(
        [num for num, status in citation_report.items() if status == "invalid"],
        reverse=True,  # descending to avoid position shifts
    )

    # Remove invalid citation markers from answer
    cleaned = answer
    for num in invalid_nums:
        cleaned = re.sub(rf"\[S{num}\]", "", cleaned)

    # Tidy up whitespace left behind by removals
    cleaned = re.sub(r" +", " ", cleaned)
    # Remove space before punctuation (e.g. "text ." → "text.")
    cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
    cleaned = cleaned.strip()

    valid_count = sum(1 for s in citation_report.values() if s == "valid")
    invalid_count = sum(1 for s in citation_report.values() if s == "invalid")

    return {
        "answer": cleaned,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "citation_report": citation_report,
    }
