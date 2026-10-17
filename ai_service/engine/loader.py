"""
Document loader for the RAG engine.
Loads markdown/text documents from knowledge_docs/ directory.
"""

import hashlib
import logging
import os
import re
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def default_knowledge_dir() -> str:
    """Return the project's default knowledge-base directory.

    This is the one folder that holds every indexable document — the seed
    corpus shipped as a release asset *and* the files users upload through the
    UI.  Rebuilding the index always scans this folder, so it is the single
    source of truth for "what should be searchable".

    Overridable with the ``KNOWLEDGE_DIR`` environment variable (absolute, or
    relative to the repository root).
    """
    configured = os.environ.get("KNOWLEDGE_DIR", "").strip()
    if configured:
        if not os.path.isabs(configured):
            repo_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "../..")
            )
            configured = os.path.join(repo_root, configured)
        return os.path.abspath(configured)

    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../knowledge_docs")
    )


# Extensions the directory scanner accepts.  Only plain text: binary formats
# are normalised into .md at upload time, so this folder always stays
# human-readable and diffable.
INDEXABLE_EXTENSIONS = (".md", ".txt")


def _iter_text_files(knowledge_dir: str):
    """Yield every indexable file under *knowledge_dir*, sorted by path."""
    found = []
    for ext in INDEXABLE_EXTENSIONS:
        found.extend(Path(knowledge_dir).rglob(f"*{ext}"))
    return sorted(found)


def _safe_segment(value: str, max_len: int = 60) -> str:
    """Turn arbitrary text into a filesystem-safe path segment."""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", value or "").strip(" ._")
    return cleaned[:max_len] or "doc"


def write_content_doc(
    doc: dict,
    category: str | None = None,
    suffix: str = ".md",
) -> str:
    """Persist a parsed document into the knowledge directory as plain text.

    Uploads are normalised this way so that the directory stays the single
    source of truth: whatever lands here is picked up by the next full rebuild,
    no matter whether it arrived as a seed corpus or as a UI upload.

    Parameters
    ----------
    doc : dict
        A document dict as returned by :func:`load_file` (``title``,
        ``content``, ``source_url`` are used).
    category : str, optional
        Sub-folder to place the file in.  Defaults to ``uploads``.  The folder
        name doubles as the document's ``category`` when the directory is
        re-scanned.
    suffix : str
        File extension to write (default ``.md``).

    Returns
    -------
    str
        Absolute path of the written file.  Its md5 is the document's
        ``doc_id``, which means the same file always maps to the same id.
    """
    base = default_knowledge_dir()
    target_dir = os.path.join(base, _safe_segment(category or "uploads", 40))
    os.makedirs(target_dir, exist_ok=True)

    stem = _safe_segment(doc.get("title") or "doc")
    # A short suffix keeps two uploads that share a title from colliding
    # without making the file name meaningless.
    file_name = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
    path = os.path.join(target_dir, file_name)

    lines = [f"# {doc.get('title') or stem}", ""]
    if doc.get("source_url"):
        lines.extend([f"> 来源: {doc['source_url']}", ""])
    lines.append(doc.get("content") or "")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    logger.info("Wrote uploaded document into knowledge dir: %s", path)
    return path


def _read_file_with_bom_handling(file_path: str) -> str:
    """Read file content, handling UTF-8 BOM."""
    with open(file_path, "rb") as f:
        raw = f.read()
    # Strip UTF-8 BOM if present
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8")


def _clean_text(text: str) -> str:
    """Clean text content:
    - Strip boilerplate lines starting with ``上一篇：`` or ``下一篇：``
    - Strip navigation menu artifacts (lines with only ``|``, ``-``, whitespace)
    - Deduplicate consecutive empty lines
    - Strip leading/trailing whitespace per line
    """
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Strip boilerplate navigation lines
        if stripped.startswith("上一篇：") or stripped.startswith("下一篇："):
            continue
        # Strip table/navigation artifacts (only |, -, and whitespace)
        if re.match(r"^[\s\|\-]+$", stripped):
            continue
        # Strip leading/trailing whitespace per line
        cleaned.append(stripped)

    # Deduplicate consecutive empty lines
    result = []
    prev_empty = False
    for line in cleaned:
        if line == "":
            if not prev_empty:
                result.append(line)
                prev_empty = True
        else:
            result.append(line)
            prev_empty = False

    return "\n".join(result).strip()


def _extract_title(content: str, filename: str) -> str:
    """Extract title from content.
    Prefer the first ``# Title`` (h1) from content; fall back to filename.
    """
    for line in content.splitlines():
        stripped = line.strip()
        # Match h1 headings but not h2+
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    # Fallback: filename without extension
    return Path(filename).stem


def _extract_source_url(content: str) -> str:
    """Extract source URL from ``> 来源:`` or ``> 来源：`` pattern."""
    match = re.search(r">\s*来源[：:]\s*(https?://\S+)", content)
    if match:
        return match.group(1).rstrip(")")
    return ""


def _compute_doc_id(file_path: str) -> str:
    """Compute md5 hex digest from the absolute file path."""
    absolute = os.path.abspath(file_path)
    return hashlib.md5(absolute.encode("utf-8")).hexdigest()


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "pypdf is required to read PDF files. "
            "Install it with: pip install pypdf"
        )

    reader = PdfReader(file_path)
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


def _extract_text_from_docx(file_path: str) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document
    except ImportError:
        raise ImportError(
            "python-docx is required to read DOCX files. "
            "Install it with: pip install python-docx"
        )

    doc = Document(file_path)
    paragraphs: list[str] = []
    for para in doc.paragraphs:
        if para.text:
            paragraphs.append(para.text)
    return "\n".join(paragraphs)


def _build_doc(file_path: str, raw_content: str | None = None) -> dict:
    """Build a document dict from a file path.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the document file.
    raw_content : str, optional
        Pre-extracted raw text content (for binary formats such as PDF/DOCX).
        When ``None`` (default), the file is read as UTF-8 text.

    Returns
    -------
    dict
        ``{"doc_id", "title", "content", "category", "source_url", "file_path"}``
    """
    path = Path(file_path)
    if raw_content is None:
        raw = _read_file_with_bom_handling(file_path)
    else:
        raw = raw_content
    content = _clean_text(raw)
    title = _extract_title(raw, path.name)
    source_url = _extract_source_url(raw)
    doc_id = _compute_doc_id(file_path)
    category = path.parent.name  # immediate parent directory name

    return {
        "doc_id": doc_id,
        "title": title,
        "content": content,
        "category": category,
        "source_url": source_url,
        "file_path": str(path.absolute()),
    }


def load_knowledge_docs(knowledge_dir: str | None = None) -> list[dict]:
    """Load all knowledge documents from the *knowledge_docs* directory.

    Parameters
    ----------
    knowledge_dir : str, optional
        Path to the knowledge docs directory.  When ``None`` (default) it is
        resolved relative to ``ai_service/engine/``:
        ``<repo_root>/knowledge_docs/``.

    Returns
    -------
    list[dict]
        Each dict has keys ``doc_id``, ``title``, ``content``, ``category``,
        ``source_url``, ``file_path``.

    Raises
    ------
    FileNotFoundError
        Only when *knowledge_dir* was passed explicitly and does not exist —
        a typo in a user-supplied path must not silently look like "0 documents
        indexed".  The default directory is created on demand instead.
    """
    explicit = knowledge_dir is not None

    if knowledge_dir is None:
        knowledge_dir = default_knowledge_dir()
    knowledge_dir = os.path.abspath(knowledge_dir)

    if not os.path.isdir(knowledge_dir):
        if explicit:
            raise FileNotFoundError(
                f"Knowledge directory not found: {knowledge_dir}"
            )
        # Fresh install: there is no seed corpus yet, so make the drop-in
        # folder instead of failing.  ``index_documents`` then reports
        # "0 documents" and the UI can tell the user to upload something.
        os.makedirs(knowledge_dir, exist_ok=True)
        logger.warning(
            "Knowledge directory did not exist, created empty: %s", knowledge_dir
        )
        return []

    docs = []
    for text_path in _iter_text_files(knowledge_dir):
        file_path = str(text_path)

        # Skip files that are too small (empty / minimal)
        if os.path.getsize(file_path) < 50:
            continue

        docs.append(_build_doc(file_path))

    return docs


def load_file(file_path: str) -> dict:
    """Load a single file and return it in the same dict format.

    Parameters
    ----------
    file_path : str
        Path to the file.  Supported extensions: ``.md``, ``.txt``, ``.pdf``,
        ``.docx``, ``.doc`` (best-effort).

    Returns
    -------
    dict
        Same schema as :func:`load_knowledge_docs`.

    Raises
    ------
    FileNotFoundError
        If *file_path* does not exist.
    ValueError
        If the file extension is not supported, or legacy ``.doc`` cannot
        be parsed (with a suggestion to convert to ``.docx`` / ``.pdf``).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    if ext == ".md" or ext == ".txt":
        return _build_doc(file_path)

    if ext == ".pdf":
        raw = _extract_text_from_pdf(file_path)
        return _build_doc(file_path, raw_content=raw)

    if ext == ".docx":
        raw = _extract_text_from_docx(file_path)
        return _build_doc(file_path, raw_content=raw)

    # Legacy .doc — best-effort via python-docx; most will fail gracefully
    if ext == ".doc":
        try:
            raw = _extract_text_from_docx(file_path)
            return _build_doc(file_path, raw_content=raw)
        except Exception as exc:
            raise ValueError(
                f"Cannot parse legacy .doc file: {file_path}. "
                f"python-docx cannot read the old OLE2 format. "
                f"Please convert the file to .docx or .pdf and try again."
            ) from exc

    raise ValueError(
        f"Unsupported file type: '{ext}'. "
        f"Supported extensions: .md, .txt, .pdf, .docx, .doc (best-effort)."
    )


def get_doc_count(knowledge_dir: str | None = None) -> int:
    """Return the total number of documents in *knowledge_docs*.

    Parameters
    ----------
    knowledge_dir : str, optional
        Passed through to :func:`load_knowledge_docs`.

    Returns
    -------
    int
    """
    return len(load_knowledge_docs(knowledge_dir))
