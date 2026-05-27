"""
AI response evaluation module.

Reference-free LLM-as-judge scoring of:
  - real student Q&A traffic (chat_sessions)
  - generated summaries (generated_summaries)
  - generated quiz questions (generated_quizzes)
  - teacher AI-generated assignment questions (assignments)

Public entry points:
    from evaluation import (
        run_evaluation_on_recent_qa,
        run_evaluation_on_summaries,
        run_evaluation_on_quizzes,
        run_evaluation_on_teacher_questions,
    )
    from evaluation.storage import save_run, list_runs, get_run, list_run_items

Models used:
    The judge LLM is whichever model `llm_client.evaluation_model` points to —
    in production that's Claude Haiku (cheap, fast, reliable for grading).
"""
from evaluation.judge import (
    judge_qa_pair_reference_free,
    judge_summary, judge_quiz_question,
    JudgeScores, ReferenceFreeScores, QuizQuestionScores,
)
from evaluation.runner import (
    run_evaluation_on_recent_qa,
    run_evaluation_on_summaries, run_evaluation_on_quizzes,
    run_evaluation_on_teacher_questions,
)
from evaluation.storage import save_run, list_runs, get_run, list_run_items

__all__ = [
    "judge_qa_pair_reference_free",
    "judge_summary", "judge_quiz_question",
    "JudgeScores", "ReferenceFreeScores", "QuizQuestionScores",
    "run_evaluation_on_recent_qa",
    "run_evaluation_on_summaries", "run_evaluation_on_quizzes",
    "run_evaluation_on_teacher_questions",
    "save_run", "list_runs", "get_run", "list_run_items",
]
