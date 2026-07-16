"""
TDD tests for ArtifactStore (ai_service/engine/artifact_store.py).

Covers:
- Save / Load round-trip with content verification
- Delete (existent and non-existent)
- List docs (populated and empty)
- Rebuild index from artifacts (FAISS + BM25)
- Concurrent write safety (multiple threads save/delete)
- Pipeline auto-rebuild on startup when faiss.index is missing
"""

from __future__ import annotations

import sys
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure ai_service is importable (namespace package, no __init__.py)
_AI_SERVICE = Path(__file__).resolve().parents[2] / "ai_service"
sys.path.insert(0, str(_AI_SERVICE))

import numpy as np
import pytest

from engine.artifact_store import ArtifactStore

# Ensure engine submodules exist as attributes (namespace package workaround)
import engine.embedding  # noqa: E402
import engine.vector_store  # noqa: E402
import engine.bm25_retriever  # noqa: E402

# ===================================================================
# 1. Basic CRUD
# ===================================================================


class TestArtifactStoreBasic:
    """Core CRUD: save, load, delete, list."""

    def test_save_load(self, tmp_path: Path):
        """Save a doc then load it — content and metadata must match."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))

        doc_id = "test_doc_001"
        chunks = [
            {"content": "这是第一段内容", "chunk_index": 0},
            {"content": "这是第二段内容", "chunk_index": 1},
        ]
        metadata = {
            "created_at": "2025-01-01T00:00:00",
            "doc_length": 100,
            "chunk_count": 2,
        }

        store.save_doc(
            doc_id,
            chunks,
            metadata=metadata,
            title="测试文档",
            category="测试",
            source_url="https://example.com/test",
        )

        loaded = store.load_doc(doc_id)
        assert loaded is not None
        assert loaded["doc_id"] == doc_id
        assert loaded["title"] == "测试文档"
        assert loaded["category"] == "测试"
        assert loaded["source_url"] == "https://example.com/test"
        assert len(loaded["chunks"]) == 2
        assert loaded["chunks"][0]["content"] == "这是第一段内容"
        assert loaded["chunks"][0]["chunk_index"] == 0
        assert loaded["chunks"][0]["vector_id"] == "test_doc_001_0"
        assert loaded["metadata"]["chunk_count"] == 2

    def test_save_load_without_metadata(self, tmp_path: Path):
        """Save without metadata — auto-populated fields should exist."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        store.save_doc(
            "minimal_doc",
            [{"content": "简约内容", "chunk_index": 0}],
        )
        loaded = store.load_doc("minimal_doc")
        assert loaded is not None
        assert loaded["metadata"]["chunk_count"] == 1
        assert loaded["metadata"]["doc_length"] == 4  # len("简约内容")
        assert "created_at" in loaded["metadata"]

    def test_load_nonexistent(self, tmp_path: Path):
        """Loading a non-existent doc must return None."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        assert store.load_doc("nonexistent") is None

    def test_delete(self, tmp_path: Path):
        """Delete a doc, then load must return None."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        store.save_doc("doc_to_del", [{"content": "delete me", "chunk_index": 0}], {})
        assert store.load_doc("doc_to_del") is not None

        assert store.delete_doc("doc_to_del") is True
        assert store.load_doc("doc_to_del") is None

    def test_delete_nonexistent(self, tmp_path: Path):
        """Deleting a non-existent doc must return False."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        assert store.delete_doc("nonexistent") is False

    def test_list_docs(self, tmp_path: Path):
        """List docs returns all saved doc IDs."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        store.save_doc("doc_a", [{"content": "a", "chunk_index": 0}], {})
        store.save_doc("doc_b", [{"content": "b", "chunk_index": 0}], {})

        docs = store.list_docs()
        assert "doc_a" in docs
        assert "doc_b" in docs
        assert len(docs) == 2

    def test_list_docs_empty(self, tmp_path: Path):
        """Empty artifact dir must return an empty list."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        assert store.list_docs() == []


# ===================================================================
# 2. Rebuild index
# ===================================================================


class TestArtifactStoreRebuild:
    """Rebuild FAISS + BM25 from artifact files."""

    def test_rebuild_index(self, tmp_path: Path):
        """Rebuild from artifacts — vector count must match chunk count."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))

        # Save 2 docs with a combined 3 chunks
        store.save_doc(
            "doc_1",
            [
                {"content": "河海大学水利工程专业排名前列", "chunk_index": 0},
                {"content": "河海大学计算机学院位于南京", "chunk_index": 1},
            ],
            metadata={"created_at": "2025-01-01", "doc_length": 200, "chunk_count": 2},
            title="水利工程",
            category="工程",
            source_url="https://example.com/1",
        )
        store.save_doc(
            "doc_2",
            [{"content": "南京大学计算机科学系介绍", "chunk_index": 0}],
            metadata={"created_at": "2025-01-02", "doc_length": 100, "chunk_count": 1},
            title="计算机科学",
            category="科学",
            source_url="https://example.com/2",
        )

        # Mock heavy dependencies (imported inline inside rebuild_index)
        with (
            patch("engine.embedding") as mock_embed,
            patch("engine.vector_store.VectorStore") as mock_vs_cls,
            patch("engine.bm25_retriever.BM25Retriever") as mock_bm25_cls,
        ):
            mock_vs = MagicMock()
            mock_vs_cls.return_value = mock_vs
            mock_bm25 = MagicMock()
            mock_bm25_cls.return_value = mock_bm25

            mock_embed.embed.return_value = np.zeros((3, 512), dtype=np.float32)

            result = store.rebuild_index()

            assert result["docs_count"] == 2
            assert result["chunks_count"] == 3
            assert result["time_seconds"] >= 0.0

            # VectorStore.build() called with 3 vectors
            mock_vs.build.assert_called_once()
            args, _ = mock_vs.build.call_args
            assert args[0].shape[0] == 3
            mock_vs.save.assert_called_once()

            # BM25 built with 3 texts
            mock_bm25.build.assert_called_once()
            build_args, _ = mock_bm25.build.call_args
            assert len(build_args[0]) == 3  # 3 texts
            assert len(build_args[1]) == 3  # 3 chunk_ids
            mock_bm25.save.assert_called_once()

    def test_rebuild_empty(self, tmp_path: Path):
        """Rebuild with no artifacts returns zero counts."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        result = store.rebuild_index()
        assert result["docs_count"] == 0
        assert result["chunks_count"] == 0
        assert result["time_seconds"] == 0.0

    def test_rebuild_metadata_structure(self, tmp_path: Path):
        """Rebuilt vector store metadata must contain all expected keys."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        store.save_doc(
            "simple_doc",
            [{"content": "仅此一段", "chunk_index": 0}],
            title="简明",
            category="文摘",
        )

        with (
            patch("engine.embedding") as mock_embed,
            patch("engine.vector_store.VectorStore") as mock_vs_cls,
            patch("engine.bm25_retriever.BM25Retriever") as mock_bm25_cls,
        ):
            mock_vs = MagicMock()
            mock_vs_cls.return_value = mock_vs
            mock_bm25 = MagicMock()
            mock_bm25_cls.return_value = mock_bm25
            mock_embed.embed.return_value = np.zeros((1, 512), dtype=np.float32)

            store.rebuild_index()

            # Check metadata passed to VectorStore.build() (positional arg)
            mock_vs.build.assert_called_once()
            args, _ = mock_vs.build.call_args
            vectors_arg, meta_list = args[0], args[1]
            assert len(meta_list) == 1
            entry = meta_list[0]
            assert entry["doc_id"] == "simple_doc"
            assert entry["title"] == "简明"
            assert entry["category"] == "文摘"
            assert entry["chunk_id"] == "simple_doc_0"
            assert "content" in entry
            assert "chunk_index" in entry


# ===================================================================
# 3. Concurrent safety
# ===================================================================


class TestArtifactStoreConcurrency:
    """Thread-safe writes to artifact files."""

    def test_concurrent_save(self, tmp_path: Path):
        """Multiple threads save simultaneously — all documents persisted."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        n = 10

        def _save(i: int) -> None:
            store.save_doc(
                f"concurrent_{i}",
                [{"content": f"content_{i}", "chunk_index": 0}],
                {},
            )

        threads = [threading.Thread(target=_save, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        docs = store.list_docs()
        assert len(docs) == n
        for i in range(n):
            assert f"concurrent_{i}" in docs

    def test_concurrent_save_and_delete(self, tmp_path: Path):
        """Concurrent save + delete must not raise exceptions."""
        store = ArtifactStore(artifact_dir=str(tmp_path / "artifacts"))
        errors: list[Exception] = []

        def _writer() -> None:
            for i in range(30):
                try:
                    store.save_doc(
                        f"shared_{i % 5}",
                        [{"content": f"write {i}", "chunk_index": 0}],
                        {},
                    )
                except Exception as e:
                    errors.append(e)

        def _deleter() -> None:
            for i in range(30):
                try:
                    store.delete_doc(f"shared_{i % 5}")
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=_writer)
        t2 = threading.Thread(target=_deleter)
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        assert not errors, f"Concurrent access raised: {errors}"


# ===================================================================
# 4. Pipeline auto-rebuild on startup
# ===================================================================


class TestPipelineAutoRebuild:
    """RAGPipeline._check_auto_rebuild triggers rebuild when index is missing."""

    def test_rebuild_triggered_when_index_missing(self):
        """When faiss.index is missing and artifacts exist, rebuild is called."""
        import engine.pipeline as pipeline_mod

        pl = pipeline_mod.RAGPipeline.__new__(pipeline_mod.RAGPipeline)
        pl.vector_store = MagicMock()
        pl.retriever = MagicMock()
        pl.generator = MagicMock()
        pl.bm25_retriever = MagicMock()
        pl._bm25_results = []
        pl._reranker_enabled = False
        pl.reranker = None

        with (
            patch("os.path.isfile", return_value=False),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=["doc.json"]),
            patch("engine.artifact_store.ArtifactStore") as mock_store_cls,
        ):
            mock_store = MagicMock()
            mock_store.rebuild_index.return_value = {
                "docs_count": 2,
                "chunks_count": 5,
            }
            mock_store_cls.return_value = mock_store

            pl._check_auto_rebuild()

            mock_store.rebuild_index.assert_called_once()
            pl.vector_store.load.assert_called_once()

    def test_rebuild_skipped_when_index_exists(self):
        """When faiss.index exists, rebuild must NOT be called."""
        import engine.pipeline as pipeline_mod

        pl = pipeline_mod.RAGPipeline.__new__(pipeline_mod.RAGPipeline)
        pl.vector_store = MagicMock()
        pl.retriever = MagicMock()
        pl.generator = MagicMock()
        pl.bm25_retriever = MagicMock()
        pl._bm25_results = []
        pl._reranker_enabled = False
        pl.reranker = None

        with (
            patch("os.path.isfile", return_value=True),
            patch("engine.artifact_store.ArtifactStore") as mock_store_cls,
        ):
            mock_store = MagicMock()
            mock_store_cls.return_value = mock_store

            pl._check_auto_rebuild()

            mock_store.rebuild_index.assert_not_called()
            pl.vector_store.load.assert_not_called()

    def test_rebuild_skipped_when_no_artifact_dir(self):
        """When artifact dir does not exist, rebuild must NOT be called."""
        import engine.pipeline as pipeline_mod

        pl = pipeline_mod.RAGPipeline.__new__(pipeline_mod.RAGPipeline)
        pl.vector_store = MagicMock()
        pl.retriever = MagicMock()
        pl.generator = MagicMock()
        pl.bm25_retriever = MagicMock()
        pl._bm25_results = []
        pl._reranker_enabled = False
        pl.reranker = None

        with (
            patch("os.path.isfile", return_value=False),
            patch("os.path.isdir", return_value=False),
            patch("engine.artifact_store.ArtifactStore") as mock_store_cls,
        ):
            pl._check_auto_rebuild()

            mock_store_cls.return_value.rebuild_index.assert_not_called()

    def test_rebuild_skipped_when_no_artifact_files(self):
        """When artifact dir is empty, rebuild must NOT be called."""
        import engine.pipeline as pipeline_mod

        pl = pipeline_mod.RAGPipeline.__new__(pipeline_mod.RAGPipeline)
        pl.vector_store = MagicMock()
        pl.retriever = MagicMock()
        pl.generator = MagicMock()
        pl.bm25_retriever = MagicMock()
        pl._bm25_results = []
        pl._reranker_enabled = False
        pl.reranker = None

        with (
            patch("os.path.isfile", return_value=False),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=[]),
            patch("engine.artifact_store.ArtifactStore") as mock_store_cls,
        ):
            pl._check_auto_rebuild()

            mock_store_cls.return_value.rebuild_index.assert_not_called()
