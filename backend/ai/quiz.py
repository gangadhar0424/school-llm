"""
AI Quiz Generation Module
Generates multiple-choice questions with answers using Ollama
"""
import logging
import json
import re
from typing import List, Dict, Any
from config import settings
from ai.ollama_client import ollama_client

logger = logging.getLogger(__name__)


def _clean_question_text(text: str) -> str:
    """Remove markdown/labels and return a clean question string."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r'^\s*#{1,6}\s*', '', cleaned)
    cleaned = re.sub(r'^\s*(?:question|mcq|q)\s*\d*\s*[:.)\-]*\s*', '', cleaned, flags=re.I)
    cleaned = cleaned.strip(' \t\n\r"\'')
    return cleaned


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


def _normalize_questions(raw_questions: List[Any]) -> List[Dict]:
    """Normalize model output into consistent quiz question objects."""
    normalized: List[Dict] = []

    for raw in raw_questions or []:
        if not isinstance(raw, dict):
            continue

        q_text = _clean_question_text(str(raw.get("question", "")))
        if not q_text or re.fullmatch(r'(?i)(question|mcq|q)\s*\d*[:.)\- ]*', q_text):
            q_text = "Question not provided. Choose the best option."

        raw_options = raw.get("options", {})
        options: Dict[str, str] = {}

        if isinstance(raw_options, dict):
            for k, v in raw_options.items():
                key = str(k).strip().upper()[:1]
                if key in "ABCD":
                    options[key] = str(v).strip()
        elif isinstance(raw_options, list):
            for idx, value in enumerate(raw_options[:4]):
                key = chr(ord('A') + idx)
                options[key] = str(value).strip()

        # Keep only non-empty options first.
        options = {k: v for k, v in options.items() if v}

        if len(options) < 2:
            continue

        # Ensure exactly 4 options (A-D) in deterministic order.
        ordered_keys = [k for k in "ABCD" if k in options]
        values = [options[k] for k in ordered_keys][:4]
        while len(values) < 4:
            values.append("Not applicable")
        options = {chr(ord('A') + i): values[i] for i in range(4)}

        correct_raw = str(raw.get("correct_answer", "")).upper()
        match = re.search(r'[A-D]', correct_raw)
        correct = match.group(0) if match else "A"

        difficulty = str(raw.get("difficulty", "medium")).lower()
        if difficulty not in {"easy", "medium", "hard", "basic"}:
            difficulty = "medium"

        normalized.append({
            "question": q_text,
            "options": options,
            "correct_answer": correct,
            "explanation": str(raw.get("explanation", "")).strip(),
            "difficulty": difficulty
        })

    return normalized


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
        q_text = _extract_question_from_lines(lines)

        # Extract options A-D
        options: Dict[str, str] = {}
        for line in lines:
            m = re.match(r'^\(?\s*([A-D])\s*\)?\s*[).\]:\-]\s*(.+)', line)
            if m:
                options[m.group(1)] = m.group(2).strip()

        if len(options) < 2:
            continue  # not a real question block

        # Try to find correct answer
        correct = ""
        for line in lines:
            m = re.search(r'(?:answer|correct)[:\s]*([A-D])', line, re.I)
            if m:
                correct = m.group(1).upper()
                break
        if not correct:
            correct = list(options.keys())[0]  # fallback

        # Pad missing options
        for letter in "ABCD":
            options.setdefault(letter, "—")

        questions.append({
            "question": q_text,
            "options": options,
            "correct_answer": correct,
            "explanation": "",
            "difficulty": "medium"
        })

    return questions


class QuizGenerator:
    """Generate quizzes from PDF content using Ollama"""
    
    def __init__(self):
        """Initialize model settings"""
        self.model = settings.OLLAMA_CHAT_MODEL

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

    async def _chat_quiz(self, prompt: str, max_tokens: int = 1200) -> str:
        return await ollama_client.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You MUST return ONLY a valid JSON object. No extra text, no markdown. The JSON must have EXACTLY these fields: questions (array), where each item has question, options (dict with A,B,C,D), correct_answer, explanation, difficulty. Return nothing else."
                },
                {"role": "user", "content": prompt}
            ],
            model=self.model,
            temperature=0.3,
            max_tokens=max_tokens
        )
    
    async def generate_quiz(self, text: str, num_questions: int = None, difficulty: str = None) -> Dict:
        try:
            if num_questions is None:
                num_questions = settings.DEFAULT_QUIZ_QUESTIONS
            # Keep quiz size in a practical range while honoring user input from UI.
            num_questions = max(1, min(int(num_questions), 15))
            
            # Use optimized document coverage for speed without sacrificing quality.
            max_chars = 12000
            text = self._representative_text(text, max_chars)
            
            diff_note = ""
            if difficulty and difficulty.lower() in ("basic", "easy"):
                diff_note = "EASY level."
            elif difficulty and difficulty.lower() == "medium":
                diff_note = "MEDIUM level."
            elif difficulty and difficulty.lower() == "hard":
                diff_note = "HARD level."

            user_prompt = (
                f"Generate EXACTLY {num_questions} multiple-choice questions from the text. {diff_note}\n"
                "MANDATORY JSON FIELDS FOR EACH QUESTION:\n"
                "- question: The question text\n"
                "- options: A dictionary with keys A, B, C, D (exactly 4 keys) and string values\n"
                "- correct_answer: Single letter A or B or C or D\n"
                "- explanation: Brief reason why this is correct\n"
                "- difficulty: One of: easy, medium, hard\n\n"
                "EXAMPLE RESPONSE FORMAT:\n"
                '{\n'
                '  "questions": [\n'
                '    {\n'
                '      "question": "What is X?",\n'
                '      "options": {"A":"Option 1","B":"Option 2","C":"Option 3","D":"Option 4"},\n'
                '      "correct_answer": "B",\n'
                '      "explanation": "Because Y",\n'
                '      "difficulty": "medium"\n'
                '    }\n'
                '  ]\n'
                '}\n\n'
                f"EXACT COUNT: Generate exactly {num_questions} questions, no more, no less.\n"
                "Use exact names/terms from the text where possible.\n"
                f"Text:\n{text}"
            )

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

                parsed_questions = None
                try:
                    data = json.loads(cleaned)
                    if isinstance(data, dict) and isinstance(data.get("questions"), list):
                        parsed_questions = data["questions"]
                    elif isinstance(data, list):
                        parsed_questions = data
                except Exception:
                    pass

                if parsed_questions is None:
                    try:
                        obj_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                        if obj_match:
                            data = json.loads(obj_match.group(0))
                            if isinstance(data, dict) and isinstance(data.get("questions"), list):
                                parsed_questions = data["questions"]
                    except Exception:
                        pass

                if parsed_questions is None:
                    try:
                        list_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
                        if list_match:
                            data = json.loads(list_match.group(0))
                            if isinstance(data, list):
                                parsed_questions = data
                    except Exception:
                        pass

                if parsed_questions is None:
                    logger.warning(
                        f"Attempt {attempt + 1}: JSON parse failed. Response structure not recognized. "
                        f"Expected 'questions' array with question/options/correct_answer/explanation."
                    )
                    parsed_questions = []

                return _normalize_questions(parsed_questions or [])

            # Try 2 fast attempts to generate questions (not 4 for speed).
            all_questions: List[Dict] = []
            seen_questions = set()
            remaining = num_questions

            for attempt in range(3):
                if remaining <= 0:
                    break

                prompt = user_prompt if attempt == 0 else (
                    f"Generate EXACTLY {remaining} ADDITIONAL unique questions (not repeating previous ones). {diff_note}\n"
                    "Return ONLY JSON object with key questions and the same schema as before.\n\n"
                    f"Text:\n{text}"
                )

                max_tokens = 1000 if remaining <= 5 else 1200
                content = await self._chat_quiz(prompt, max_tokens=max_tokens)

                parsed = _parse_questions_from_content(content)
                for q in parsed:
                    q_key = q.get("question", "").strip().lower()
                    if q_key and q_key not in seen_questions:
                        seen_questions.add(q_key)
                        all_questions.append(q)

                remaining = num_questions - len(all_questions)

            questions = all_questions[:num_questions]

            if len(questions) < num_questions:
                # Final targeted pass: request missing items one-by-one for better reliability.
                while len(questions) < num_questions:
                    needed = num_questions - len(questions)
                    fallback_prompt = (
                        f"Generate EXACTLY 1 unique multiple-choice question from the text below. {diff_note}\n"
                        "Return ONLY JSON object with key questions using the same schema.\n"
                        "Do not repeat previous question wording.\n\n"
                        f"Text:\n{text}"
                    )
                    one_content = await self._chat_quiz(fallback_prompt, max_tokens=500)
                    one_parsed = _parse_questions_from_content(one_content)
                    added = 0
                    for q in one_parsed:
                        q_key = q.get("question", "").strip().lower()
                        if q_key and q_key not in seen_questions:
                            seen_questions.add(q_key)
                            questions.append(q)
                            added += 1
                            break
                    if added == 0:
                        logger.warning(
                            f"Could not generate additional unique question; still missing {needed}"
                        )
                        break

            if len(questions) < num_questions:
                raise Exception(
                    f"Could not generate requested {num_questions} questions right now. Generated {len(questions)}. Please try again."
                )

            if not questions:
                raise Exception("Could not extract questions from AI response. Please try again.")
            
            logger.info(f"Generated {len(questions)} quiz questions")
            
            return {
                "questions": questions,
                "total_questions": len(questions),
                "difficulty_breakdown": self._count_difficulty(questions)
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
