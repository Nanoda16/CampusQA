"""Tests for citation extraction and validation (ai_service.engine.citation)."""

import sys
from pathlib import Path

# Ensure ai_service is importable
_AI_SERVICE = Path(__file__).resolve().parents[2] / "ai_service"
sys.path.insert(0, str(_AI_SERVICE))

from engine.citation import extract_citations, validate_citations


# ---------------------------------------------------------------------------
# extract_citations
# ---------------------------------------------------------------------------


def test_extract_citations():
    """[S1][S2] text [S3] → [1, 2, 3]"""
    result = extract_citations("[S1][S2] text [S3]")
    assert result == [1, 2, 3], f"Expected [1, 2, 3], got {result}"


def test_extract_citations_none():
    """No citations → []"""
    assert extract_citations("no citations here") == []
    assert extract_citations("") == []
    assert extract_citations("text with [no] brackets") == []


def test_extract_citations_duplicates():
    """Duplicate citations are returned as a single unique entry."""
    result = extract_citations("[S1] some text [S1] more [S2]")
    assert result == [1, 2], f"Expected [1, 2], got {result}"


def test_extract_citations_unsorted_input():
    """Citations are returned sorted regardless of input order."""
    result = extract_citations("[S3] first [S1] second [S2] third")
    assert result == [1, 2, 3], f"Expected [1, 2, 3], got {result}"


# ---------------------------------------------------------------------------
# validate_citations
# ---------------------------------------------------------------------------


def test_validate_all_valid():
    """All Sx match available sources → no change."""
    sources = [{"chunk_id": "a_0"}, {"chunk_id": "a_1"}, {"chunk_id": "a_2"}]
    answer = "Water is wet [S1]. The sky is blue [S2]. Gravity exists [S3]."
    result = validate_citations(answer, sources)
    assert result["answer"] == answer, "Answer should be unchanged"
    assert result["valid_count"] == 3
    assert result["invalid_count"] == 0
    assert result["citation_report"] == {1: "valid", 2: "valid", 3: "valid"}


def test_validate_invalid_removed():
    """S5 with only 3 sources → S5 removed."""
    sources = [{"chunk_id": "a_0"}, {"chunk_id": "a_1"}, {"chunk_id": "a_2"}]
    answer = "Some claim [S5] is supported by evidence."
    result = validate_citations(answer, sources)
    assert "S5" not in result["answer"], "S5 should be removed"
    assert "[S5]" not in result["answer"]
    assert result["valid_count"] == 0
    assert result["invalid_count"] == 1
    assert result["citation_report"] == {5: "invalid"}


def test_validate_mixed_valid_and_invalid():
    """Valid citations kept, invalid ones removed."""
    sources = [{"chunk_id": "a_0"}, {"chunk_id": "a_1"}, {"chunk_id": "a_2"}]
    answer = "Water is wet [S1]. Some claim [S5] is supported. Sky is blue [S2]."
    result = validate_citations(answer, sources)
    assert "[S1]" in result["answer"]
    assert "[S2]" in result["answer"]
    assert "[S5]" not in result["answer"]
    assert result["valid_count"] == 2
    assert result["invalid_count"] == 1
    assert result["citation_report"] == {1: "valid", 2: "valid", 5: "invalid"}


def test_validate_empty():
    """No citations → no change."""
    assert validate_citations("plain text without citations", []) == {
        "answer": "plain text without citations",
        "valid_count": 0,
        "invalid_count": 0,
        "citation_report": {},
    }


def test_validate_zero_sources():
    """When there are zero sources, all citations are invalid."""
    sources = []
    answer = "Some claim [S1] is supported [S2]."
    result = validate_citations(answer, sources)
    assert result["valid_count"] == 0
    assert result["invalid_count"] == 2
    assert "[S1]" not in result["answer"]
    assert "[S2]" not in result["answer"]
    # Check the answer is cleaned up (no double spaces)
    assert "Some claim is supported." == result["answer"]


def test_validate_multi_digit_number():
    """Multi-digit citation numbers (e.g. S42) work correctly."""
    sources = [{"chunk_id": f"a_{i}"} for i in range(50)]
    answer = "Deep research [S42] shows results."
    result = validate_citations(answer, sources)
    assert "[S42]" in result["answer"]
    assert result["valid_count"] == 1
    assert result["invalid_count"] == 0

    # Test out of range
    answer2 = "Beyond range [S99] is invalid."
    result2 = validate_citations(answer2, sources)
    assert "[S99]" not in result2["answer"]
    assert result2["invalid_count"] == 1
