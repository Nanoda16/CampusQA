"""
pytest fixtures for ai_service tests.
"""

import sys
import os
from unittest.mock import MagicMock

import pytest

# Ensure ai_service/ is on sys.path
_ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)


@pytest.fixture
def mock_search():
    """Factory: returns a mock ``VectorStore`` whose ``.search()`` returns
    results with pre-determined *scores*."""

    def _make(scores: list[float]) -> MagicMock:
        mock = MagicMock()
        results = []
        for i, score in enumerate(scores):
            results.append({
                "content": f"chunk {i}",
                "doc_id": f"doc_{i}",
                "title": f"Title {i}",
                "category": "test",
                "source_url": f"http://test.com/{i}",
                "score": score,
                "chunk_index": i,
            })
        mock.search.return_value = results
        return mock

    return _make
