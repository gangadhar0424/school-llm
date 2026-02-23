"""
AI Quiz Generation Module
Generates multiple-choice questions with answers using Ollama
"""
import logging
import json
import re
from typing import List, Dict
from config import settings
from ai.ollama_client import ollama_client

logger = logging.getLogger(__name__)


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

        # First non-empty line is the question
        q_text = lines[0]

        # Extract options A-D
        options: Dict[str, str] = {}
        for line in lines:
            m = re.match(r'^([A-D])\s*[).\]:\-]\s*(.+)', line)
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
    
    async def generate_quiz(self, text: str, num_questions: int = None, difficulty: str = None) -> Dict:
        try:
            if num_questions is None:
                num_questions = settings.DEFAULT_QUIZ_QUESTIONS
            
            max_chars = 2000
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            if num_questions > 3:
                num_questions = 3
            
            diff_note = ""
            if difficulty and difficulty.lower() in ("basic", "easy"):
                diff_note = "EASY level."
            elif difficulty and difficulty.lower() == "medium":
                diff_note = "MEDIUM level."
            elif difficulty and difficulty.lower() == "hard":
                diff_note = "HARD level."
            
            prompt = (
                f"Generate {num_questions} multiple-choice questions from the text below. {diff_note}\n"
                f"For EACH question give:\n"
                f"- The question\n"
                f"- Four options A, B, C, D\n"
                f"- The correct answer letter\n\n"
                f"Text:\n{text}"
            )
            
            content = await ollama_client.chat(
                messages=[
                    {"role": "system", "content": "You are a quiz generator."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=800
            )
            
            logger.info(f"Raw quiz response (first 500 chars): {content[:500]}")
            
            # --- Try JSON first ---
            questions = None
            try:
                # Strip markdown code fences
                cleaned = content
                if "```" in cleaned:
                    parts = cleaned.split("```")
                    for part in parts:
                        part = part.strip().lstrip("json").strip()
                        if part.startswith("["):
                            cleaned = part
                            break
                
                json_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
                if json_match:
                    questions = json.loads(json_match.group(0))
            except (json.JSONDecodeError, Exception):
                pass
            
            # --- Fallback: parse plain text ---
            if not questions:
                logger.info("JSON parse failed, using plain-text parser")
                questions = _parse_plain_text_quiz(content)
            
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
