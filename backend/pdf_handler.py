"""
PDF Handler for School LLM
Extracts text from PDFs, preserves section structure for RAG, and keeps math notation readable.
"""
import io
import logging
import re
from typing import Any, Dict, List, Optional

import requests
from PyPDF2 import PdfReader

from config import settings

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    import tiktoken
except ImportError:
    tiktoken = None

logger = logging.getLogger(__name__)


class PDFHandler:
    """Handle PDF extraction and processing with smart token-based chunking."""

    _SECTION_HEADING_RE = re.compile(r"^(?P<code>\d+(?:\.\d+)+)\s+(?P<title>.+)$")
    _SECTION_CODE_ONLY_RE = re.compile(r"^(?P<code>\d+(?:\.\d+)+)\s*$")
    _EXERCISE_HEADING_RE = re.compile(
        r"^(?P<label>exercise)\s+(?P<code>\d+(?:\.\d+)+)\s*(?P<title>.*)$",
        re.IGNORECASE,
    )
    _EXAMPLE_HEADING_RE = re.compile(
        r"^(?P<label>example\s+\d+)\s*:?\s*(?P<title>.*)$",
        re.IGNORECASE,
    )
    _CHAPTER_RE = re.compile(r"\bchapter\s*[:\-]?\s*(\d+)\b|\bchapter(\d+)\b", re.IGNORECASE)
    # Matches plain chapter headings like "1 Our Earth" or "19 Human Rights"
    _CHAPTER_HEADING_RE = re.compile(
        r"^(?P<code>\d{1,3})\s+(?P<title>[A-Z][A-Za-z][A-Za-z0-9\s&\-:,/']+)$"
    )

    def __init__(self, chunk_size_tokens: int = 750, chunk_overlap_tokens: int = 100):
        self.chunk_size_tokens = max(500, min(1000, chunk_size_tokens))
        self.chunk_overlap_tokens = chunk_overlap_tokens

        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo") if tiktoken else None
        except Exception:
            self.tokenizer = None
            logger.warning("Failed to initialize tokenizer; falling back to character-based chunking")

        logger.info(
            "PDFHandler initialized with %s token chunks and %s token overlap",
            self.chunk_size_tokens,
            self.chunk_overlap_tokens,
        )

    def _count_tokens(self, text: str) -> int:
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except Exception as exc:
                logger.warning("Tokenizer error: %s; using character estimate", exc)
        return len(text) // 4

    def _count_tokens_estimate(self, text: str) -> int:
        return len(text) // 4

    def _normalize_text(self, text: str) -> str:
        text = (text or "").replace("\u00a0", " ")
        text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        return text

    def _clean_line_text(self, text: str) -> str:
        text = self._normalize_text(text)
        text = text.replace("\t", " ")
        text = re.sub(r"[ ]{2,}", " ", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"\(\s+", "(", text)
        text = re.sub(r"\s+\)", ")", text)
        text = re.sub(r"\s*\^\s*", "^", text)
        text = re.sub(r"\s*_\s*", "_", text)
        return text.strip()

    def _is_noise_line(self, line: str) -> bool:
        cleaned = self._clean_line_text(line)
        if not cleaned:
            return True
        lower = cleaned.lower()
        if lower in {"mathematics", "contents", "table of contents"}:
            return True
        if re.fullmatch(r"\d+", cleaned):
            return True
        if re.fullmatch(r"[A-Z][A-Z\s&\-]+\s+\d+", cleaned):
            return True
        if len(cleaned) <= 2:
            return True
        return False

    def _looks_like_heading_continuation(self, line: str) -> bool:
        cleaned = self._clean_line_text(line)
        if self._is_noise_line(cleaned):
            return False
        if len(cleaned) > 80:
            return False
        if re.search(r"[.!?;]$", cleaned):
            return False
        if re.match(r"^(In|For|To|Observe|Thus|Similarly|Let|Can|We|The)\b", cleaned):
            return False
        if len(cleaned.split()) > 8:
            return False
        return bool(re.match(r"^[A-Z][A-Za-z0-9()\-+,/: ]*$", cleaned))

    def _heading_title_from_match(self, code: str, title: str) -> Dict[str, Any]:
        title = self._clean_line_text(title).strip(" :")
        return {
            "section_code": code,
            "section_title": title,
            "chapter": code.split(".")[0] if code else None,
            "topic": f"{code} {title}".strip() if code and title else title or code,
        }

    def _extract_sections_from_pages(self, pages_text: List[str]) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        seen = set()

        for page_number, page_text in enumerate(pages_text, start=1):
            lines = [self._clean_line_text(line) for line in page_text.splitlines() if line.strip()]
            idx = 0
            while idx < len(lines):
                line = lines[idx]
                if self._is_noise_line(line):
                    idx += 1
                    continue

                code = None
                title = None
                kind = "section"

                section_match = self._SECTION_HEADING_RE.match(line)
                if section_match:
                    code = section_match.group("code")
                    title = section_match.group("title")
                else:
                    # Also detect chapter-level headings like "1 Our Earth" (no dots)
                    chapter_heading_match = self._CHAPTER_HEADING_RE.match(line)
                    if chapter_heading_match:
                        candidate_title = chapter_heading_match.group("title").strip()
                        # Only accept if title has >= 2 words or is long enough (avoids data matches)
                        _title_words = candidate_title.split()
                        if len(_title_words) >= 2 or len(candidate_title) >= 8:
                            code = chapter_heading_match.group("code")
                            title = candidate_title
                    if not code:
                        exercise_match = self._EXERCISE_HEADING_RE.match(line)
                        if exercise_match:
                            code = exercise_match.group("code")
                            title = exercise_match.group("title") or f"Exercise {code}"
                            kind = "exercise"
                        else:
                            code_only_match = self._SECTION_CODE_ONLY_RE.match(line)
                            if code_only_match:
                                code = code_only_match.group("code")
                                title = ""

                if not code:
                    idx += 1
                    continue

                end_idx = idx
                if not title and idx + 1 < len(lines) and self._looks_like_heading_continuation(lines[idx + 1]):
                    end_idx = idx + 1
                    title = lines[idx + 1]
                elif title and idx + 1 < len(lines) and self._looks_like_heading_continuation(lines[idx + 1]):
                    end_idx = idx + 1
                    title = f"{title} {lines[idx + 1]}"

                section_title = self._clean_line_text(title).strip(" :") or code
                label = f"{code} {section_title}".strip() if kind == "section" else section_title
                section = {
                    "code": code,
                    "title": section_title,
                    "label": label,
                    "kind": kind,
                    "level": max(1, code.count(".")),
                    "page_number": page_number,
                    "chapter": code.split(".")[0],
                }
                dedupe_key = (section["kind"], section["code"], section["title"].lower(), page_number)
                if dedupe_key not in seen:
                    seen.add(dedupe_key)
                    sections.append(section)

                idx = end_idx + 1

        return sections

    def _build_page_section_map(self, sections: List[Dict[str, Any]], total_pages: int) -> Dict[int, Dict[str, Any]]:
        page_map: Dict[int, Dict[str, Any]] = {}
        current_primary: Optional[Dict[str, Any]] = None
        sections_by_page: Dict[int, List[Dict[str, Any]]] = {}

        for section in sections:
            sections_by_page.setdefault(section["page_number"], []).append(section)

        for page_number in range(1, total_pages + 1):
            explicit_sections = sections_by_page.get(page_number, [])
            primary_section = next((sec for sec in explicit_sections if sec["kind"] == "section"), None)

            if primary_section:
                current_primary = primary_section
            elif explicit_sections and current_primary is None:
                current_primary = explicit_sections[0]

            if current_primary:
                page_map[page_number] = {
                    "chapter": current_primary.get("chapter"),
                    "section_code": current_primary.get("code"),
                    "section_title": current_primary.get("title"),
                    "topic": current_primary.get("label"),
                    "headers": [current_primary.get("label")] if current_primary.get("label") else [],
                }

        return page_map

    def _is_superscript_span(self, span: Dict[str, Any], previous_span: Optional[Dict[str, Any]], base_size: float) -> bool:
        if previous_span is None:
            return False

        text = self._clean_line_text(span.get("text", ""))
        if not text or len(text) > 4:
            return False
        if not re.fullmatch(r"[0-9A-Za-z+\-]+", text):
            return False

        size = float(span.get("size", 0) or 0)
        previous_size = float(previous_span.get("size", 0) or 0)
        if size >= min(base_size, previous_size) * 0.82:
            return False

        span_bbox = span.get("bbox", [0, 0, 0, 0])
        previous_bbox = previous_span.get("bbox", [0, 0, 0, 0])
        return (previous_bbox[3] - span_bbox[3]) >= max(1.2, previous_size * 0.12)

    def _is_subscript_span(self, span: Dict[str, Any], previous_span: Optional[Dict[str, Any]], base_size: float) -> bool:
        if previous_span is None:
            return False

        text = self._clean_line_text(span.get("text", ""))
        if not text or len(text) > 4:
            return False
        if not re.fullmatch(r"[0-9A-Za-z+\-]+", text):
            return False

        size = float(span.get("size", 0) or 0)
        previous_size = float(previous_span.get("size", 0) or 0)
        if size >= min(base_size, previous_size) * 0.82:
            return False

        span_bbox = span.get("bbox", [0, 0, 0, 0])
        previous_bbox = previous_span.get("bbox", [0, 0, 0, 0])
        return (span_bbox[1] - previous_bbox[1]) >= max(1.2, previous_size * 0.12)

    def _needs_space_between(self, current_text: str, next_text: str, gap: float, base_size: float) -> bool:
        if not current_text or not next_text:
            return False
        if current_text.endswith((" ", "(", "[", "{", "/", "^", "_")):
            return False
        if next_text.startswith((" ", ",", ".", ";", ":", ")", "]", "}", "%", "^", "_", "/", "+", "-", "=")):
            return False
        return gap > max(1.5, base_size * 0.12)

    def _reconstruct_line_from_spans(self, line: Dict[str, Any]) -> str:
        spans = line.get("spans", []) or []
        if not spans:
            return ""

        non_empty_sizes = [
            float(span.get("size", 0) or 0)
            for span in spans
            if self._clean_line_text(span.get("text", ""))
        ]
        base_size = max(non_empty_sizes) if non_empty_sizes else 0.0

        parts: List[str] = []
        previous_span: Optional[Dict[str, Any]] = None

        for span in spans:
            text = self._normalize_text(span.get("text", ""))
            if not text:
                continue

            cleaned_text = self._clean_line_text(text)
            if not cleaned_text and text.isspace():
                continue

            gap = 0.0
            if previous_span is not None:
                prev_bbox = previous_span.get("bbox", [0, 0, 0, 0])
                span_bbox = span.get("bbox", [0, 0, 0, 0])
                gap = max(0.0, float(span_bbox[0]) - float(prev_bbox[2]))

            if self._is_superscript_span(span, previous_span, base_size):
                if parts:
                    parts[-1] = parts[-1].rstrip()
                parts.append("^")
                parts.append(cleaned_text)
            elif self._is_subscript_span(span, previous_span, base_size):
                if parts:
                    parts[-1] = parts[-1].rstrip()
                parts.append("_")
                parts.append(cleaned_text)
            else:
                current_joined = "".join(parts)
                if self._needs_space_between(current_joined, text, gap, base_size):
                    parts.append(" ")
                parts.append(text)

            previous_span = span

        return self._clean_line_text("".join(parts))

    def _extract_page_text_from_pymupdf_page(self, page: Any) -> str:
        raw = page.get_text("dict")
        block_texts: List[str] = []

        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue

            lines: List[str] = []
            for line in block.get("lines", []):
                line_text = self._reconstruct_line_from_spans(line)
                if line_text:
                    lines.append(line_text)

            if lines:
                block_texts.append("\n".join(lines))

        return "\n\n".join(block_texts).strip()

    def _extract_metadata(
        self,
        text: str,
        page_number: int = 0,
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "page_number": page_number,
            "chapter": None,
            "topic": None,
            "headers": [],
            "section_code": None,
            "section_title": None,
            "content_type": "text",
        }

        if base_metadata:
            metadata.update({k: v for k, v in base_metadata.items() if v})
            metadata["headers"] = list(base_metadata.get("headers", []) or [])

        lines = [self._clean_line_text(line) for line in text.splitlines()[:30] if line.strip()]

        for line in lines:
            if self._is_noise_line(line):
                continue

            chapter_match = self._CHAPTER_RE.search(line)
            if chapter_match and not metadata.get("chapter"):
                metadata["chapter"] = chapter_match.group(1) or chapter_match.group(2)

            section_match = self._SECTION_HEADING_RE.match(line)
            if section_match:
                info = self._heading_title_from_match(section_match.group("code"), section_match.group("title"))
                current_title = str(metadata.get("section_title", "") or "")
                if not current_title or len(info["section_title"]) >= len(current_title):
                    metadata.update(info)
                if metadata.get("topic") and metadata["topic"] not in metadata["headers"]:
                    metadata["headers"].append(metadata["topic"])
                continue

            exercise_match = self._EXERCISE_HEADING_RE.match(line)
            if exercise_match and not metadata.get("section_code"):
                code = exercise_match.group("code")
                exercise_title = exercise_match.group("title") or f"Exercise {code}"
                info = self._heading_title_from_match(code, exercise_title)
                metadata.update(info)
                metadata["content_type"] = "exercise"
                if exercise_title not in metadata["headers"]:
                    metadata["headers"].append(exercise_title)
                continue

            example_match = self._EXAMPLE_HEADING_RE.match(line)
            if example_match:
                example_title = self._clean_line_text(example_match.group("label"))
                metadata["content_type"] = "example"
                if example_title and example_title not in metadata["headers"]:
                    metadata["headers"].append(example_title)
                if not metadata.get("topic"):
                    metadata["topic"] = example_title
                continue

            if len(line) <= 100 and len(line.split()) <= 8 and not re.search(r"[.!?]$", line):
                if line not in metadata["headers"]:
                    metadata["headers"].append(line)
                if not metadata.get("topic"):
                    metadata["topic"] = line

        if metadata.get("section_title") and not metadata.get("topic"):
            code = metadata.get("section_code")
            title = metadata.get("section_title")
            metadata["topic"] = f"{code} {title}".strip() if code else title

        metadata["headers"] = metadata["headers"][:4]
        return metadata

    def _extract_pages_from_reader(self, pdf_reader: PdfReader) -> List[str]:
        pages_text: List[str] = []
        for page_num, page in enumerate(pdf_reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
                pages_text.append(self._normalize_text(page_text).strip())
            except Exception as exc:
                logger.warning("Error extracting page %s: %s", page_num, exc)
                pages_text.append("")
        return pages_text

    def _extract_pages_with_pymupdf_bytes(self, pdf_bytes: bytes) -> List[str]:
        if fitz is None:
            raise RuntimeError("PyMuPDF is not available")

        pages_text: List[str] = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page_num, page in enumerate(doc, start=1):
                try:
                    pages_text.append(self._extract_page_text_from_pymupdf_page(page))
                except Exception as exc:
                    logger.warning("PyMuPDF error extracting page %s: %s", page_num, exc)
                    pages_text.append("")
        finally:
            doc.close()

        return pages_text

    def _extract_pages_with_pymupdf_file(self, file_path: str) -> List[str]:
        if fitz is None:
            raise RuntimeError("PyMuPDF is not available")

        pages_text: List[str] = []
        doc = fitz.open(file_path)
        try:
            for page_num, page in enumerate(doc, start=1):
                try:
                    pages_text.append(self._extract_page_text_from_pymupdf_page(page))
                except Exception as exc:
                    logger.warning("PyMuPDF error extracting page %s: %s", page_num, exc)
                    pages_text.append("")
        finally:
            doc.close()

        return pages_text

    def _join_pages_text(self, pages_text: List[str]) -> str:
        return "\n\n".join([page for page in pages_text if page]).strip()

    async def extract_text_from_url(self, pdf_url: str) -> str:
        try:
            logger.info("Downloading PDF from: %s", pdf_url)

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                ),
                "Accept": "application/pdf,*/*",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }

            response = requests.get(pdf_url, timeout=30, allow_redirects=True, headers=headers)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if "application/pdf" not in content_type:
                logger.error("Invalid content type: %s. URL does not point to a PDF file.", content_type)
                raise Exception(
                    f"URL does not return a PDF. Content-Type: {content_type}. "
                    "Please provide a direct link to a PDF file (not a webpage)."
                )

            if fitz is not None:
                pages_text = self._extract_pages_with_pymupdf_bytes(response.content)
            else:
                pdf_file = io.BytesIO(response.content)
                pdf_reader = PdfReader(pdf_file)
                pages_text = self._extract_pages_from_reader(pdf_reader)

            text = self._join_pages_text(pages_text)
            logger.info("Successfully extracted %s characters from PDF", len(text))
            return text.strip()

        except requests.ConnectionError as exc:
            logger.error("Connection error downloading PDF: %s", exc)
            raise Exception(
                "Connection failed. The server may have rejected or closed the connection. "
                "Try a different PDF URL or check your internet connection."
            )
        except requests.RequestException as exc:
            logger.error("Error downloading PDF: %s", exc)
            raise Exception(f"Failed to download PDF from URL. Check the link is accessible: {exc}")
        except Exception as exc:
            logger.error("Error processing PDF: %s", exc)
            raise Exception(f"Failed to process PDF: {exc}")

    async def extract_text_from_file(self, file_path: str) -> str:
        try:
            logger.info("Reading PDF from: %s", file_path)

            if fitz is not None:
                pages_text = self._extract_pages_with_pymupdf_file(file_path)
            else:
                pdf_reader = PdfReader(file_path)
                pages_text = self._extract_pages_from_reader(pdf_reader)

            text = self._join_pages_text(pages_text)
            logger.info("Successfully extracted %s characters from PDF", len(text))
            return text.strip()

        except Exception as exc:
            logger.error("Error processing PDF file: %s", exc)
            raise Exception(f"Failed to process PDF file: {exc}")

    def chunk_text(
        self,
        text: str,
        page_number: int = 0,
        base_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []

        chunks: List[Dict[str, Any]] = []
        chunk_id = 0
        paragraphs = re.split(r"\n\n+", text.strip())
        current_chunk = ""
        current_tokens = 0

        def is_heading_boundary(paragraph_text: str) -> bool:
            first_line = self._clean_line_text(paragraph_text.splitlines()[0] if paragraph_text else "")
            if not first_line:
                return False
            return bool(
                self._SECTION_HEADING_RE.match(first_line)
                or self._EXERCISE_HEADING_RE.match(first_line)
            )

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            para_tokens = self._count_tokens(paragraph)
            if current_chunk and is_heading_boundary(paragraph):
                metadata = self._extract_metadata(current_chunk, page_number, base_metadata=base_metadata)
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "text": current_chunk.strip(),
                        "token_count": current_tokens,
                        "metadata": metadata,
                    }
                )
                chunk_id += 1
                current_chunk = ""
                current_tokens = 0

            if current_tokens + para_tokens > self.chunk_size_tokens and current_chunk:
                metadata = self._extract_metadata(current_chunk, page_number, base_metadata=base_metadata)
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "text": current_chunk.strip(),
                        "token_count": current_tokens,
                        "metadata": metadata,
                    }
                )
                chunk_id += 1
                current_chunk = ""
                current_tokens = 0

            if current_chunk:
                current_chunk += "\n\n"
            current_chunk += paragraph
            current_tokens += para_tokens

        if current_chunk.strip():
            metadata = self._extract_metadata(current_chunk, page_number, base_metadata=base_metadata)
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": current_chunk.strip(),
                    "token_count": current_tokens,
                    "metadata": metadata,
                }
            )

        logger.info("Created %s semantic chunks (token-based) from text on page %s", len(chunks), page_number or "?")
        return chunks

    def chunk_pages_text(
        self,
        pages_text: List[str],
        page_section_map: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        chunk_id = 0

        for page_number, page_text in enumerate(pages_text, start=1):
            if not page_text or not page_text.strip():
                continue

            base_metadata = dict(page_section_map.get(page_number, {}) if page_section_map else {})
            page_chunks = self.chunk_text(page_text, page_number, base_metadata=base_metadata)

            for chunk in page_chunks:
                chunk["chunk_id"] = chunk_id
                chunk["metadata"]["page_number"] = page_number
                chunks.append(chunk)
                chunk_id += 1

        logger.info("Created %s semantic chunks from %s pages (token-aware, topic-aware)", len(chunks), len(pages_text))
        return chunks

    def build_study_context(
        self,
        chunks: List[Dict[str, Any]],
        pages_text: List[str],
        sections: Optional[List[Dict[str, Any]]] = None,
        max_chars: int = 8000,
        max_chunks: int = 10,
    ) -> str:
        if not chunks:
            return self._join_pages_text(pages_text)[:max_chars]

        parts: List[str] = []
        total_chars = 0

        if sections:
            outline_lines = ["Document outline:"]
            for section in sections[:12]:
                label = section.get("label") or section.get("title") or section.get("code")
                page_number = int(section.get("page_number", 0) or 0)
                if not label:
                    continue
                outline_lines.append(f"- {label} (page {page_number})" if page_number else f"- {label}")
            outline_text = "\n".join(outline_lines)
            if outline_text and len(outline_text) < max_chars // 2:
                parts.append(outline_text)
                total_chars += len(outline_text) + 2

        total_chunks = len(chunks)
        candidate_indexes: List[int] = []
        candidate_indexes.extend(range(min(2, total_chunks)))
        for fraction in (0.2, 0.4, 0.6, 0.8):
            if total_chunks <= 2:
                break
            candidate_indexes.append(int((total_chunks - 1) * fraction))
        candidate_indexes.extend(range(max(total_chunks - 2, 0), total_chunks))

        for idx, chunk in enumerate(chunks):
            metadata = chunk.get("metadata", {})
            if (
                metadata.get("section_code")
                or metadata.get("section_title")
                or metadata.get("chapter")
                or metadata.get("topic")
                or metadata.get("headers")
            ):
                candidate_indexes.append(idx)

        seen_indexes = set()
        unique_indexes: List[int] = []
        for idx in candidate_indexes:
            if 0 <= idx < total_chunks and idx not in seen_indexes:
                seen_indexes.add(idx)
                unique_indexes.append(idx)

        used_pages = set()
        used_topics = set()

        for idx in unique_indexes:
            chunk = chunks[idx]
            metadata = chunk.get("metadata", {})
            page_number = int(metadata.get("page_number", 0) or 0)
            chapter = str(metadata.get("chapter", "") or "").strip()
            section_code = str(metadata.get("section_code", "") or "").strip()
            section_title = str(metadata.get("section_title", "") or "").strip()
            topic = str(metadata.get("topic", "") or "").strip()
            topic_key = topic.lower()

            if page_number in used_pages and topic_key and topic_key in used_topics:
                continue

            text = re.sub(r"\s+", " ", chunk.get("text", "")).strip()
            if not text:
                continue

            excerpt = text[:700].strip()
            label_parts = []
            if page_number:
                label_parts.append(f"Page {page_number}")
            if chapter:
                label_parts.append(f"Chapter {chapter}")
            if section_code:
                label_parts.append(section_code)
            if section_title:
                label_parts.append(section_title)
            elif topic:
                label_parts.append(topic)

            label = " | ".join(label_parts) if label_parts else f"Chunk {idx + 1}"
            section_text = f"[{label}] {excerpt}"
            if total_chars + len(section_text) > max_chars:
                break

            parts.append(section_text)
            total_chars += len(section_text) + 2
            if page_number:
                used_pages.add(page_number)
            if topic_key:
                used_topics.add(topic_key)

            if len(parts) >= max_chunks + (1 if sections else 0):
                break

        if not parts:
            return self._join_pages_text(pages_text)[:max_chars]

        return "\n\n".join(parts)

    async def process_pdf(self, pdf_source: str, is_url: bool = True) -> Dict[str, Any]:
        try:
            if is_url:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    ),
                    "Accept": "application/pdf,*/*",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                }
                response = requests.get(pdf_source, timeout=30, allow_redirects=True, headers=headers)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()
                if "application/pdf" not in content_type:
                    logger.error("Invalid content type: %s. URL does not point to a PDF file.", content_type)
                    raise Exception(
                        f"URL does not return a PDF. Content-Type: {content_type}. "
                        "Please provide a direct link to a PDF file (not a webpage)."
                    )

                if fitz is not None:
                    pages_text = self._extract_pages_with_pymupdf_bytes(response.content)
                else:
                    pdf_file = io.BytesIO(response.content)
                    pdf_reader = PdfReader(pdf_file)
                    pages_text = self._extract_pages_from_reader(pdf_reader)
            else:
                if fitz is not None:
                    pages_text = self._extract_pages_with_pymupdf_file(pdf_source)
                else:
                    pdf_reader = PdfReader(pdf_source)
                    pages_text = self._extract_pages_from_reader(pdf_reader)

            full_text = self._join_pages_text(pages_text)
            sections = self._extract_sections_from_pages(pages_text)
            page_section_map = self._build_page_section_map(sections, len(pages_text))
            chunks = self.chunk_pages_text(pages_text, page_section_map=page_section_map)
            study_context = self.build_study_context(chunks, pages_text, sections=sections)

            return {
                "full_text": full_text,
                "pages_text": pages_text,
                "sections": sections,
                "total_pages": len(pages_text),
                "chunks": chunks,
                "study_context": study_context,
                "total_chunks": len(chunks),
                "total_chars": len(full_text),
                "source": pdf_source,
            }

        except Exception as exc:
            logger.error("Error processing PDF: %s", exc)
            raise


pdf_handler = PDFHandler(
    chunk_size_tokens=750,
    chunk_overlap_tokens=100,
)
