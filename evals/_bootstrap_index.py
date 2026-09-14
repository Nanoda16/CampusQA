"""Bootstrapping script: build the FAISS + BM25 index from knowledge_docs/.

Why this exists instead of `python cli.py --rebuild`:
  cli.py's cmd_rebuild calls `_delete_index()` BEFORE constructing
  RAGPipeline().  RAGPipeline.__init__ unconditionally builds a Generator(),
  which raises when DEEPSEEK_API_KEY is absent.  So the CLI deletes the index
  and then dies, leaving the project with no index at all.

  Index construction only needs the embedding model -- no LLM.  This script
  sets a placeholder key so Generator() can be constructed (the OpenAI client
  is never called during indexing), then calls index_documents() directly.
"""
import os
import sys

AI_DIR = r"D:\b1ss\CampusQA\ai_service"
sys.path.insert(0, AI_DIR)

os.environ.setdefault("DEEPSEEK_API_KEY", "sk-placeholder-not-used-for-indexing")

from engine.pipeline import RAGPipeline  # noqa: E402

print("constructing pipeline (embedding model load takes a moment)...")
pipe = RAGPipeline()
print("pipeline ready; indexing documents...")

result = pipe.index_documents(chunk_size=500, chunk_overlap=50)

print("=" * 60)
print("docs_count    :", result.get("docs_count"))
print("chunks_count  :", result.get("chunks_count"))
print("indexed_count :", result.get("indexed_count"))
print("time_seconds  :", result.get("time_seconds"))
print("=" * 60)
print("stats:", pipe.get_stats())
