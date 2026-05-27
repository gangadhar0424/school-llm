"""
API Client for School LLM Streamlit Frontend.
All calls to the FastAPI backend go through this module.
"""
import requests
from typing import Any, Dict, List, Optional

BASE_URL = "http://localhost:8000"
TIMEOUT = 120         # seconds — fast calls (auth, PDF list, admin)
AI_TIMEOUT = 600      # seconds — LLM calls (quiz, summary, Q&A, multi-doc) on local Ollama
VIDEO_TIMEOUT = 900   # seconds — video rendering (LLM + TTS + MoviePy encode)


class APIClient:
    """Thin wrapper around requests for calling the School LLM backend."""

    def __init__(self, token: str = None):
        self.token = token

    def _headers(self, extra: Dict = None) -> Dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def _handle(self, resp: requests.Response) -> Dict:
        if resp.status_code == 429:
            raise RuntimeError("Rate limit exceeded. Please wait a moment and try again.")
        if resp.status_code == 401:
            raise RuntimeError("Session expired. Please log in again.")
        if resp.status_code == 403:
            raise RuntimeError(resp.json().get("detail", "Access denied."))
        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"Server error {resp.status_code}: {resp.text[:200]}")
        if not resp.ok:
            raise RuntimeError(data.get("detail", f"Error {resp.status_code}"))
        return data

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self, email: str, password: str, role: str = "student") -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password, "role": role},
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def signup(
        self, email: str, username: str, password: str,
        full_name: str = "", role: str = "student",
        class_level: Optional[int] = None,
        section: Optional[str] = None,
        subjects_taught: Optional[List[str]] = None,
        assigned_classes: Optional[List[str]] = None,
    ) -> Dict:
        body = {
            "email": email, "username": username, "password": password,
            "full_name": full_name, "role": role,
        }
        if class_level is not None:
            body["class_level"] = int(class_level)
        if section:
            body["section"] = str(section).upper()
        if subjects_taught:
            body["subjects_taught"] = subjects_taught
        if assigned_classes:
            body["assigned_classes"] = assigned_classes
        resp = requests.post(
            f"{BASE_URL}/api/auth/signup",
            json=body,
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def admin_update_user_class(self, user_id: str, class_level: int, section: str) -> Dict:
        resp = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}/class",
            json={"class_level": int(class_level), "section": str(section).upper()},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def admin_assign_teacher(self, user_id: str, subjects_taught: List[str], assigned_classes: List[str]) -> Dict:
        resp = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}/teacher-assignments",
            json={
                "subjects_taught": subjects_taught,
                "assigned_classes": [c.strip().upper() for c in assigned_classes],
            },
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def admin_get_permissions(self) -> Dict:
        """Fetch the role-permissions matrix (defaults merged with overrides)."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/permissions",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def admin_set_permission(self, role: str, feature: str, enabled: bool) -> Dict:
        """Toggle a single permission for a role."""
        resp = requests.put(
            f"{BASE_URL}/api/admin/permissions",
            json={"role": role, "feature": feature, "enabled": bool(enabled)},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def admin_get_rate_limits(self) -> Dict:
        """Fetch the per-role per-feature daily rate-limit matrix (defaults
        merged with admin overrides). -1 = unlimited, 0 = disabled."""
        resp = requests.get(
            f"{BASE_URL}/api/admin/rate-limits",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def admin_update_rate_limits(self, roles: Dict[str, Dict[str, int]]) -> Dict:
        """Replace the rate-limit matrix. `roles` is shaped like
        {'student': {'qa': 50, 'quiz': 10, ...}, 'teacher': {...}, 'admin': {...}}."""
        resp = requests.put(
            f"{BASE_URL}/api/admin/rate-limits",
            json={"roles": roles},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def admin_get_teachers_for_class(self, class_section: str, subject: Optional[str] = None) -> Dict:
        params = {"class_section": class_section}
        if subject:
            params["subject"] = subject
        resp = requests.get(
            f"{BASE_URL}/api/admin/teachers-for-class",
            params=params,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_grading_standards(self) -> Dict:
        """Return the configured grading bands + subject overlays (Phase 2/6)."""
        resp = requests.get(
            f"{BASE_URL}/api/grading-standards",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def reload_grading_standards(self) -> Dict:
        """Re-read backend grading_standards.json without restarting the server."""
        resp = requests.post(
            f"{BASE_URL}/api/admin/grading-standards/reload",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_me(self) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def change_password(self, old_password: str, new_password: str) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/auth/change-password",
            json={"old_password": old_password, "new_password": new_password},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    # ── PDF Management ────────────────────────────────────────────────────────

    def upload_pdf(self, file_bytes: bytes, filename: str) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/upload_pdf",
            files={"file": (filename, file_bytes, "application/pdf")},
            headers={"Authorization": f"Bearer {self.token}"} if self.token else {},
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_my_pdfs(self, limit: int = 100) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/my-uploaded-pdfs",
            params={"limit": limit},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def delete_pdf(self, pdf_id: str) -> Dict:
        resp = requests.delete(
            f"{BASE_URL}/api/my-uploaded-pdfs/{pdf_id}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    # ── Onboarding + progress ─────────────────────────────────────────────────

    def complete_onboarding(self) -> Dict:
        """Mark the current user's onboarding as complete (persists in MongoDB)."""
        resp = requests.put(
            f"{BASE_URL}/api/auth/complete-onboarding",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def update_theme(self, theme: str) -> Dict:
        """Update the user's selected color theme (persists in MongoDB)."""
        resp = requests.put(
            f"{BASE_URL}/api/auth/theme",
            json={"theme": theme},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_student_progress(self) -> Dict:
        """Aggregate dashboard data: features used, streak, recent PDFs, pending assignments."""
        resp = requests.get(
            f"{BASE_URL}/api/student/progress",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    # ── AI Features ───────────────────────────────────────────────────────────

    def ask_question(
        self,
        pdf_identifier: str,
        question: str,
        conversation_history: List[Dict] = None,
        session_id: str = None,
    ) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/ask",
            json={
                "pdf_url": pdf_identifier,
                "question": question,
                "conversation_history": conversation_history or [],
                "session_id": session_id,
            },
            headers=self._headers(),
            timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def ask_question_multi(
        self,
        pdf_identifiers: List[str],
        question: str,
        conversation_history: List[Dict] = None,
        session_id: str = None,
    ) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/ask-multi",
            json={
                "pdf_identifiers": pdf_identifiers,
                "question": question,
                "conversation_history": conversation_history or [],
                "session_id": session_id,
            },
            headers=self._headers(),
            timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    # ── Chat Sessions (ChatGPT-style persistent conversations) ───────────────

    def create_chat_session(
        self,
        pdf_ids: List[str] = None,
        mode: str = "single",
        name: str = "New chat",
    ) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/chat-sessions",
            json={"pdf_ids": pdf_ids or [], "mode": mode, "name": name},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def list_chat_sessions(self, mode: str = None) -> Dict:
        params = {"mode": mode} if mode else {}
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            params=params,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_chat_session(self, session_id: str) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions/{session_id}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def rename_chat_session(self, session_id: str, name: str) -> Dict:
        resp = requests.patch(
            f"{BASE_URL}/api/chat-sessions/{session_id}",
            json={"name": name},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def delete_chat_session(self, session_id: str) -> Dict:
        resp = requests.delete(
            f"{BASE_URL}/api/chat-sessions/{session_id}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def generate_quiz(
        self,
        pdf_identifier: str,
        num_questions: int = 5,
        difficulty: str = "medium",
        question_type: str = "mcq",
        search_query: str = None,
        target_class: Optional[int] = None,
        subject: Optional[str] = None,
    ) -> Dict:
        body: Dict[str, Any] = {
            "pdf_url": pdf_identifier,
            "num_questions": num_questions,
            "difficulty": difficulty,
            "question_types": [question_type],
            "search_query": search_query or None,
        }
        if target_class is not None:
            body["target_class"] = int(target_class)
        if subject:
            body["subject"] = subject
        resp = requests.post(
            f"{BASE_URL}/api/quiz",
            json=body,
            headers=self._headers(),
            timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def save_active_quiz(
        self,
        pdf_id: str,
        questions: List[Dict],
        question_type: str = "mcq",
        difficulty: str = "basic",
        answers: Optional[Dict] = None,
    ) -> Dict:
        """Persist an in-progress quiz so a browser reload doesn't lose it."""
        resp = requests.post(
            f"{BASE_URL}/api/quiz/active",
            json={
                "pdf_id": pdf_id,
                "questions": questions,
                "question_type": question_type,
                "difficulty": difficulty,
                "answers": answers or {},
            },
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_active_quiz(self, pdf_id: str) -> Optional[Dict]:
        """Fetch the student's saved quiz for this PDF, or None if there
        isn't one. Returns None on 404 instead of raising."""
        resp = requests.get(
            f"{BASE_URL}/api/quiz/active/{pdf_id}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        return self._handle(resp)

    def discard_active_quiz(self, pdf_id: str) -> Dict:
        """Delete the saved active quiz (called on submit or 'Restart')."""
        resp = requests.delete(
            f"{BASE_URL}/api/quiz/active/{pdf_id}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    # ── Quiz attempts & student history ──────────────────────────────────────
    def save_quiz_attempt(
        self,
        pdf_id: str,
        questions: List[Dict],
        answers: Dict,
        score: int,
        total: int,
        question_type: str = "mcq",
        difficulty: str = "basic",
    ) -> Dict:
        """Persist a completed quiz attempt so it appears in the History tab."""
        resp = requests.post(
            f"{BASE_URL}/api/student/quiz-attempt",
            json={
                "pdf_id": pdf_id,
                "questions": questions,
                "answers": answers,
                "score": score,
                "total": total,
                "question_type": question_type,
                "difficulty": difficulty,
            },
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def student_history_qa(self, limit: int = 50) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/history/qa",
            params={"limit": limit}, headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def student_history_quizzes(self, limit: int = 50) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/history/quizzes",
            params={"limit": limit}, headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def student_history_summaries(self, limit: int = 50) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/history/summaries",
            params={"limit": limit}, headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def student_history_audio(self, limit: int = 50) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/history/audio",
            params={"limit": limit}, headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def student_history_video(self, limit: int = 50) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/history/video",
            params={"limit": limit}, headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def generate_summary(
        self,
        pdf_identifier: str,
        summary_type: str = "both",
        topic: str = None,
    ) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/summarize",
            json={
                "pdf_url": pdf_identifier,
                "summary_type": summary_type,
                "topic": topic or None,
            },
            headers=self._headers(),
            timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def generate_audio(self, text: str, pdf_identifier: str = None) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/audio",
            json={"text": text, "pdf_url": pdf_identifier},
            headers=self._headers(),
            timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def generate_video(self, summary: str = None, pdf_identifier: str = None,
                       query: str = None, style: str = "slides") -> Dict:
        payload: Dict[str, Any] = {"style": style}
        if summary:
            payload["summary"] = summary
        if pdf_identifier:
            payload["pdf_url"] = pdf_identifier
        if query:
            payload["query"] = query
        resp = requests.post(
            f"{BASE_URL}/api/video",
            json=payload,
            headers=self._headers(),
            timeout=VIDEO_TIMEOUT,
        )
        return self._handle(resp)

    def get_video_url(self, filename: str) -> str:
        return f"{BASE_URL}/api/video/{filename}"

    # ── Answer Evaluation (admin only) ──────────────────────────────────────

    def evaluate_answer(
        self,
        student_answer: str,
        question: str = "",
        expected_answer: str = "",
        keywords: List[str] = None,
        student_class: Optional[int] = None,
        target_class: Optional[int] = None,
        subject: Optional[str] = None,
    ) -> Dict:
        body: Dict[str, Any] = {
            "student_answer": student_answer,
            "question": question or "",
            "expected_answer": expected_answer or "",
            "keywords": keywords or [],
        }
        if student_class is not None:
            body["student_class"] = int(student_class)
        if target_class is not None:
            body["target_class"] = int(target_class)
        if subject:
            body["subject"] = subject
        resp = requests.post(
            f"{BASE_URL}/api/evaluate-answer",
            json=body,
            headers=self._headers(),
            timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def parse_questions(self, copyable_text: str) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/parse-questions",
            json={"copyable_text": copyable_text},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def extract_text_from_upload(self, file_bytes: bytes, filename: str) -> Dict:
        """Upload a PDF or image; backend returns extracted text."""
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        resp = requests.post(
            f"{BASE_URL}/api/extract-text",
            files={"file": (filename, file_bytes)},
            headers=headers,
            timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def get_audio_url(self, filename: str) -> str:
        return f"{BASE_URL}/api/audio/{filename}"

    # ── Chat History ──────────────────────────────────────────────────────────

    def save_chat_message(
        self,
        document_ids: List[str],
        question: str,
        answer: str,
        sources: List[str] = None,
        confidence: str = "medium",
    ) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/chat-history",
            json={
                "document_ids": document_ids,
                "question": question,
                "answer": answer,
                "sources": sources or [],
                "confidence": confidence,
            },
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_chat_history(self, document_id: str = None, limit: int = 50) -> Dict:
        params = {"limit": limit}
        if document_id:
            params["document_id"] = document_id
        resp = requests.get(
            f"{BASE_URL}/api/chat-history",
            params=params,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def clear_chat_history(self, document_id: str = None) -> Dict:
        params = {}
        if document_id:
            params["document_id"] = document_id
        resp = requests.delete(
            f"{BASE_URL}/api/chat-history",
            params=params,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    # ── Admin: AI evaluation ──────────────────────────────────────────────────
    def admin_eval_run_on_qa(
        self,
        label: Optional[str] = None,
        limit: Optional[int] = None,
        user_email: Optional[str] = None,
    ) -> Dict:
        """Reference-free evaluation on REAL student Q&A traffic. Pulls
        the most recent N (question, AI answer) turns from chat_sessions
        and scores each on faithfulness + answer relevance."""
        body: Dict = {}
        if label:
            body["label"] = label
        if limit:
            body["limit"] = limit
        if user_email:
            body["user_email"] = user_email
        resp = requests.post(
            f"{BASE_URL}/api/admin/eval/run-on-qa",
            json=body,
            headers=self._headers(),
            timeout=1800,
        )
        return self._handle(resp)

    def admin_eval_run_student_bundle(
        self, label: Optional[str] = None, limit: Optional[int] = None,
    ) -> Dict:
        """One-shot student-side evaluation: runs Q&A + Summaries + Quizzes
        sequentially and returns a combined bundle summary. Skips sub-evals
        that have no data yet rather than failing the whole bundle."""
        body: Dict = {}
        if label:
            body["label"] = label
        if limit:
            body["limit"] = limit
        resp = requests.post(
            f"{BASE_URL}/api/admin/eval/run-student-bundle",
            json=body, headers=self._headers(), timeout=3600,  # 1hr — runs 3 sub-evals
        )
        return self._handle(resp)

    def admin_eval_run_on_summaries(
        self, label: Optional[str] = None, limit: Optional[int] = None,
    ) -> Dict:
        body: Dict = {}
        if label:
            body["label"] = label
        if limit:
            body["limit"] = limit
        resp = requests.post(
            f"{BASE_URL}/api/admin/eval/run-on-summaries",
            json=body, headers=self._headers(), timeout=1800,
        )
        return self._handle(resp)

    def admin_eval_run_on_quizzes(
        self, label: Optional[str] = None, limit: Optional[int] = None,
    ) -> Dict:
        body: Dict = {}
        if label:
            body["label"] = label
        if limit:
            body["limit"] = limit
        resp = requests.post(
            f"{BASE_URL}/api/admin/eval/run-on-quizzes",
            json=body, headers=self._headers(), timeout=1800,
        )
        return self._handle(resp)

    def admin_eval_run_on_teacher_questions(
        self, label: Optional[str] = None, limit: Optional[int] = None,
    ) -> Dict:
        body: Dict = {}
        if label:
            body["label"] = label
        if limit:
            body["limit"] = limit
        resp = requests.post(
            f"{BASE_URL}/api/admin/eval/run-on-teacher-questions",
            json=body, headers=self._headers(), timeout=1800,
        )
        return self._handle(resp)

    def admin_eval_list_runs(self, limit: int = 30) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/admin/eval/runs",
            params={"limit": limit},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def admin_eval_get_run(self, run_id: str) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/admin/eval/runs/{run_id}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    # ── Admin ─────────────────────────────────────────────────────────────────

    def get_all_users(self) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def update_user_status(self, user_id: str, is_active: bool) -> Dict:
        resp = requests.put(
            f"{BASE_URL}/api/admin/users/{user_id}/status",
            json={"is_active": is_active},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_analytics(self) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/admin/analytics",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_activity_logs(self, user_email: str = None, limit: int = 100) -> Dict:
        params = {"limit": limit}
        if user_email:
            params["user_email"] = user_email
        resp = requests.get(
            f"{BASE_URL}/api/admin/activity",
            params=params,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def get_all_uploaded_pdfs(self, limit: int = 100) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/admin/uploaded-pdfs",
            params={"limit": limit},
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        return self._handle(resp)

    def export_logs_csv(
        self,
        user_email: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> bytes:
        params = {}
        if user_email:
            params["user_email"] = user_email
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        resp = requests.get(
            f"{BASE_URL}/api/admin/export-logs",
            params=params,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        if not resp.ok:
            raise RuntimeError(f"Export failed: {resp.status_code}")
        return resp.content

    # ── Teacher endpoints (assignments + class students) ──────────────────────

    def teacher_list_students(self) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/teacher/students",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def teacher_student_submissions(self, student_id: str) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/teacher/students/{student_id}/submissions",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def teacher_get_submission(self, submission_id: str) -> Dict:
        """Get detailed submission info including grading breakdown."""
        resp = requests.get(
            f"{BASE_URL}/api/teacher/submissions/{submission_id}",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def teacher_create_assignment(self, body: Dict) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/teacher/assignments",
            json=body, headers=self._headers(), timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def teacher_list_assignments(self) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/teacher/assignments",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def teacher_get_assignment(self, assignment_id: str) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/teacher/assignments/{assignment_id}",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def teacher_update_assignment(self, assignment_id: str, body: Dict) -> Dict:
        resp = requests.put(
            f"{BASE_URL}/api/teacher/assignments/{assignment_id}",
            json=body, headers=self._headers(), timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def teacher_delete_assignment(self, assignment_id: str) -> Dict:
        resp = requests.delete(
            f"{BASE_URL}/api/teacher/assignments/{assignment_id}",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def teacher_override_grade(
        self, submission_id: str, question_index: int,
        score: float, comment: str = "",
    ) -> Dict:
        resp = requests.put(
            f"{BASE_URL}/api/teacher/submissions/{submission_id}/override",
            json={"question_index": int(question_index), "score": float(score), "comment": comment or ""},
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    # ── Student assignment endpoints ──────────────────────────────────────────

    def student_list_assignments(self) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/assignments",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def student_get_assignment(self, assignment_id: str) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/assignments/{assignment_id}",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def student_submit_assignment(self, assignment_id: str, answers: List[Dict]) -> Dict:
        resp = requests.post(
            f"{BASE_URL}/api/student/assignments/{assignment_id}/submit",
            json={"answers": answers},
            headers=self._headers(), timeout=AI_TIMEOUT,
        )
        return self._handle(resp)

    def student_list_submissions(self) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/submissions",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)

    def student_get_submission(self, submission_id: str) -> Dict:
        resp = requests.get(
            f"{BASE_URL}/api/student/submissions/{submission_id}",
            headers=self._headers(), timeout=TIMEOUT,
        )
        return self._handle(resp)
