"""Extract indexable text from uploaded files."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".jsonl", ".log", ".yml", ".yaml", ".xml", ".html", ".htm"}


def extract_file_text(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in {".docx"}:
        return _extract_docx(path)
    if suffix in TEXT_SUFFIXES or suffix == "":
        return path.read_text(encoding="utf-8", errors="replace")
    raw = path.read_bytes()
    if b"\x00" in raw[:4096]:
        raise ValueError(f"Binary file '{path.name}' is not supported for RAG. Use PDF, DOCX, Markdown, or text.")
    return raw.decode("utf-8", errors="replace")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
        if text:
            return text
    except ImportError:
        logger.warning("pypdf not installed; PDF text extraction unavailable")
    except Exception as e:
        logger.warning("PDF extract failed for %s: %s", path.name, e)
    raise ValueError(f"Could not extract text from PDF '{path.name}'")


def _extract_docx(path: Path) -> str:
    try:
        import zipfile
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
        parts = [t.text for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t") if t.text]
        if not parts:
            parts = [n.text for n in root.iter() if n.text]
        text = "\n".join(p for p in parts if p and p.strip())
        if text.strip():
            return text
    except Exception as e:
        logger.warning("DOCX extract failed for %s: %s", path.name, e)
    raise ValueError(f"Could not extract text from DOCX '{path.name}'")
