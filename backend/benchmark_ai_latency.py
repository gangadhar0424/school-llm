"""
Simple local benchmark for summary, quiz, and Q&A latency.

Runs directly against backend modules so you can benchmark without auth or the web UI.
"""
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ai.ollama_client import ollama_client
from ai.qa import qa_system
from ai.quiz import quiz_generator
from ai.summary import summary_generator
from pdf_handler import pdf_handler
from vector_db import vector_db


DEFAULT_PDF = Path("runtime_data/uploads/Research_Paper BATCH 51 REVIEW1.pdf")
DEFAULT_TOPIC = "warehouse automation system"
DEFAULT_QUESTION = "How does the warehouse automation system use AI agents to improve operations?"
DEFAULT_PASSES = 1


async def benchmark_case(label: str, coro):
    started = time.perf_counter()
    try:
        result = await coro
        elapsed = time.perf_counter() - started
        print(f"{label}: {elapsed:.2f}s")
        return elapsed, result, None
    except Exception as exc:
        elapsed = time.perf_counter() - started
        print(f"{label}: FAILED after {elapsed:.2f}s -> {exc}")
        return elapsed, None, exc


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    passes = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PASSES
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"Benchmark PDF: {pdf_path}")
    print(f"Model: {ollama_client.default_model}")

    process_started = time.perf_counter()
    pdf_data = await pdf_handler.process_pdf(str(pdf_path), is_url=False)
    process_elapsed = time.perf_counter() - process_started
    print(f"process_pdf: {process_elapsed:.2f}s")

    study_context = pdf_data.get("study_context") or pdf_handler.build_study_context(
        pdf_data.get("chunks", []),
        pdf_data.get("pages_text", []),
        sections=pdf_data.get("sections", []),
    )

    pdf_key = f"benchmark::{pdf_path.resolve()}"
    chunks = pdf_data.get("chunks", [])
    metadatas = [
        {
            "chunk_index": i,
            "page_number": int(chunk.get("metadata", {}).get("page_number", 0) or 0),
            "chapter": str(chunk.get("metadata", {}).get("chapter", "") or ""),
            "topic": str(chunk.get("metadata", {}).get("topic", "") or ""),
            "section_code": str(chunk.get("metadata", {}).get("section_code", "") or ""),
            "section_title": str(chunk.get("metadata", {}).get("section_title", "") or ""),
            "start_pos": int(chunk.get("start_pos", 0) or 0),
            "end_pos": int(chunk.get("end_pos", 0) or 0),
        }
        for i, chunk in enumerate(chunks)
    ]
    await vector_db.add_documents(
        pdf_url=pdf_key,
        chunks=[chunk.get("text", "") for chunk in chunks],
        metadata=metadatas,
    )

    await ollama_client.warm_up()

    summary_runs = []
    quiz_runs = []
    qa_runs = []

    for run_no in range(1, passes + 1):
        print(f"\nPass {run_no}")
        summary_elapsed, summary_result, summary_error = await benchmark_case(
            "summary_both",
            summary_generator.generate_both_summaries(
                pdf_data.get("full_text", ""),
                study_context=study_context,
            ),
        )
        if summary_error is None:
            summary_runs.append(summary_elapsed)
            print(
                f"  short_summary_chars={len((summary_result or {}).get('short_summary', ''))} "
                f"detailed_summary_chars={len((summary_result or {}).get('detailed_summary', ''))}"
            )

        quiz_elapsed, quiz_result, quiz_error = await benchmark_case(
            "quiz_3q_topic",
            quiz_generator.generate_quiz(
                pdf_data.get("full_text", ""),
                num_questions=3,
                difficulty="medium",
                study_context=study_context,
                search_query=DEFAULT_TOPIC,
                pdf_identifier=pdf_key,
                question_types=["mcq"],
            ),
        )
        if quiz_error is None:
            quiz_runs.append(quiz_elapsed)
            print(f"  generated_questions={quiz_result.get('total_questions', 0)}")
        else:
            quiz_elapsed, quiz_result, quiz_error = await benchmark_case(
                "quiz_1q_topic_fallback",
                quiz_generator.generate_quiz(
                    pdf_data.get("full_text", ""),
                    num_questions=1,
                    difficulty="medium",
                    study_context=study_context,
                    search_query=DEFAULT_TOPIC,
                    pdf_identifier=pdf_key,
                    question_types=["mcq"],
                ),
            )
            if quiz_error is None:
                quiz_runs.append(quiz_elapsed)
                print(f"  generated_questions={quiz_result.get('total_questions', 0)}")

        qa_elapsed, qa_result, qa_error = await benchmark_case(
            "qa_answer",
            qa_system.answer_question(
                pdf_url=pdf_key,
                question=DEFAULT_QUESTION,
                conversation_history=[],
                full_text=pdf_data.get("full_text", ""),
                user_role="user",
                sections=pdf_data.get("sections", []),
                chunks=pdf_data.get("chunks", []),
            ),
        )
        if qa_error is None:
            qa_runs.append(qa_elapsed)
            print(
                f"  answer_chars={len((qa_result or {}).get('answer', ''))} "
                f"confidence={qa_result.get('confidence', 'unknown')}"
            )

    print("\nSummary")
    if summary_runs:
        print(f"  summary_both avg: {sum(summary_runs) / len(summary_runs):.2f}s")
    if quiz_runs:
        print(f"  quiz avg: {sum(quiz_runs) / len(quiz_runs):.2f}s")
    if qa_runs:
        print(f"  qa_answer avg: {sum(qa_runs) / len(qa_runs):.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
