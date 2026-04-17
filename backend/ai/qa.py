"""
AI Q&A Module with RAG (Retrieval Augmented Generation)
Answers questions using context from PDF via vector database
"""
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from config import settings
from vector_db import vector_db
from ai.ollama_client import ollama_client
from timing_utils import log_phase

logger = logging.getLogger(__name__)

class QASystem:
    """Question-answering system using RAG"""

    _STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "brief", "by", "chapter",
        "define", "definition", "describe", "detail", "details", "do", "does",
        "explain", "for", "from", "give", "how", "in", "is", "it", "list",
        "many", "me", "of", "on", "please", "show", "summarize", "summary",
        "tell", "that", "the", "their", "this", "those", "to", "what", "when",
        "where", "which", "who", "why", "with"
    }
    
    def __init__(self):
        """Initialize model settings"""
        self.model = settings.OLLAMA_CHAT_MODEL

    def _is_chapter_list_request(self, question: str) -> bool:
        """Return True only for explicit chapter list/count/index requests."""
        q = (question or "").strip().lower()
        if not q:
            return False

        # If user asks to explain/summarize a chapter, do not treat it as TOC intent.
        if re.search(r'\b(explain|summary|summarize|describe|detail|brief|about|what is|tell me)\b', q):
            if re.search(r'\bchapter\s*\d+\b', q):
                return False

        # Explicit signals for list/count intent.
        explicit_patterns = [
            r'\bhow many chapters\b',
            r'\bnumber of chapters\b',
            r'\bno\.?\s*of chapters\b',
            r'\blist (all )?chapters\b',
            r'\bname (all )?chapters\b',
            r'\bchapter names\b',
            r'\bwhat are the chapters\b',
            r'\btable of contents\b',
            r'\bcontents page\b',
            r'\bindex\b',
        ]
        if any(re.search(p, q) for p in explicit_patterns):
            return True

        return False

    def _build_query_variants(self, question: str, chapter_list_intent: bool) -> List[str]:
        """Build retrieval variants to improve recall for natural questions."""
        q = (question or "").strip()
        if not q:
            return []

        variants = [q]

        if chapter_list_intent:
            variants.append(f"{q} table of contents chapter list headings titles units")
            return variants

        chapter_match = re.search(r'\bchapter\s*(\d+)\b', q, re.I)
        if chapter_match:
            chapter_no = chapter_match.group(1)
            variants.extend([
                f"chapter {chapter_no} explanation summary key points",
                f"what is discussed in chapter {chapter_no}",
            ])

        section_codes = self._extract_section_codes(q)
        for code in section_codes[:2]:
            variants.extend([
                f"section {code} {q}",
                f"{code} concept explanation",
                f"{code} example exercise solution",
            ])

        if re.search(r'\bexercise\s+\d+(?:\.\d+)+\b', q, re.I):
            variants.append(f"{q} worked example method answer")

        if re.search(r'\b(question|problem|solve|solution|exercise|example)\b', q, re.I):
            variants.append(f"{q} worked example steps method")

        variants.extend([
            f"{q} definition explanation",
            f"{q} important points",
        ])

        # Deduplicate while preserving order.
        seen = set()
        unique = []
        for v in variants:
            k = v.lower().strip()
            if k and k not in seen:
                seen.add(k)
                unique.append(v)
        return unique

    def _merge_results(self, result_sets: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Merge multiple vector search results and deduplicate evidence chunks."""
        merged_docs: List[str] = []
        merged_meta: List[Dict[str, Any]] = []
        seen = set()

        for rs in result_sets:
            docs = rs.get("documents", []) or []
            metas = rs.get("metadatas", []) or []
            for i, doc in enumerate(docs):
                md = metas[i] if i < len(metas) else {}
                key = (
                    int(md.get("page_number", 0) or 0),
                    int(md.get("chunk_index", i) or i),
                    (doc or "")[:180]
                )
                if key in seen:
                    continue
                seen.add(key)
                merged_docs.append(doc)
                merged_meta.append(md)

        return merged_docs, merged_meta

    def _extract_chapters_from_sections(self, sections: Optional[List[Dict[str, Any]]]) -> List[str]:
        """Extract unique chapter names from structured section data.
        
        Sections are hierarchical (e.g., 1.1, 1.2, 2.1).
        Chapter = first number (1, 2, 3, etc.)
        """
        if not sections:
            return []
        
        chapters_dict: Dict[str, str] = {}  # {chapter_num: chapter_title}
        
        for section in sections:
            code = str(section.get("code", "") or "").strip()
            title = str(section.get("title", "") or "").strip()
            section_title = str(section.get("section_title", "") or "").strip()
            
            if not code:
                continue
            
            # Extract chapter number (first number in code like "1" from "1.2.3")
            parts = code.split(".")
            chapter_num = parts[0] if parts else ""
            
            if not chapter_num.isdigit():
                continue
            
            # Use the most descriptive title available
            display_title = title or section_title
            if not display_title or display_title.lower() in {"", "content", "contents"}:
                continue
            
            # Store the first occurrence of each chapter (chapters typically have more descriptive titles at top level)
            if chapter_num not in chapters_dict:
                chapters_dict[chapter_num] = display_title
        
        # Return chapters sorted by number
        if chapters_dict:
            sorted_chapters = sorted(chapters_dict.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999)
            return [title for _, title in sorted_chapters]
        
        return []

    # Regex patterns for stripping trailing TOC info (page ranges, month names)
    _TOC_MONTH_RE = re.compile(
        r'\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*$',
        re.I,
    )
    _TOC_PAGE_RANGE_RE = re.compile(r'\s+\d+[\u2013\-]\d+\s*$')
    _TOC_PAGE_NUM_RE = re.compile(r'\s+\d+\s*$')

    def _strip_toc_trailing(self, text: str) -> str:
        """Strip trailing page ranges and month names that appear in TOC lines."""
        text = self._TOC_MONTH_RE.sub('', text).strip()
        text = self._TOC_PAGE_RANGE_RE.sub('', text).strip()
        text = self._TOC_PAGE_NUM_RE.sub('', text).strip()
        return text

    def _extract_chapter_lines(self, full_text: str, max_items: int = 20) -> List[str]:
        if not full_text:
            return []

        head = full_text[:150000]
        lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
        chapters: List[str] = []

        patterns = [
            # Standard: "Chapter 1: Title" or "Chapter 1 - Title"
            re.compile(r'^\s*chapter\s+(\d+)\s*[:—\-]?\s*(.+)$', re.I),
            # Number with separator: "1. Title" or "1) Title"
            re.compile(r'^\s*(\d+)\s*[.)]\s*([A-Z].+)$'),
            # Plain number + title (works on pre-stripped TOC lines): "1 Our Earth"
            re.compile(r'^\s*(\d{1,3})\s+([A-Z][A-Za-z0-9\s\&\-:,/\'"]+)$'),
        ]

        for ln in lines:
            if len(ln) < 3 or len(ln) > 200:
                continue

            lower = ln.lower()
            if any(bad in lower for bad in ["copyright", "isbn", "published", "acknowledgement", "preface", "contents", "table of"]):
                continue

            # Skip lines that are purely numeric/decimal/percentage (data values, not titles)
            if re.fullmatch(r'[\d.\-%\s]+', ln):
                continue

            # Pre-strip trailing TOC artifacts (page range + month) so patterns can match
            stripped_ln = self._strip_toc_trailing(ln)

            title = None
            for p in patterns:
                # Try stripped version first (handles TOC rows), then original
                for candidate_ln in ([stripped_ln, ln] if stripped_ln != ln else [ln]):
                    m = p.match(candidate_ln)
                    if m:
                        title = m.group(2).strip() if m.lastindex >= 2 else m.group(1).strip()
                        break
                if title:
                    break

            if title is None:
                continue

            # Reject titles that are pure numbers, decimals, or percentages
            if re.fullmatch(r'[\d.\-%]+', title):
                continue
            # Reject titles starting with a digit or % (data fragments, not chapter names)
            if re.match(r'^[\d%]', title):
                continue
            # Skip very short single-word titles (likely noise)
            words = title.split()
            if len(words) < 2 and len(title) < 10:
                continue
            # Skip years embedded in the title
            if re.search(r'\b\d{4}\b', title):
                continue

            chapters.append(title)
            if len(chapters) >= max_items:
                break

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for c in chapters:
            k = c.lower()
            if k not in seen:
                seen.add(k)
                unique.append(c)
        return unique

    def _extract_toc_mapping(self, full_text: str, max_items: int = 40) -> Dict[str, str]:
        if not full_text:
            return {}

        head = full_text[:150000]
        lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
        toc_map: Dict[str, str] = {}

        patterns = [
            re.compile(r'^\s*chapter\s+(\d+)\s*[:—\-]?\s*(.+)$', re.I),
            re.compile(r'^\s*(\d+)\s*[.)]\s*([A-Z].+)$'),
            re.compile(r'^\s*(\d{1,3})\s+([A-Z][A-Za-z0-9\s\&\-:,/\'"]+)$'),
        ]

        for ln in lines:
            if len(ln) < 3 or len(ln) > 200:
                continue

            lower = ln.lower()
            if any(bad in lower for bad in ["copyright", "isbn", "published", "acknowledgement", "preface", "contents", "table of"]):
                continue
            if re.fullmatch(r'[\d.\-%\s]+', ln):
                continue
            stripped_ln = self._strip_toc_trailing(ln)

            title = None
            code = None
            for p in patterns:
                for candidate_ln in ([stripped_ln, ln] if stripped_ln != ln else [ln]):
                    m = p.match(candidate_ln)
                    if m:
                        code = m.group(1).strip()
                        title = m.group(2).strip() if m.lastindex >= 2 else m.group(1).strip()
                        break
                if code and title:
                    break
            
            if not code or not title:
                continue

            if re.fullmatch(r'[\d.\-%]+', title):
                continue
            if re.match(r'^[\d%]', title):
                continue
            words = title.split()
            if len(words) < 2 and len(title) < 10:
                continue
            if re.search(r'\b\d{4}\b', title):
                continue

            if code not in toc_map:
                toc_map[code] = title
                if len(toc_map) >= max_items:
                    break

        return toc_map

    def _normalize_token(self, token: str) -> str:
        token = (token or "").lower().strip()
        if len(token) > 4 and token.endswith("s"):
            token = token[:-1]
        return token

    def _tokenize(self, text: str) -> set:
        return {
            self._normalize_token(token)
            for token in re.findall(r'[a-zA-Z]+|[0-9]+', (text or '').lower())
            if self._normalize_token(token)
        }

    def _extract_key_terms(self, text: str) -> List[str]:
        terms: List[str] = []
        seen = set()
        for raw in re.findall(r'[a-zA-Z0-9]+', (text or '').lower()):
            token = self._normalize_token(raw)
            if not token:
                continue
            if token in self._STOPWORDS:
                continue
            if len(token) <= 2 and not token.isdigit():
                continue
            if token not in seen:
                seen.add(token)
                terms.append(token)
        return terms

    def _is_document_overview_request(self, question: str) -> bool:
        q = (question or "").strip().lower()
        if not q:
            return False
        explicit_overview_patterns = [
            r'\bwhat topics\b',
            r'\bwhich topics\b',
            r'\blist (the )?(topics|sections|concepts|subjects)\b',
            r'\bmain idea\b',
            r'\boverview\b',
            r'\boverall summary\b',
            r'\bwhat does the pdf cover\b',
            r'\bwhat does this pdf cover\b',
            r'\bwhat is this about\b',
        ]
        if any(re.search(pattern, q) for pattern in explicit_overview_patterns):
            return True

        if re.search(r'\b(explain|describe|detail|detailed|teach|elaborate|discuss)\b', q):
            if not re.search(r'\b(all|main|overall)\b', q):
                return False

        overview_patterns = [
            r'\bthis pdf\b',
            r'\bthis document\b',
            r'\bin the pdf\b',
            r'\bin this pdf\b',
            r'\bin the document\b',
            r'\btopic[s]?\b',
            r'\bconcept[s]?\b',
            r'\bsubject[s]?\b',
        ]
        return any(re.search(pattern, q) for pattern in overview_patterns)

    def _extract_section_codes(self, text: str) -> List[str]:
        seen = set()
        codes: List[str] = []
        for code in re.findall(r'\b\d+(?:\.\d+)+\b', text or ""):
            if code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    def _format_section_label(self, section: Dict[str, Any]) -> str:
        code = str(section.get("code", "") or "").strip()
        title = str(section.get("title", "") or "").strip()
        kind = str(section.get("kind", "") or "").strip().lower()

        if kind == "exercise" and title:
            return title
        if code and title:
            return f"{code} {title}"
        return title or code

    def _recent_message(self, conversation_history: Optional[List[Dict[str, Any]]], role: str) -> str:
        if not conversation_history:
            return ""
        for item in reversed(conversation_history):
            if str(item.get("role", "")).lower() == role and str(item.get("content", "")).strip():
                return str(item.get("content", "")).strip()
        return ""

    def _is_follow_up_question(self, question: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> bool:
        if not question or not conversation_history:
            return False

        q = question.strip().lower()
        if re.search(r'^(and|also|then|so|what about)\b', q):
            return True
        if re.search(r'\b(explain more|more detail|in more detail|elaborate|continue|expand on|why|how so)\b', q):
            return True
        if re.search(r'\b(this|that|it|they|these|those|same|above|previous|this topic|that topic|this section)\b', q):
            return True

        key_terms = self._extract_key_terms(question)
        return len(key_terms) <= 2

    def _classify_intent(
        self,
        question: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        matched_sections: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        q = (question or "").strip().lower()
        matched_sections = matched_sections or []

        if self._is_document_overview_request(question):
            return "overview"
        if self._is_chapter_list_request(question):
            return "chapter_list"
        if re.search(r'\b(summary|summarize|key points|main points|important points)\b', q):
            return "summary"
        if re.search(r'\b(solve|solution|find|calculate|evaluate|simplify|expand|factori[sz]e|prove|show that)\b', q):
            return "problem_solving"
        if matched_sections and re.search(r'\b(explain|describe|detail|detailed|teach|discuss|what is|tell me about)\b', q):
            return "section_explanation"
        if self._is_follow_up_question(question, conversation_history):
            return "follow_up"
        if matched_sections:
            return "section_explanation"
        return "direct_qa"

    def _contextualize_question(
        self,
        question: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        matched_sections: Optional[List[Dict[str, Any]]] = None,
        intent: str = "direct_qa",
    ) -> str:
        question = (question or "").strip()
        matched_sections = matched_sections or []

        section_labels = [self._format_section_label(section) for section in matched_sections if self._format_section_label(section)]
        section_hint = ", ".join(section_labels[:2])
        if section_hint and section_hint.lower() not in question.lower():
            if intent in {"section_explanation", "problem_solving"}:
                return f"{question} about {section_hint}"

        if intent != "follow_up":
            return question

        previous_user = self._recent_message(conversation_history, "user")
        if section_hint:
            return f"{question} about {section_hint}"
        if previous_user and previous_user.lower() not in question.lower():
            return f"{question} regarding {previous_user}"
        return question

    def _section_code_family(self, code: str) -> List[str]:
        code = str(code or "").strip()
        if not code:
            return []

        parts = code.split(".")
        family = []
        for i in range(len(parts), 1, -1):
            family.append(".".join(parts[:i]))
        return family

    def _preferred_section_codes(self, matched_sections: Optional[List[Dict[str, Any]]]) -> List[str]:
        preferred: List[str] = []
        seen = set()
        for section in matched_sections or []:
            for code in self._section_code_family(str(section.get("code", "") or "")):
                if code and code not in seen:
                    seen.add(code)
                    preferred.append(code)
        return preferred

    def _find_referenced_sections(self, question: str, sections: Optional[List[Dict[str, Any]]], max_matches: int = 2) -> List[Dict[str, Any]]:
        if not question or not sections:
            return []

        q_lower = question.lower()
        q_tokens = self._tokenize(question)
        matches: List[Tuple[int, Dict[str, Any]]] = []

        target_chapters = re.findall(r'chapter\s*(\d+)', q_lower)
        target_sections = re.findall(r'section\s*(\d+(?:\.\d+)?)', q_lower)

        for section in sections:
            label = self._format_section_label(section)
            title = str(section.get("title", "") or "").strip()
            code = str(section.get("code", "") or "").strip()
            if not label:
                continue

            label_lower = label.lower()
            title_lower = title.lower()
            title_tokens = self._tokenize(title)
            overlap = len(q_tokens.intersection(title_tokens))
            score = 0

            for target in target_chapters + target_sections:
                if code == target:
                    score += 150
                elif title_lower.startswith(f"{target} "):
                    score += 150
                elif title_lower == target:
                    score += 150

            if code and code in q_lower:
                score += 8
            if title_lower and title_lower in q_lower:
                score += 6
            if overlap >= 2:
                score += overlap

            if score > 0:
                matches.append((score, section))

        matches.sort(key=lambda item: item[0], reverse=True)
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for _, section in matches:
            key = (section.get("code"), str(section.get("title", "")).lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(section)
            if len(deduped) >= max_matches:
                break

        return deduped

    def _normalize_answer_text(self, text: str) -> str:
        if not text:
            return ""

        normalized = str(text).replace("\r\n", "\n")
        replacements = {
            r"\(": "",
            r"\)": "",
            r"\[": "",
            r"\]": "",
            r"\times": " * ",
            r"\cdot": " * ",
            r"\div": " / ",
            r"\pm": " +/- ",
            r"\leq": " <= ",
            r"\geq": " >= ",
            r"\neq": " != ",
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        normalized = re.sub(r'\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}', r'(\1)/(\2)', normalized)
        normalized = re.sub(r'\\sqrt\s*\{([^{}]+)\}', r'sqrt(\1)', normalized)
        normalized = re.sub(r'\*\*(.*?)\*\*', r'\1', normalized)
        normalized = re.sub(r'`([^`]+)`', r'\1', normalized)
        normalized = re.sub(r'\\([A-Za-z]+)', r'\1', normalized)
        normalized = re.sub(r'[ \t]+', ' ', normalized)
        normalized = re.sub(r' *\n *', '\n', normalized)
        normalized = re.sub(r'\n{3,}', '\n\n', normalized)
        return normalized.strip()

    def _select_section_evidence(
        self,
        question: str,
        chunks: Optional[List[Dict[str, Any]]],
        matched_sections: Optional[List[Dict[str, Any]]],
        intent: str,
        max_items: int = 4,
    ) -> List[Dict[str, Any]]:
        if not chunks or not matched_sections:
            return []

        preferred_codes = self._preferred_section_codes(matched_sections)
        if not preferred_codes:
            return []

        q_tokens = self._tokenize(question)
        chunk_map = {int(chunk.get("chunk_id", idx)): chunk for idx, chunk in enumerate(chunks)}
        scored: List[Tuple[float, int]] = []

        for idx, chunk in enumerate(chunks):
            metadata = chunk.get("metadata", {}) or {}
            section_code = str(metadata.get("section_code", "") or "").strip()
            section_title = str(metadata.get("section_title", "") or "").strip()
            content_type = str(metadata.get("content_type", "") or "").strip().lower()
            score = 0.0

            if section_code:
                if section_code in preferred_codes:
                    score += 120
                elif any(
                    section_code.startswith(f"{preferred}.") or preferred.startswith(f"{section_code}.")
                    for preferred in preferred_codes
                ):
                    score += 70

            title_overlap = len(q_tokens.intersection(self._tokenize(section_title)))
            score += title_overlap * 10

            text_overlap = len(q_tokens.intersection(self._tokenize(chunk.get("text", "")[:500])))
            score += text_overlap * 2

            if intent == "problem_solving" and (content_type in {"example", "exercise"} or "solution" in chunk.get("text", "").lower()):
                score += 15
            if intent in {"section_explanation", "follow_up"} and content_type == "example":
                score += 6

            if score > 0:
                scored.append((score - (idx * 0.01), int(chunk.get("chunk_id", idx))))

        scored.sort(key=lambda item: item[0], reverse=True)

        selected_ids: List[int] = []
        seen_ids = set()
        for _, chunk_id in scored:
            if chunk_id not in seen_ids:
                selected_ids.append(chunk_id)
                seen_ids.add(chunk_id)
            if len(selected_ids) >= max_items:
                break

        expanded_ids = list(selected_ids)
        for chunk_id in selected_ids[:2]:
            current = chunk_map.get(chunk_id)
            if not current:
                continue
            current_meta = current.get("metadata", {}) or {}
            current_section = str(current_meta.get("section_code", "") or "").strip()
            current_page = int(current_meta.get("page_number", 0) or 0)

            for offset in (-1, 1):
                neighbor = chunk_map.get(chunk_id + offset)
                if not neighbor:
                    continue
                neighbor_meta = neighbor.get("metadata", {}) or {}
                neighbor_section = str(neighbor_meta.get("section_code", "") or "").strip()
                neighbor_page = int(neighbor_meta.get("page_number", 0) or 0)
                if neighbor.get("chunk_id") in seen_ids:
                    continue
                if neighbor_section and neighbor_section == current_section:
                    expanded_ids.append(int(neighbor.get("chunk_id")))
                    seen_ids.add(int(neighbor.get("chunk_id")))
                elif current_page and neighbor_page == current_page:
                    expanded_ids.append(int(neighbor.get("chunk_id")))
                    seen_ids.add(int(neighbor.get("chunk_id")))

        evidence: List[Dict[str, Any]] = []
        for chunk_id in expanded_ids[: max_items + 2]:
            chunk = chunk_map.get(chunk_id)
            if not chunk:
                continue
            evidence.append(
                {
                    "text": str(chunk.get("text", "") or ""),
                    "metadata": dict(chunk.get("metadata", {}) or {}),
                }
            )
        return evidence

    def _merge_evidence_candidates(
        self,
        vector_contexts: List[str],
        vector_metadatas: List[Dict[str, Any]],
        section_evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        contexts: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        seen = set()

        for ev in section_evidence or []:
            text = str(ev.get("text", "") or "").strip()
            metadata = dict(ev.get("metadata", {}) or {})
            key = (
                int(metadata.get("page_number", 0) or 0),
                int(metadata.get("chunk_id", metadata.get("chunk_index", 0)) or 0),
                text[:180],
            )
            if text and key not in seen:
                seen.add(key)
                contexts.append(text)
                metadatas.append(metadata)

        for idx, text in enumerate(vector_contexts):
            metadata = vector_metadatas[idx] if idx < len(vector_metadatas) else {}
            key = (
                int(metadata.get("page_number", 0) or 0),
                int(metadata.get("chunk_index", idx) or idx),
                (text or "")[:180],
            )
            if text and key not in seen:
                seen.add(key)
                contexts.append(text)
                metadatas.append(metadata)

        return contexts, metadatas

    def _build_context_text(self, evidence: List[Dict[str, Any]]) -> str:
        parts = []
        for i, ev in enumerate(evidence, start=1):
            metadata = ev.get("metadata", {}) or {}
            page_no = int(metadata.get("page_number", 0) or 0)
            section_code = str(metadata.get("section_code", "") or "").strip()
            section_title = str(metadata.get("section_title", "") or "").strip()
            header = f"[S{i}|p{page_no}"
            if section_code:
                header += f"|{section_code}"
            header += "]"
            label = f" {section_title}" if section_title else ""
            parts.append(f"{header}{label} {ev.get('text', '')}".strip())
        return "\n\n".join(parts)

    def _intent_instruction(self, intent: str) -> str:
        if intent == "problem_solving":
            return (
                "Solve the problem step by step using only the document evidence. "
                "Explain the logic clearly like a helpful tutor, keeping calculations readable, and clearly state the final result."
            )
        if intent in {"section_explanation", "follow_up", "overview"}:
            return (
                "Synthesize the provided context to offer a clear, comprehensive explanation. "
                "Group related ideas naturally. Do not just list headings; read the evidence and explain the concepts "
                "as if you were a knowledgeable teacher giving a personalized lesson."
            )
        if intent == "chapter_list":
            return (
                "Look through the provided context for headings, chapters, or topics, and outline them clearly in a structured list. "
                "Provide a brief, insightful summary of what each topic covers based on the context."
            )
        if intent == "summary":
            return (
                "Provide a beautiful, highly structured concept summary. Group the strongest points logically, "
                "using bold text for key terms and bullet points for readability."
            )
        return (
            "Analyze the provided context deeply and answer the user's question with clarity and insight. "
            "Synthesize the information gracefully rather than just returning raw excerpts."
        )

    def _generate_answer_plan(
        self,
        question: str,
        contextualized_question: str,
        evidence: List[Dict[str, Any]],
        intent: str,
        matched_sections: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if not evidence:
            return ""

        section_hint = ", ".join([self._format_section_label(section) for section in (matched_sections or [])[:2]])
        plan_lines: List[str] = []

        if section_hint:
            plan_lines.append(f"- Focus section: {section_hint}")
        if intent == "problem_solving":
            plan_lines.append("- Show only the method and formulas directly supported by the evidence.")
        elif intent in {"section_explanation", "follow_up"}:
            plan_lines.append("- Start with the direct explanation before supporting details.")
        elif intent == "summary":
            plan_lines.append("- Group the strongest points into a compact summary.")

        normalized_question = contextualized_question.strip() or question.strip()
        if normalized_question:
            plan_lines.append(f"- Stay anchored to: {normalized_question}")

        for idx, ev in enumerate(evidence[:3], start=1):
            snippet = re.sub(r"\s+", " ", str(ev.get("text", "") or "")).strip()
            if not snippet:
                continue
            first_sentence = re.split(r'(?<=[.!?])\s+', snippet, maxsplit=1)[0]
            if len(first_sentence) > 220:
                first_sentence = first_sentence[:217].rstrip() + "..."
            plan_lines.append(f"- [S{idx}] {first_sentence}")

        return "\n".join(plan_lines[:6])

    def _build_sections_overview_response(self, question: str, sections: Optional[List[Dict[str, Any]]]) -> Dict[str, Any] | None:
        if not self._is_document_overview_request(question):
            return None
        if not sections:
            return None

        items: List[Dict[str, Any]] = []
        seen = set()
        for section in sections:
            label = self._format_section_label(section)
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(section)

        if not items:
            return None

        answer_lines = ["The main sections I found in this PDF are:"]
        citations = []
        sources = []

        for idx, section in enumerate(items[:12], start=1):
            label = self._format_section_label(section)
            page_number = int(section.get("page_number", 0) or 0)
            answer_lines.append(f"{idx}. {label}" + (f" (page {page_number})" if page_number else ""))
            if page_number:
                citations.append({"tag": f"S{idx}", "page": page_number})
            sources.append(label)

        return {
            "answer": "\n".join(answer_lines),
            "sources": sources,
            "citations": citations,
            "confidence": "high",
            "num_sources": min(len(items), 12),
        }

    def _extract_topic_lines(self, full_text: str, max_items: int = 12) -> List[str]:
        """Extract likely headings/topics from the document for overview-type questions."""
        if not full_text:
            return []

        head = full_text[:150000]
        lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
        topics: List[str] = []

        patterns = [
            re.compile(r'^\s*(?:chapter|unit|lesson|topic|section)\s*[:\-]?\s*(.+)$', re.I),
            re.compile(r'^\s*\d+(?:\.\d+)+\s+(.+)$', re.I),
        ]
        imperative_starts = {
            "add", "find", "complete", "obtain", "multiply", "carry", "write",
            "solve", "state", "fill", "draw", "choose", "show", "factorise",
            "factorize", "simplify"
        }

        for ln in lines:
            if len(ln) < 3 or len(ln) > 90:
                continue

            lower = ln.lower()
            if any(bad in lower for bad in ["copyright", "isbn", "published", "acknowledgement", "preface"]):
                continue

            # Skip purely numeric/decimal/percentage lines -- data values, not headings
            if re.fullmatch(r'[\d.\-%\s]+', ln):
                continue

            candidate = None
            for pattern in patterns:
                match = pattern.match(ln)
                if match:
                    candidate = match.group(1).strip()
                    break

            if candidate is None:
                word_count = len(ln.split())
                # Treat short all-caps / title-like lines as headings.
                if word_count <= 8 and (
                    ln.isupper() or
                    ln == ln.title() or
                    re.match(r'^[A-Z][A-Za-z0-9/&,\- ]+$', ln)
                ):
                    # Guard: skip lines starting with a digit or % (data values, not headings)
                    if not re.match(r'^[\d%]', ln):
                        candidate = ln.strip()

            if not candidate:
                continue

            candidate = re.sub(r'\s+', ' ', candidate).strip(' .:-')
            if len(candidate.split()) < 1:
                continue
            if candidate.lower() in {"contents", "table of contents", "index"}:
                continue
            first_word = candidate.split()[0].lower()
            if first_word in imperative_starts:
                continue
            # Unified guard against matched data fragments!
            if re.fullmatch(r'[\d.\-%]+', candidate) or re.match(r'^[\d%]', candidate) or len(candidate) <= 2:
                continue

            topics.append(candidate)
            if len(topics) >= max_items:
                break

        seen = set()
        unique = []
        for topic in topics:
            key = topic.lower()
            if key not in seen:
                seen.add(key)
                unique.append(topic)
        return unique

    def _build_document_overview_response(self, question: str, full_text: str) -> Dict[str, Any] | None:
        """Handle broad 'what is in this PDF?' style questions directly from headings/topics."""
        if not self._is_document_overview_request(question):
            return None

        chapters = self._extract_chapter_lines(full_text, max_items=10)
        topics = self._extract_topic_lines(full_text, max_items=12)

        combined: List[str] = []
        seen = set()
        for item in chapters + topics:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                combined.append(item)

        if not combined:
            return None

        answer_lines = ["The main topics I can identify in this PDF are:"]
        answer_lines.extend([f"{i+1}. {topic}" for i, topic in enumerate(combined[:10])])

        return {
            "answer": "\n".join(answer_lines),
            "sources": combined[:10],
            "citations": [],
            "confidence": "high",
            "num_sources": min(len(combined), 10)
        }

    def _grounding_metrics(self, question: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        question_terms = self._extract_key_terms(question)
        if not question_terms:
            return {
                "question_terms": [],
                "matched_terms": [],
                "coverage": 0.0,
                "best_overlap": 0,
            }

        evidence_tokens = set()
        best_overlap = 0
        for ev in evidence:
            ctx_tokens = self._tokenize(ev.get("text", ""))
            evidence_tokens.update(ctx_tokens)
            best_overlap = max(best_overlap, len(set(question_terms).intersection(ctx_tokens)))

        matched_terms = [term for term in question_terms if term in evidence_tokens]
        coverage = len(matched_terms) / len(question_terms) if question_terms else 0.0

        return {
            "question_terms": question_terms,
            "matched_terms": matched_terms,
            "coverage": coverage,
            "best_overlap": best_overlap,
        }

    def _should_refuse_answer(
        self,
        question: str,
        retrieve_scores: List[float],
        evidence: List[Dict[str, Any]],
        conversation_history: List[Dict] = None,
        grounding: Dict[str, Any] = None
    ) -> bool:
        if not evidence:
            return True

        max_score = max(retrieve_scores) if retrieve_scores else 0.0
        avg_score = sum(retrieve_scores) / len(retrieve_scores) if retrieve_scores else 0.0
        grounding = grounding or self._grounding_metrics(question, evidence)
        matched_count = len(grounding["matched_terms"])
        question_term_count = len(grounding["question_terms"])
        coverage = grounding["coverage"]
        best_overlap = grounding["best_overlap"]
        chapter_specific = bool(re.search(r'\bchapter\s*\d+\b', (question or ''), re.I))
        overview_request = self._is_document_overview_request(question)
        follow_up = bool(conversation_history)
        requested_section_codes = set(self._extract_section_codes(question))
        evidence_section_match = False
        if requested_section_codes:
            for ev in evidence:
                md = ev.get("metadata", {}) or {}
                section_code = str(md.get("section_code", "") or "").strip()
                if section_code and section_code in requested_section_codes:
                    evidence_section_match = True
                    break

        if overview_request and max_score >= 0.40:
            return False

        if chapter_specific and max_score >= 0.45:
            return False

        if evidence_section_match and max_score >= 0.35:
            return False

        if follow_up and len(grounding["question_terms"]) <= 2 and max_score >= 0.48:
            return False

        if question_term_count:
            required_matches = 1 if question_term_count <= 2 else 2
            if matched_count < required_matches:
                return True

            if best_overlap < required_matches:
                return True

        if question_term_count >= 3 and coverage < 0.50:
            return True

        if max_score < 0.45:
            return True

        if avg_score < 0.52 and best_overlap < 2:
            return True

        return False

    def _rerank_contexts(
        self,
        question: str,
        contexts: List[str],
        metadatas: List[Dict[str, Any]],
        top_k: int = 6,
        prefer_early_pages: bool = False
    ) -> List[Dict[str, Any]]:
        q_tokens = self._tokenize(question)
        question_section_codes = set(self._extract_section_codes(question))
        if not q_tokens:
            return [
                {
                    "text": contexts[i],
                    "metadata": metadatas[i] if i < len(metadatas) else {}
                }
                for i in range(min(top_k, len(contexts)))
            ]

        scored = []
        for idx, ctx in enumerate(contexts):
            c_tokens = self._tokenize(ctx)
            overlap = len(q_tokens.intersection(c_tokens))
            md = metadatas[idx] if idx < len(metadatas) else {}
            page_no = int(md.get("page_number", 0) or 0)
            score = overlap * 10 - idx
            section_code = str(md.get("section_code", "") or "").strip()
            section_title_tokens = self._tokenize(str(md.get("section_title", "") or ""))

            # For explicit table-of-contents style queries, early pages are usually more important.
            if prefer_early_pages and page_no > 0:
                score += max(0, 20 - page_no)

            if section_code and section_code in question_section_codes:
                score += 25

            if section_title_tokens:
                title_overlap = len(q_tokens.intersection(section_title_tokens))
                score += title_overlap * 4

            scored.append((score, {"text": ctx, "metadata": md}))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def _audience_instruction(self, user_role: str) -> Tuple[str, int]:
        role = (user_role or "user").strip().lower()
        if role == "admin":
            return (
                "The user is an admin. Keep the explanation brief, conceptual, and well-structured. "
                "Use compact bullets for quick reading.",
                250
            )

        return (
            "The user is a student. Structure your response like Gemini: highly engaging, clear, and instantly understandable. "
            "Break complex ideas into simple concepts, define key terms naturally, and provide intuitive explanations. Always format your output beautifully with markdown.",
            450
        )
    
    async def answer_question(
        self,
        pdf_url: str,
        question: str,
        conversation_history: List[Dict] = None,
        full_text: str = "",
        user_role: str = "user",
        sections: Optional[List[Dict[str, Any]]] = None,
        chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict:
        """
        Answer a question using RAG with improved retrieval and metadata
        
        Args:
            pdf_url: URL/identifier of the PDF
            question: User's question
            conversation_history: Previous messages for context
            full_text: Full PDF text for fallback
            
        Returns:
            Answer with context, sources, and confidence scores
        """
        try:
            total_started = time.perf_counter()
            phase_started = time.perf_counter()
            audience_instruction, answer_max_tokens = self._audience_instruction(user_role)
            sections = sections or []
            chunks = chunks or []
            matched_sections = self._find_referenced_sections(question, sections)
            
            target_chapters = re.findall(r'chapter\s*(\d+)', question.lower())
            toc_map = self._extract_toc_mapping(full_text) if full_text and target_chapters else {}
            toc_titles = [toc_map[t] for t in target_chapters if t in toc_map]
            
            intent = self._classify_intent(question, conversation_history, matched_sections)
            chapter_list_intent = intent == "chapter_list"
            contextualized_question = self._contextualize_question(
                question,
                conversation_history=conversation_history,
                matched_sections=matched_sections,
                intent=intent,
            )
            preferred_section_codes = self._preferred_section_codes(matched_sections)
            if intent == "problem_solving":
                answer_max_tokens += 120
            elif intent in {"section_explanation", "follow_up"}:
                answer_max_tokens += 80
            log_phase(
                logger,
                "qa",
                "intent_and_context",
                phase_started,
                intent=intent,
                matched_sections=len(matched_sections),
            )


            phase_started = time.perf_counter()
            query_variants = self._build_query_variants(contextualized_question, chapter_list_intent)
            if contextualized_question.lower().strip() != question.lower().strip():
                query_variants.insert(0, question.strip())
            for section in matched_sections:
                section_label = self._format_section_label(section)
                section_title = str(section.get("title", "") or "").strip()
                extra_queries = [
                    f"{section_label} explanation",
                    f"{section_label} key points examples",
                    f"{contextualized_question} from {section_label}",
                ]
                if section_title and len(section_title) > 3:
                     extra_queries.append(f"{section_title} summary concepts")
                if intent == "problem_solving":
                    extra_queries.append(f"{section_label} solved example steps")
                for extra_query in extra_queries:
                    if extra_query not in query_variants:
                        query_variants.insert(1, extra_query)
            
            if not matched_sections and toc_titles:
                 for toc_title in toc_titles:
                     if len(toc_title) > 3:
                         query_variants.insert(1, f"{toc_title} summary concepts")
                         query_variants.insert(1, f"{toc_title} explanation")
                         
            deduped_variants = []
            seen_variants = set()
            for variant in query_variants:
                key = variant.lower().strip()
                if key and key not in seen_variants:
                    seen_variants.add(key)
                    deduped_variants.append(variant)
            query_variants = deduped_variants
            log_phase(logger, "qa", "build_query_variants", phase_started, query_variants=len(query_variants[:3]))
            phase_started = time.perf_counter()
            result_sets = await vector_db.query_documents_multi(
                pdf_url=pdf_url,
                queries=query_variants[:3],
                n_results=5,
                preferred_section_codes=preferred_section_codes,
            )
            log_phase(logger, "qa", "vector_query_batch", phase_started, query_count=min(len(query_variants), 3))
            retrieve_scores = [
                score
                for results in result_sets
                for score in (results.get("scores", []) or [])
            ]

            phase_started = time.perf_counter()
            vector_contexts, vector_metadatas = self._merge_results(result_sets)
            section_evidence = self._select_section_evidence(
                contextualized_question,
                chunks,
                matched_sections,
                intent=intent,
                max_items=4,
            )
            contexts, metadatas = self._merge_evidence_candidates(
                vector_contexts,
                vector_metadatas,
                section_evidence=section_evidence,
            )
            log_phase(
                logger,
                "qa",
                "assemble_evidence",
                phase_started,
                vector_contexts=len(vector_contexts),
                merged_contexts=len(contexts),
                section_evidence=len(section_evidence),
            )
            if not contexts:
                log_phase(logger, "qa", "total", total_started, path="no_contexts")
                return {
                    "answer": "I don't have enough context from this PDF to answer that question. Please make sure the PDF has been processed.",
                    "sources": [],
                    "confidence": "low",
                }

            avg_confidence = sum(retrieve_scores) / len(retrieve_scores) if retrieve_scores else 0.5
            confidence_level = "high" if avg_confidence > 0.7 else "medium" if avg_confidence > 0.5 else "low"

            phase_started = time.perf_counter()
            evidence = self._rerank_contexts(
                contextualized_question,
                contexts,
                metadatas,
                top_k=5,
                prefer_early_pages=chapter_list_intent,
            )

            max_chars_per_chunk = 700
            max_total_context = 3600
            picked: List[Dict[str, Any]] = []
            total = 0
            for ev in evidence:
                ctx = ev.get("text", "")
                clipped = (ctx or "")[:max_chars_per_chunk].strip()
                if not clipped:
                    continue
                if total + len(clipped) > max_total_context:
                    break
                picked.append({"text": clipped, "metadata": ev.get("metadata", {})})
                total += len(clipped)
            log_phase(logger, "qa", "rerank_and_clip_evidence", phase_started, picked=len(picked))

            if not picked:
                log_phase(logger, "qa", "total", total_started, path="no_picked_evidence")
                return {
                    "answer": "I could not find enough relevant evidence in this PDF for that question.",
                    "sources": [],
                    "citations": [],
                    "confidence": "low",
                    "num_sources": 0,
                }

            phase_started = time.perf_counter()
            grounding = self._grounding_metrics(question, picked)
            should_refuse = self._should_refuse_answer(question, retrieve_scores, picked, conversation_history, grounding=grounding)
            log_phase(
                logger,
                "qa",
                "grounding_check",
                phase_started,
                should_refuse=should_refuse,
                coverage=f"{grounding['coverage']:.2f}",
            )
            if should_refuse:
                logger.info(
                    "Refusing out-of-document question. max_score=%.2f avg_score=%.2f matched=%d coverage=%.2f best_overlap=%d question=%r",
                    max(retrieve_scores) if retrieve_scores else 0.0,
                    avg_confidence,
                    len(grounding["matched_terms"]),
                    grounding["coverage"],
                    grounding["best_overlap"],
                    question,
                )
                log_phase(logger, "qa", "total", total_started, path="refused_out_of_document")
                return {
                    "answer": "This question is outside the provided PDF, so I can't answer it from this document.",
                    "sources": [],
                    "citations": [],
                    "confidence": "low",
                    "num_sources": 0,
                }

            phase_started = time.perf_counter()
            context_text = self._build_context_text(picked)
            answer_plan = self._generate_answer_plan(
                question,
                contextualized_question,
                picked,
                intent=intent,
                matched_sections=matched_sections,
            )
            log_phase(logger, "qa", "build_answer_plan", phase_started, plan_chars=len(answer_plan or ""))
            section_hint = ", ".join([self._format_section_label(section) for section in matched_sections[:2]])
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an intelligent, highly capable teaching assistant. Synthesize the provided context to answer the user's question clearly and comprehensively. "
                        "You must ground every fact completely within the provided text. Do not invent missing facts, equations, or out-of-context answers. "
                        "Read the evidence and explain the concepts insightfully rather than just blindly copy-pasting raw text. "
                        "Cite source tags like [S1], [S2] naturally in your explanation where appropriate. "
                        "For math content, preserve expressions in plain text like x^2, (x + 3), 7xy, and explain the steps clearly when solving a problem from the document. "
                        "Do not use LaTeX delimiters like \\( \\), \\[ \\], or commands like \\times and \\cdot in the final answer. "
                        "If the evidence does not directly answer the question, "
                        "reply exactly: This question is outside the provided PDF, so I can't answer it from this document. "
                        f"{self._intent_instruction(intent)} "
                        f"{audience_instruction}"
                    ),
                },
            ]

            if conversation_history:
                messages.extend(conversation_history[-4:])

            if answer_plan:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Use this grounded answer plan as internal scaffolding only. "
                            "Do not mention the plan explicitly in the final answer.\n\n"
                            f"{answer_plan}"
                        ),
                    }
                )

            user_prompt = (
                f"Intent: {intent}\n"
                f"Relevant section: {section_hint or 'not explicitly matched'}\n"
                f"Original question: {question}\n"
                f"Contextualized question: {contextualized_question}\n\n"
                f"Evidence:\n{context_text}\n\n"
                "Answer the user's question now."
            )
            messages.append({"role": "user", "content": user_prompt})
            phase_started = time.perf_counter()
            answer = await ollama_client.chat(
                messages=messages,
                model=self.model,
                temperature=0.2,
                max_tokens=answer_max_tokens,
            )
            log_phase(logger, "qa", "llm_answer", phase_started, output_chars=len(answer or ""), max_tokens=answer_max_tokens)
            answer = self._normalize_answer_text(answer)

            final_confidence = (
                "high" if (confidence_level == "high" and len(picked) >= 3)
                else "medium" if (confidence_level in ["medium", "high"] and len(picked) >= 2)
                else "low"
            )

            logger.info(
                "Answered question using %s context chunks with %s confidence (avg relevance: %.2f)",
                len(picked),
                final_confidence,
                avg_confidence,
            )

            citations = []
            sources = []
            phase_started = time.perf_counter()
            for i, ev in enumerate(picked[:5], start=1):
                md = ev.get("metadata", {}) or {}
                page_no = int(md.get("page_number", 0) or 0)
                section_code = str(md.get("section_code", "") or "").strip()
                section_title = str(md.get("section_title", "") or "").strip()
                tag = f"S{i}"
                citations.append({"tag": tag, "page": page_no})
                section_label = ""
                if section_code and section_title:
                    section_label = f" [{section_code} {section_title}]"
                elif section_code:
                    section_label = f" [{section_code}]"
                sources.append(f"{tag} (page {page_no}){section_label}: {ev['text']}")
            log_phase(logger, "qa", "format_sources", phase_started, citations=len(citations))
            log_phase(logger, "qa", "total", total_started, confidence=final_confidence, picked=len(picked))

            return {
                "answer": answer,
                "sources": sources,
                "citations": citations,
                "confidence": final_confidence,
                "num_sources": len(picked),
            }

        except Exception as e:
            logger.error(f"Error answering question: {e}")
            raise Exception(f"Failed to answer question: {str(e)}")
    
    async def get_suggested_questions(self, pdf_text_sample: str) -> List[str]:
        """
        Generate suggested questions based on content
        
        Args:
            pdf_text_sample: Sample text from PDF
            
        Returns:
            List of suggested questions
        """
        try:
            # Limit sample length
            max_chars = 5000
            if len(pdf_text_sample) > max_chars:
                pdf_text_sample = pdf_text_sample[:max_chars]
            
            prompt = f"""Based on this educational content, suggest 5 interesting questions a student might ask:

Content:
{pdf_text_sample}

Generate 5 specific, thoughtful questions that would help students understand this material better.
Format: Return only the questions, one per line, without numbering."""
            
            content = await ollama_client.chat(
                messages=[
                    {"role": "system", "content": "You are an educational assistant helping students learn."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=300
            )
            questions = [q.strip() for q in content.split("\n") if q.strip()]
            
            logger.info(f"Generated {len(questions)} suggested questions")
            return questions[:5]
            
        except Exception as e:
            logger.error(f"Error generating suggested questions: {e}")
            return []

# Global QA system instance
qa_system = QASystem()
