"""
AI Quiz Generation Module
Generates multiple-choice questions with answers using Ollama
Uses RAG (Retrieval-Augmented Generation) for accuracy
"""
import ast
import logging
import json
import re
import time
from typing import List, Dict, Any, Optional
from config import settings
from ai.ollama_client import ollama_client
from vector_db import vector_db
from timing_utils import log_phase

logger = logging.getLogger(__name__)


def _clean_question_text(text: str) -> str:
    """Remove markdown/labels and return a clean question string."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r'^\s*#{1,6}\s*', '', cleaned)
    cleaned = re.sub(r'^\s*(?:question|mcq|q)\s*\d*\s*[:.)\-]*\s*', '', cleaned, flags=re.I)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip(' \t\n\r"\'')
    return cleaned


def _remove_template_tags(text: str) -> str:
    """Remove leftover XML/template tags like <topic>, <from text>, <question>, etc."""
    if not text:
        return text
    # Remove all XML-style tags
    text = re.sub(r'</?question>', '', text, flags=re.I)
    text = re.sub(r'</?topic>', '', text, flags=re.I)
    text = re.sub(r'</?from\s+text>', '', text, flags=re.I)
    text = re.sub(r'</?justified\s+from\s+text>', '', text, flags=re.I)
    text = re.sub(r'</?answer>', '', text, flags=re.I)
    text = re.sub(r'</?explanation>', '', text, flags=re.I)
    text = re.sub(r'</?option[s]?>', '', text, flags=re.I)
    # Also remove the full "(Correct answer: ...)" pattern
    text = re.sub(r'\(Correct answer:\s*[^)]*\)', '', text, flags=re.I)
    # Remove any other generic XML tags
    text = re.sub(r'<[^>]+>', '', text)
    text = text.strip()
    return text


def _extract_question_from_lines(lines: List[str]) -> str:
    """Pick the first non-option, non-answer line as the question."""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if re.match(r'^([A-D])\s*[).\]:\-]\s*(.+)', line):
            continue
        if re.match(r'^(answer|correct|explanation)\b', line, re.I):
            continue

        q = _clean_question_text(line)
        if q and not re.fullmatch(r'(?i)(question|mcq|q)\s*\d*[:.)\- ]*', q):
            return q

    return _clean_question_text(lines[0] if lines else "")


def _clean_option_text(text: str) -> str:
    """Normalize option/explanation text returned by the model."""
    cleaned = _remove_template_tags(str(text or "").replace("\\n", "\n").replace("\\r", " ").replace("\\t", " "))
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r'^(?:option\s*)?[A-D]\s*[).:\-]\s*', '', cleaned, flags=re.I)
    return cleaned.strip(' \t\n\r"\'')


def _canonicalize_text(text: str) -> str:
    return re.sub(r'\W+', ' ', str(text or '').lower()).strip()


def _extract_answer_letter(answer_text: str, options: Dict[str, str]) -> str:
    """Infer the correct answer letter from either a letter or option text."""
    cleaned = _clean_option_text(answer_text)
    if not cleaned:
        return ""

    for pattern in (
        r'^(?:option\s*)?([A-D])(?:\b|[).:\-])',
        r'\b([A-D])\b',
    ):
        match = re.search(pattern, cleaned, re.I)
        if match:
            letter = match.group(1).upper()
            if letter in options:
                return letter

    canonical_answer = _canonicalize_text(cleaned)
    for letter, option_text in options.items():
        if canonical_answer and _canonicalize_text(option_text) == canonical_answer:
            return letter

    return ""


def _extract_embedded_options(text: str) -> Dict[str, Any]:
    """
    Recover MCQ data when the model puts a whole question block into one string
    instead of a clean structured object.
    """
    normalized = _remove_template_tags(str(text or "").replace("\\n", "\n")).strip()
    if not normalized:
        return {"question": "", "options": {}, "correct_answer": "", "explanation": ""}

    lines = [line.strip().strip('"\',') for line in normalized.splitlines() if line.strip()]
    question_lines: List[str] = []
    options: Dict[str, str] = {}
    explanation_lines: List[str] = []
    current_option: Optional[str] = None
    answer_hint = ""
    saw_option = False

    option_line_pattern = re.compile(r'^(?:"|\')?(?:option[_ ]*)?([A-D])(?:"|\')?\s*[).:\-]\s*(.+)$', re.I)

    for raw_line in lines:
        line = raw_line.strip()

        answer_match = re.match(r'^(?:answer|correct(?: answer)?)\s*[:\-]\s*(.+)$', line, re.I)
        if answer_match:
            answer_hint = answer_match.group(1).strip()
            current_option = None
            continue

        explanation_match = re.match(r'^(?:explanation|reason)\s*[:\-]\s*(.+)$', line, re.I)
        if explanation_match:
            explanation_lines.append(explanation_match.group(1).strip())
            current_option = None
            continue

        option_match = option_line_pattern.match(line)
        if option_match:
            current_option = option_match.group(1).upper()
            options[current_option] = _clean_option_text(option_match.group(2))
            saw_option = True
            continue

        if saw_option and current_option:
            options[current_option] = _clean_option_text(f"{options[current_option]} {line}")
            continue

        question_lines.append(line)

    if len(options) < 2:
        inline_pattern = re.compile(
            r'(?is)\b([A-D])\s*[).:\-]\s*(.+?)(?=(?:\s+[A-D]\s*[).:\-])|(?:\s+(?:answer|correct|explanation)\s*[:\-])|$)'
        )
        inline_matches = list(inline_pattern.finditer(normalized))
        if len(inline_matches) >= 2:
            first_match = inline_matches[0]
            question_lines = [normalized[:first_match.start()].strip()]
            options = {
                match.group(1).upper(): _clean_option_text(match.group(2))
                for match in inline_matches[:4]
            }

    return {
        "question": _clean_question_text(" ".join(question_lines) if question_lines else normalized),
        "options": {key: value for key, value in options.items() if value},
        "correct_answer": answer_hint.strip(),
        "explanation": _clean_option_text(" ".join(explanation_lines)),
    }


def _escape_control_chars_in_json_strings(text: str) -> str:
    """Escape raw newlines/tabs inside quoted strings in almost-JSON output."""
    result: List[str] = []
    in_string = False
    quote_char = ""
    escaped = False

    for char in text:
        if in_string:
            if escaped:
                result.append(char)
                escaped = False
                continue
            if char == "\\":
                result.append(char)
                escaped = True
                continue
            if char == quote_char:
                result.append(char)
                in_string = False
                quote_char = ""
                continue
            if char == "\n":
                result.append("\\n")
                continue
            if char == "\r":
                result.append("\\r")
                continue
            if char == "\t":
                result.append("\\t")
                continue
            result.append(char)
            continue

        if char in {'"', "'"}:
            in_string = True
            quote_char = char
        result.append(char)

    return "".join(result)


def _repair_json_candidate(text: str) -> str:
    repaired = _escape_control_chars_in_json_strings(text.strip())
    repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)
    return repaired


def _extract_questions_payload(data: Any) -> Optional[List[Any]]:
    if isinstance(data, dict) and isinstance(data.get("questions"), list):
        return data["questions"]
    if isinstance(data, list):
        return data
    return None


def _load_questions_from_jsonish(text: str) -> Optional[List[Any]]:
    for candidate in (text, _repair_json_candidate(text)):
        for loader in (json.loads, ast.literal_eval):
            try:
                payload = _extract_questions_payload(loader(candidate))
                if payload is not None:
                    return payload
            except Exception:
                continue
    return None


def _parse_loose_structured_quiz(text: str) -> List[Dict[str, Any]]:
    """Recover questions from malformed JSON-like output using regex extraction."""
    questions: List[Dict[str, Any]] = []
    question_matches = list(re.finditer(r'(?is)["\']question["\']\s*:\s*["\']', text))
    if not question_matches:
        return questions

    option_field_pattern = re.compile(
        r'(?is)["\'](?:option[_ ]*)?([A-D])["\']\s*:\s*["\'](.*?)["\']\s*(?=,\s*["\'](?:option[_ ]*[A-D]|[A-D]|correct_answer|answer|explanation|difficulty|question_type|question)["\']\s*:|\s*[\}\]])'
    )

    for index, match in enumerate(question_matches):
        start = match.start()
        end = question_matches[index + 1].start() if index + 1 < len(question_matches) else len(text)
        block = text[start:end]

        question_match = re.search(
            r'(?is)["\']question["\']\s*:\s*["\'](.*?)["\']\s*(?=,\s*["\'](?:question_type|options|correct_answer|answer|explanation|difficulty|A|B|C|D|option_[A-Da-d]|choice_[A-Da-d])["\']\s*:|\s*[\}\]])',
            block,
        )
        if not question_match:
            continue

        options: Dict[str, str] = {}
        options_block_match = re.search(
            r'(?is)["\']options["\']\s*:\s*\{(.*?)\}\s*(?=,\s*["\'](?:correct_answer|answer|explanation|difficulty|question_type|question)["\']\s*:|\s*[\}\]])',
            block,
        )
        if options_block_match:
            for option_match in option_field_pattern.finditer(options_block_match.group(1)):
                options[option_match.group(1).upper()] = _clean_option_text(option_match.group(2))

        if len(options) < 2:
            for option_match in option_field_pattern.finditer(block):
                options.setdefault(option_match.group(1).upper(), _clean_option_text(option_match.group(2)))

        answer_match = re.search(
            r'(?is)["\'](?:correct_answer|answer|correct_option|correct)["\']\s*:\s*["\'](.*?)["\']\s*(?=,\s*["\'](?:explanation|difficulty|question_type|question)["\']\s*:|\s*[\}\]])',
            block,
        )
        explanation_match = re.search(
            r'(?is)["\']explanation["\']\s*:\s*["\'](.*?)["\']\s*(?=,\s*["\'](?:difficulty|question_type|question)["\']\s*:|\s*[\}\]])',
            block,
        )
        difficulty_match = re.search(r'(?is)["\']difficulty["\']\s*:\s*["\'](.*?)["\']', block)
        question_type_match = re.search(r'(?is)["\']question_type["\']\s*:\s*["\'](.*?)["\']', block)

        questions.append({
            "question": question_match.group(1),
            "question_type": question_type_match.group(1) if question_type_match else "mcq",
            "options": options,
            "correct_answer": answer_match.group(1) if answer_match else "",
            "explanation": explanation_match.group(1) if explanation_match else "",
            "difficulty": difficulty_match.group(1) if difficulty_match else "medium",
        })

    return questions


def _normalize_questions(raw_questions: List[Any]) -> List[Dict]:
    """Normalize model output into consistent quiz question objects."""
    normalized: List[Dict] = []

    for raw in raw_questions or []:
        if not isinstance(raw, dict):
            continue

        raw_question = str(raw.get("question", raw.get("question_text", raw.get("stem", ""))))
        q_text = _clean_question_text(_remove_template_tags(raw_question))
        if not q_text or re.fullmatch(r'(?i)(question|mcq|q)\s*\d*[:.)\- ]*', q_text):
            q_text = "Question not provided. Choose the best option."

        raw_options = raw.get("options", raw.get("choices", {}))
        options: Dict[str, str] = {}

        if isinstance(raw_options, dict):
            for k, v in raw_options.items():
                key = str(k).strip().upper()[:1]
                if key in "ABCD":
                    options[key] = _clean_option_text(v)
        elif isinstance(raw_options, list):
            for idx, value in enumerate(raw_options[:4]):
                key = chr(ord('A') + idx)
                options[key] = _clean_option_text(value)

        if len(options) < 2:
            for letter in "ABCD":
                root_keys = (
                    letter,
                    letter.lower(),
                    f"option_{letter}",
                    f"option_{letter.lower()}",
                    f"option{letter}",
                    f"option{letter.lower()}",
                    f"choice_{letter}",
                    f"choice_{letter.lower()}",
                    f"choice{letter}",
                    f"choice{letter.lower()}",
                )
                for key in root_keys:
                    value = raw.get(key)
                    if str(value or "").strip():
                        options[letter] = _clean_option_text(value)
                        break

        embedded_question = {}
        if len(options) < 2:
            embedded_question = _extract_embedded_options(raw_question)
            if embedded_question.get("question"):
                q_text = embedded_question["question"]
            for letter, value in (embedded_question.get("options") or {}).items():
                options.setdefault(letter, value)

        # Keep only non-empty options first.
        options = {k: v for k, v in options.items() if v}

        if len(options) < 2:
            logger.info(
                "Dropping quiz item during normalization due to missing options: question=%s keys=%s",
                q_text[:120],
                ",".join(sorted(str(key) for key in raw.keys())),
            )
            continue

        real_option_keys = [letter for letter in "ABCD" if options.get(letter)]
        options = {letter: options.get(letter, "Not applicable") for letter in "ABCD"}

        correct_raw = raw.get(
            "correct_answer",
            raw.get(
                "answer",
                raw.get("correct", raw.get("correct_option", embedded_question.get("correct_answer", ""))),
            ),
        )
        correct = _extract_answer_letter(str(correct_raw), options)
        if not correct:
            correct = real_option_keys[0] if real_option_keys else "A"

        difficulty = str(raw.get("difficulty", "medium")).lower()
        if difficulty not in {"easy", "medium", "hard", "basic"}:
            difficulty = "medium"

        # Preserve or infer question type
        question_type = str(raw.get("question_type", "mcq")).lower()
        if question_type not in {"mcq", "fill-in-blank", "true-false", "short-answer"}:
            question_type = "mcq"

        normalized.append({
            "question": q_text,
            "options": options,
            "correct_answer": correct,
            "explanation": _clean_option_text(raw.get("explanation", embedded_question.get("explanation", ""))),
            "difficulty": difficulty,
            "question_type": question_type
        })

    return normalized


def _convert_to_question_type(question: Dict, target_type: str) -> Dict:
    """
    Convert a question to a specific type if needed.
    Preserves MCQ format as-is, converts to other types as needed.
    """
    question_text = question.get("question", "")
    options = question.get("options", {})
    correct_answer = question.get("correct_answer", "A")
    explanation = question.get("explanation", "")
    difficulty = question.get("difficulty", "medium")
    
    if target_type == "mcq":
        # Already in MCQ format
        return question
    
    elif target_type == "fill-in-blank":
        # Convert MCQ to fill-in-the-blank
        # Use one of the options as the correct answer
        correct_text = options.get(correct_answer, "")
        return {
            "question": question_text,  # Don't show correct answer in question!
            "question_type": "fill-in-blank",
            "correct_answer": correct_text,
            "explanation": explanation,
            "difficulty": difficulty
        }
    
    elif target_type == "true-false":
        # Convert to true/false
        # Make it a statement and set T/F based on original correctness
        statement = question_text.replace("?", ".")
        return {
            "question": f"True or False: {statement}",
            "question_type": "true-false",
            "correct_answer": "True",  # Assume the statement is true
            "options": {"A": "True", "B": "False"},
            "explanation": explanation,
            "difficulty": difficulty
        }
    
    elif target_type == "short-answer":
        # Convert to short answer
        correct_text = options.get(correct_answer, "")
        return {
            "question": question_text,
            "question_type": "short-answer",
            "correct_answer": correct_text,
            "explanation": explanation,
            "difficulty": difficulty
        }
    
    else:
        return question


def _parse_plain_text_quiz(text: str) -> List[Dict]:
    """
    Fallback parser: extract MCQs from plain-text output when the model
    doesn't return JSON.  Handles formats like:
        1. Question text?
        A) option   B) option   C) option   D) option
        Answer: B
    """
    questions: List[Dict] = []
    # Split into blocks per question (numbered or "MCQ N:")
    blocks = re.split(r'(?:^|\n)(?:MCQ\s*\d+[:\.]?|\d+[\.\):])', text)
    blocks = [b.strip() for b in blocks if b.strip()]

    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue

        # Extract the best candidate question line
        embedded = _extract_embedded_options(block)
        q_text = embedded["question"] or _extract_question_from_lines(lines)

        # Extract options A-D
        options: Dict[str, str] = dict(embedded.get("options") or {})
        for line in lines:
            m = re.match(r'^\(?\s*([A-D])\s*\)?\s*[).\]:\-]\s*(.+)', line)
            if m:
                options[m.group(1)] = _clean_option_text(m.group(2))

        if len(options) < 2:
            continue  # not a real question block

        # Try to find correct answer
        correct = _extract_answer_letter(embedded.get("correct_answer", ""), options)
        for line in lines:
            if correct:
                break
            m = re.search(r'(?:answer|correct)[:\s]*([A-D])', line, re.I)
            if m:
                correct = m.group(1).upper()
                break
        if not correct:
            correct = list(options.keys())[0]  # fallback

        # Pad missing options
        for letter in "ABCD":
            options.setdefault(letter, "Not applicable")

        questions.append({
            "question": q_text,
            "options": options,
            "correct_answer": correct,
            "explanation": embedded.get("explanation", ""),
            "difficulty": "medium"
        })

    return questions


class QuizGenerator:
    """Generate quizzes from PDF content using Ollama"""
    
    def __init__(self):
        """Initialize model settings"""
        self.model = settings.OLLAMA_CHAT_MODEL

    def _is_small_local_model(self) -> bool:
        model_name = (self.model or "").lower()
        return any(size in model_name for size in ("0.5b", "1b", "1.5b", "1.8b", "2b"))

    def _validate_topic_in_text(self, text: str, topic: str) -> bool:
        """Check if the specified topic exists in the text."""
        if not topic or not text:
            return True  # Allow if no topic specified
        
        text_lower = text.lower()
        topic_lower = topic.lower()
        
        # Split topic into keywords and filter out common stop words
        stop_words = {"the", "a", "an", "of", "in", "to", "and", "or", "is", "are", "was", "were", "be", "by", "for", "with", "on", "at", "from"}
        keywords = [kw for kw in topic_lower.split() if kw not in stop_words and len(kw) > 2]
        
        # If all keywords are stop words, accept it
        if not keywords:
            keywords = topic_lower.split()
        
        # Check if at least 50% of meaningful keywords appear in text
        found_keywords = sum(1 for keyword in keywords if keyword in text_lower)
        threshold = max(1, len(keywords) * 0.5)  # At least 1 keyword or 50%, whichever is greater
        
        logger.info(f"Topic validation: '{topic}' - Found {found_keywords}/{len(keywords)} keywords in text (threshold: {threshold})")
        
        return found_keywords >= threshold

    def _representative_text(self, text: str, max_chars: int) -> str:
        """Sample start/middle/end segments for better whole-document coverage."""
        if len(text) <= max_chars:
            return text

        part = max_chars // 3
        start = text[:part]
        mid_start = max((len(text) // 2) - (part // 2), 0)
        middle = text[mid_start:mid_start + part]
        end = text[-part:]
        return (start + "\n\n" + middle + "\n\n" + end).strip()

    def _prepare_input(self, text: str, study_context: str, max_chars: int) -> str:
        candidate = (study_context or "").strip()
        if candidate:
            return candidate[:max_chars]
        return self._representative_text(text, max_chars)

    async def _retrieve_relevant_chunks(
        self, 
        pdf_identifier: str, 
        search_query: str, 
        num_chunks: int = 5
    ) -> str:
        """
        Retrieve relevant chunks from vector DB using RAG.
        
        Args:
            pdf_identifier: PDF URL or upload identifier
            search_query: Topic/query to search for
            num_chunks: Number of chunks to retrieve
            
        Returns:
            Combined text of relevant chunks
        """
        try:
            total_started = time.perf_counter()
            logger.info(f"Retrieving chunks for: '{search_query}' from {pdf_identifier}")
            
            # Query vector DB for relevant chunks
            phase_started = time.perf_counter()
            results = await vector_db.query_documents(
                pdf_url=pdf_identifier,
                query=search_query,
                n_results=num_chunks
            )
            log_phase(
                logger,
                "quiz.rag",
                "vector_query",
                phase_started,
                requested_chunks=num_chunks,
                result_count=len(results.get("documents") or []),
            )
            
            # Combine only the highest-value parts of retrieved documents so quiz prompts stay fast.
            if results.get("documents"):
                phase_started = time.perf_counter()
                selected_parts: List[str] = []
                total_chars = 0
                max_total_chars = 5200
                max_chunk_chars = 850

                for document in results["documents"]:
                    excerpt = str(document or "").strip()[:max_chunk_chars].strip()
                    if not excerpt:
                        continue
                    if total_chars + len(excerpt) > max_total_chars:
                        break
                    selected_parts.append(excerpt)
                    total_chars += len(excerpt)

                combined_text = "\n\n".join(selected_parts)
                logger.info(
                    f"Retrieved {len(selected_parts)} relevant chunks for quiz generation "
                    f"({total_chars} chars)"
                )
                log_phase(
                    logger,
                    "quiz.rag",
                    "combine_chunks",
                    phase_started,
                    selected_chunks=len(selected_parts),
                    total_chars=total_chars,
                )
                log_phase(logger, "quiz.rag", "total", total_started, used_rag=True)
                return combined_text
            else:
                logger.warning(f"No relevant chunks found for: '{search_query}'")
                log_phase(logger, "quiz.rag", "total", total_started, used_rag=False)
                return ""
                
        except Exception as e:
            logger.warning(f"Vector DB retrieval failed: {e}. Falling back to full text.")
            return ""

    def _estimate_max_tokens(self, num_questions: int) -> int:
        """Estimate max tokens needed for quiz generation."""
        # Keep enough room for grounded options/explanations without over-allocating
        # on small local models, where large output budgets noticeably slow generation.
        if self._is_small_local_model():
            return max(320, min(900, 200 * max(1, num_questions) + 80))
        return max(650, min(2200, 180 * max(1, num_questions) + 180))

    async def _chat_quiz(self, prompt: str, max_tokens: int = 1200, trace_label: str = "attempt", requested_diff: str = "medium") -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "Return ONLY a JSON object with this schema: "
                    "{\"questions\":[{\"question\":\"...\",\"question_type\":\"mcq\","
                    "\"options\":{\"A\":\"...\",\"B\":\"...\",\"C\":\"...\",\"D\":\"...\"},"
                    "\"correct_answer\":\"A\",\"explanation\":\"...\",\"difficulty\":\"" + requested_diff + "\"}]}. "
                    "Use only the supplied text. If an exact topic is provided, every question must stay on that exact topic. "
                    "Each question must be distinct, grounded in the text, and have one correct answer letter from A-D. "
                    "Keep explanations to one short sentence. Do not include markdown, tags, or commentary."
                )
            },
            {"role": "user", "content": prompt}
        ]

        try:
            phase_started = time.perf_counter()
            result = await ollama_client.chat(
                messages=messages,
                model=self.model,
                temperature=0.15,
                max_tokens=max_tokens,
                response_format="json",
            )
            log_phase(logger, f"quiz.{trace_label}", "llm_generate_json", phase_started, max_tokens=max_tokens)
            return result
        except Exception as exc:
            logger.warning("Quiz JSON mode failed; retrying without explicit JSON mode: %s", exc)
            phase_started = time.perf_counter()
            result = await ollama_client.chat(
                messages=messages,
                model=self.model,
                temperature=0.15,
                max_tokens=max_tokens,
            )
            log_phase(logger, f"quiz.{trace_label}", "llm_generate_fallback", phase_started, max_tokens=max_tokens)
            return result
    
    async def generate_quiz(
        self,
        text: str,
        num_questions: int = None,
        difficulty: str = None,
        study_context: str = "",
        search_query: str = None,
        pdf_identifier: str = None,
        question_types: List[str] = None
    ) -> Dict:
        try:
            total_started = time.perf_counter()
            if num_questions is None:
                num_questions = settings.DEFAULT_QUIZ_QUESTIONS
            # Keep quiz size in a practical range while honoring user input from UI.
            num_questions = max(1, min(int(num_questions), 15))
            
            # Set default question types if not provided
            if question_types is None:
                question_types = ["mcq"]
            # Ensure valid question types
            valid_types = {"mcq", "fill-in-blank", "true-false", "short-answer"}
            question_types = [t for t in question_types if t in valid_types]
            if not question_types:
                question_types = ["mcq"]
            
            logger.info(f"Generating quiz with types: {', '.join(question_types)}")
            
            # STEP 1: RETRIEVAL-AUGMENTED GENERATION (RAG) ARCHITECTURE
            # If search_query provided and pdf_identifier available, retrieve relevant chunks
            if search_query and search_query.strip() and pdf_identifier:
                search_query = search_query.strip()[:100]
                logger.info(f"Using RAG: Retrieving chunks for topic: '{search_query}'")
                
                # Retrieve relevant chunks from vector DB
                rag_text = await self._retrieve_relevant_chunks(
                    pdf_identifier=pdf_identifier,
                    search_query=search_query,
                    num_chunks=8
                )
                
                if rag_text:
                    # Use RAG-retrieved chunks instead of full text
                    text = rag_text
                    logger.info("RAG retrieval successful - using relevant chunks")
                else:
                    logger.warning("RAG retrieval returned no chunks - falling back to full text")
                    phase_started = time.perf_counter()
                    text = self._prepare_input(text, study_context, max_chars=5000)
                    log_phase(logger, "quiz", "prepare_input_fallback", phase_started, source_chars=len(text))
            else:
                # Use compact cached context when available for faster local inference.
                phase_started = time.perf_counter()
                text = self._prepare_input(text, study_context, max_chars=5000)
                log_phase(
                    logger,
                    "quiz",
                    "prepare_input",
                    phase_started,
                    source_chars=len(text),
                    used_study_context=bool((study_context or "").strip()),
                )
            
            # STEP 2: VALIDATE TOPIC IF PROVIDED
            if search_query and search_query.strip():
                phase_started = time.perf_counter()
                topic_exists = self._validate_topic_in_text(text, search_query)
                log_phase(logger, "quiz", "validate_topic", phase_started, topic_found=topic_exists)
                if not topic_exists:
                    error_msg = (
                        f"Topic '{search_query}' not found in the PDF document. "
                        f"Please ensure the PDF contains content related to '{search_query}'. "
                        f"Check the document or try a different topic."
                    )
                    # Log as INFO since this is expected user input validation, not a system error
                    logger.info(f"Topic validation failed: {error_msg}")
                    raise Exception(error_msg)
            
            diff_note = ""
            if difficulty and difficulty.lower() in ("basic", "easy"):
                diff_note = "Difficulty: EASY"
            elif difficulty and difficulty.lower() == "medium":
                diff_note = "Difficulty: MEDIUM"
            elif difficulty and difficulty.lower() == "hard":
                diff_note = "Difficulty: HARD (Create highly challenging, rigorous questions requiring deep conceptual reasoning)"

            # Add topic filter instruction if search_query provided
            topic_instruction = ""
            rag_note = ""
            if search_query and search_query.strip():
                topic_instruction = f"*** CRITICAL: TOPIC *** ONLY questions about: {search_query}\nEvery question MUST be ONLY about: {search_query}\nDO NOT ask about any other topics.\nDO NOT ask about related topics.\nONLY {search_query}"
                rag_note = "(Using RAG - Retrieval-Augmented Generation: Questions based on relevant chunks for: " + search_query + ")"

            # Build question types instruction
            question_types_note = ""
            if len(question_types) == 1 and question_types[0] == "mcq":
                question_types_note = "QUESTION FORMAT: Multiple Choice (MCQ) with 4 options (A, B, C, D)\n"
            else:
                types_list = ", ".join(question_types)
                question_types_note = f"QUESTION TYPES: Mix the following types: {types_list}\nSpecify 'question_type' field for each question.\n"

            user_prompt = (
                f"TASK: Create exactly {num_questions} questions about: {search_query if search_query else 'provided text'}\n"
                f"DIFFICULTY LEVEL: {diff_note}\n"
                f"{question_types_note}"
                f"{topic_instruction}\n"
                f"{rag_note}\n\n"
                "⚠️ STRICT TOPIC VALIDATION - READ CAREFULLY:\n"
                "- EVERY question MUST be SPECIFICALLY about the stated topic ONLY\n"
                "- If topic is 'Multiplication of Algebraic Expressions', questions must be about multiplication in algebra - NOT general math\n"
                "- Questions must reference specific concepts from the text provided below\n"
                "- REJECT any question that could apply to other topics or is too generic\n"
                "- NO questions about related topics, only the EXACT stated topic\n\n"
                "QUESTION GENERATION RULES (CRITICAL):\n"
                "1. ALWAYS generate questions in MCQ format with exactly 4 options (A, B, C, D)\n"
                "2. Even if question_type is 'fill-in-blank', 'true-false', or 'short-answer', still generate MCQ\n"
                "3. Each option (A,B,C,D) MUST be realistic and from the text - NOT generic placeholders\n"
                "4. Explanation must justify why correct_answer is right based on text content\n"
                "5. NEVER include template examples or placeholder tags in your response\n"
                "6. DO NOT ask about related but different topics\n"
                "7. Each question must be distinct and not repeat previous questions\n\n"
                "⚠️ RESPONSE FORMAT REQUIREMENT:\n"
                "RESPOND WITH ONLY VALID JSON - exactly 3 questions in this format (MUST have quotes around all strings):\n"
                '{"questions":[{"question":"Here write the complete question with specific details from text?","question_type":"mcq","options":{"A":"First option from text","B":"Second option from text","C":"Third option from text","D":"Fourth option from text"},"correct_answer":"A","explanation":"Why optionA is correct based on the text","difficulty":"' + (difficulty or "medium").lower() + '"},...repeat 2 more times...]}\n\n'
                "TEXT DATA TO USE:\n"
                f"{text}"
            )

            def _build_quiz_prompt(
                request_count: int,
                avoid_questions: Optional[List[str]] = None,
                excerpt_limit: Optional[int] = None
            ) -> str:
                lines = [
                    f"Generate exactly {request_count} grounded quiz question(s).",
                    f"Difficulty: {diff_note or 'MEDIUM'}",
                    "Question format: MCQ only with 4 options (A, B, C, D).",
                    "Set question_type to mcq for every item.",
                    "Every option must be realistic and supported by the text.",
                    "Each question stem must be one concise sentence.",
                    "Do not copy textbook exercises with sub-parts like (i), (ii), or (iii).",
                    "Do not return explanations, prose, or markdown outside the JSON object.",
                    "Keep every option short and distinct.",
                    "Keep each explanation to one short sentence.",
                ]

                if search_query and search_query.strip():
                    lines.append(f"Exact topic: {search_query}")
                    lines.append("If that exact topic is not clearly present, return {\"questions\":[]}.")
                else:
                    lines.append("Cover the most important concepts from the provided text.")

                if avoid_questions:
                    lines.append("Do not repeat or closely paraphrase these existing questions:")
                    lines.extend([f"- {question}" for question in avoid_questions[:3]])

                source_text = text if excerpt_limit is None else text[:excerpt_limit]
                lines.append("")
                lines.append("Source text:")
                lines.append(source_text)
                return "\n".join(lines)

            user_prompt = _build_quiz_prompt(num_questions)

            def _parse_questions_from_content(content: str) -> List[Dict]:
                logger.info(f"Raw quiz response (first 500 chars): {content[:500]}")
                cleaned = content.strip()

                if "```" in cleaned:
                    parts = cleaned.split("```")
                    for part in parts:
                        candidate = part.strip()
                        if candidate.lower().startswith("json"):
                            candidate = candidate[4:].strip()
                        if candidate.startswith("{") or candidate.startswith("["):
                            cleaned = candidate
                            break

                parsed_questions = _load_questions_from_jsonish(cleaned)

                if parsed_questions is None:
                    try:
                        obj_match = re.search(r'\{.*"questions"\s*:\s*\[.*\]\s*\}', _repair_json_candidate(cleaned), re.DOTALL)
                        if obj_match:
                            parsed_questions = _load_questions_from_jsonish(obj_match.group(0))
                    except Exception as e:
                        logger.debug(f"JSON parse attempt 2 failed: {e}")
                        pass

                if parsed_questions is None:
                    try:
                        list_match = re.search(r'\[.*\]', _repair_json_candidate(cleaned), re.DOTALL)
                        if list_match:
                            parsed_questions = _load_questions_from_jsonish(list_match.group(0))
                    except Exception as e:
                        logger.debug(f"JSON parse attempt 3 failed: {e}")
                        pass

                if parsed_questions is None:
                    parsed_questions = _parse_loose_structured_quiz(cleaned)
                    if parsed_questions:
                        logger.info(f"Loose structured parser recovered {len(parsed_questions)} questions")

                if parsed_questions is None:
                    logger.warning(f"JSON parse failed. Attempting fallback text parsing...")
                    parsed_questions = _parse_plain_text_quiz(cleaned)
                    if parsed_questions:
                        logger.info(f"Fallback parser recovered {len(parsed_questions)} questions from text")

                return _normalize_questions(parsed_questions or [])

            all_questions: List[Dict] = []
            seen_questions = set()
            remaining = num_questions

            if self._is_small_local_model():
                attempt_plan = [1] * (num_questions + 2)
            else:
                attempt_plan = [num_questions] + [1] * max(2, num_questions)

            for attempt, planned_count in enumerate(attempt_plan):
                if remaining <= 0:
                    break

                request_count = min(planned_count, remaining)
                if attempt == 0 and request_count == num_questions:
                    prompt = user_prompt
                elif attempt <= 1:
                    prompt = _build_quiz_prompt(
                        request_count,
                        avoid_questions=sorted(seen_questions),
                        excerpt_limit=3200 if self._is_small_local_model() else None,
                    )
                else:
                    prompt = _build_quiz_prompt(
                        request_count,
                        avoid_questions=sorted(seen_questions),
                        excerpt_limit=2200,
                    )

                try:
                    attempt_label = f"attempt_{attempt + 1}"
                    content = await self._chat_quiz(
                        prompt,
                        max_tokens=self._estimate_max_tokens(request_count),
                        trace_label=attempt_label,
                        requested_diff=(difficulty or "medium").lower()
                    )

                    phase_started = time.perf_counter()
                    parsed = _parse_questions_from_content(content)
                    log_phase(
                        logger,
                        f"quiz.{attempt_label}",
                        "parse_output",
                        phase_started,
                        parsed_questions=len(parsed),
                    )
                    parsed_count = len(parsed)
                    logger.info(f"Attempt {attempt + 1}: Parsed {parsed_count} questions")
                    
                    for q in parsed:
                        q_key = q.get("question", "").strip().lower()
                        if q_key and q_key not in seen_questions:
                            seen_questions.add(q_key)
                            all_questions.append(q)

                    remaining = num_questions - len(all_questions)
                    logger.info(f"After attempt {attempt + 1}: {len(all_questions)}/{num_questions} questions collected")
                    
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
                    continue

            questions = all_questions[:num_questions]

            # Be more lenient: accept 80% or higher of requested questions
            min_acceptable = max(1, int(num_questions * 0.8))
            if len(questions) < min_acceptable:
                logger.error(f"Generated only {len(questions)}/{num_questions} questions (minimum {min_acceptable} required)")
                raise Exception(
                    f"Could not generate enough questions. Generated {len(questions)}/{num_questions}. Please try again or reduce the number requested."
                )

            if not questions:
                raise Exception("Could not extract any questions from AI response. Please try again.")
            
            # STEP 3: CONVERT QUESTIONS TO REQUESTED TYPES
            # If multiple question types requested, mix them
            phase_started = time.perf_counter()
            if len(question_types) > 1:
                converted_questions = []
                for idx, question in enumerate(questions):
                    # Distribute question types across questions
                    target_type = question_types[idx % len(question_types)]
                    converted_q = _convert_to_question_type(question, target_type)
                    converted_questions.append(converted_q)
                questions = converted_questions
            elif len(question_types) == 1 and question_types[0] != "mcq":
                # Single non-MCQ type requested
                converted_questions = []
                for question in questions:
                    converted_q = _convert_to_question_type(question, question_types[0])
                    converted_questions.append(converted_q)
                questions = converted_questions
            log_phase(
                logger,
                "quiz",
                "convert_question_types",
                phase_started,
                output_questions=len(questions),
                requested_types=",".join(question_types),
            )
            
            # STEP 4: FILTER QUESTIONS BY DIFFICULTY IF SPECIFIED
            if difficulty:
                phase_started = time.perf_counter()
                # Normalize difficulty mapping (basic = easy)
                difficulty_normalized = difficulty.lower()
                if difficulty_normalized == "basic":
                    difficulty_normalized = "easy"
                
                # Filter questions to match requested difficulty
                filtered_questions = [
                    q for q in questions 
                    if q.get("difficulty", "medium").lower() == difficulty_normalized
                ]
                
                logger.info(
                    f"Difficulty filter applied: {len(questions)} questions → {len(filtered_questions)} questions "
                    f"with difficulty '{difficulty}'"
                )
                
                # If we have filtered questions, use them; otherwise warn but use all
                if filtered_questions:
                    questions = filtered_questions
                else:
                    logger.warning(
                        f"No questions found with requested difficulty '{difficulty}'. "
                        f"Returning all generated questions instead."
                    )
                
                log_phase(
                    logger,
                    "quiz",
                    "filter_by_difficulty",
                    phase_started,
                    requested_difficulty=difficulty,
                    filtered_questions=len(questions),
                )
            
            log_phase(logger, "quiz", "total", total_started, questions=len(questions))
            logger.info(f"Generated {len(questions)} quiz questions (requested {num_questions})")
            
            return {
                "questions": questions,
                "total_questions": len(questions),
                "difficulty_breakdown": self._count_difficulty(questions),
                "requested_difficulty": difficulty
            }
            
        except Exception as e:
            logger.error(f"Error generating quiz: {e}")
            raise Exception(f"Failed to generate quiz: {str(e)}")
    
    def _count_difficulty(self, questions: List[Dict]) -> Dict[str, int]:
        """Count questions by difficulty level"""
        counts = {"easy": 0, "medium": 0, "hard": 0}
        for q in questions:
            difficulty = q.get("difficulty", "medium").lower()
            if difficulty in counts:
                counts[difficulty] += 1
        return counts
    
    async def validate_answer(self, question_data: Dict, user_answer: str) -> Dict:
        """
        Validate a user's answer
        
        Args:
            question_data: Question dictionary
            user_answer: User's selected answer (A, B, C, or D)
            
        Returns:
            Validation result
        """
        correct = question_data["correct_answer"].upper()
        user = user_answer.upper()
        
        is_correct = correct == user
        
        return {
            "is_correct": is_correct,
            "correct_answer": correct,
            "user_answer": user,
            "explanation": question_data.get("explanation", ""),
            "correct_option_text": question_data["options"].get(correct, "")
        }

# Global quiz generator instance
quiz_generator = QuizGenerator()
