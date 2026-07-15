# School LLM Memory

This file is the long-lived project memory for future models and future work in this workspace. It should answer four questions quickly:

1. What does the application do?
2. What is currently running and how does it work?
3. What changes have been made recently?
4. What should be done next?

## 1. Project Overview

School LLM is an AI-powered learning platform for school workflows. The application is organized around three roles:

- Student: uploads PDFs, asks grounded questions, generates quizzes and summaries, creates narration audio and videos, attempts assignments, and reviews history.
- Teacher: creates assignments manually or with AI, reviews submissions, overrides grades, and leaves comments.
- Admin or super admin: manages users, permissions, analytics, activity logs, rate limits, and AI evaluation workflows.

The backend is a FastAPI service. The frontend is a Next.js 16 App Router application with React 19 and TypeScript. The browser does not call FastAPI directly; requests flow through Next.js route handlers that attach auth cookies or bearer tokens server-side.

## 2. Current Runtime Workflow

The current application flow is:

1. User opens the Next.js frontend.
2. Protected routes are gated by `frontend_next/src/proxy.ts` before page rendering.
3. Login and signup are handled through Next.js route handlers that talk to the FastAPI backend.
4. The backend issues and validates JWT-based sessions, with the token kept in an httpOnly cookie on the frontend side.
5. The frontend proxy layer forwards authenticated calls to FastAPI.
6. The backend routes requests to PDF handling, retrieval, LLM generation, grading, audio, video, notifications, and admin workflows.

The backend startup path in `backend/main.py` performs configuration validation, connects to MongoDB, warms Ollama in the background, and prepares the API lifespan.

## 3. Major Backend Services

The main runtime services are:

- `backend/ai/qa.py`: retrieval-augmented question answering over uploaded PDFs.
- `backend/ai/quiz.py`: quiz generation and grading support.
- `backend/ai/summary.py`: document summarization.
- `backend/ai/audio.py`: text-to-speech narration.
- `backend/ai/video.py`: slide-style video generation.
- `backend/ai/llm_client.py`: provider abstraction and fallback handling.
- `backend/rate_limiting.py`: per-day feature quotas managed from the admin surface.
- `backend/middleware/rate_limiter.py`: per-minute anti-burst protection.
- `backend/services/realtime.py`: chat and notification emission.
- `backend/pdf_handler.py`: PDF upload, extraction, and processing.
- `backend/vector_db.py`: ChromaDB-backed vector storage.

The runtime data lives in `runtime_data/`:

- `runtime_data/chroma_db/`: persisted vector database.
- `runtime_data/uploads/`: uploaded source PDFs.
- `runtime_data/generated_audio/`: generated narration files.
- `runtime_data/generated_videos/`: generated video assets and temporary working files.

## 4. Current Frontend Workflow

The frontend is a Next.js 16 application with these active patterns:

- Auth is stored in an httpOnly cookie rather than localStorage.
- `frontend_next/src/proxy.ts` redirects unauthenticated users away from protected routes.
- Route handlers under `frontend_next/src/app/api/` proxy backend requests.
- UI sections exist for student, teacher, and admin dashboards.
- Themes are persisted through CSS variables and server-side rendering to avoid flash-of-unstyled state.

The frontend README lists the current major capabilities as complete, including login/signup, student workspace tools, teacher assignment workflows, admin panels, and polling-based notifications/chat.

## 5. Current Sprint and Active Work

The active production-hardening work focuses on rate limiting.

Current state:

- Daily per-role/per-feature quotas are implemented in the backend.
- The admin UI exposes rate-limit management.
- AI endpoints are wired to enforce quota checks.
- Per-minute anti-burst limits are still active as a separate layer.

The immediate next validation item is the end-to-end flow where an admin sets a quota, a student consumes it, and the backend returns HTTP 429 after the limit is exceeded.

## 6. Future Work

Likely next steps from the existing docs and codebase are:

- Finish end-to-end and load testing for the rate-limit implementation.
- Add broader unit and integration coverage for auth, rate limiting, and AI orchestration.
- Harden security around uploads, auth, and token handling.
- Continue refining the evaluation pipeline for question answering, summaries, and quizzes.
- Replace polling and fake-stream behaviors with true backend streaming and WebSockets where appropriate.

## 7. Important Notes For Future Models

- The repo contains some older status text that still references Streamlit. The current frontend code and README are Next.js-based.
- `backend/config.py` supports both local and ERP-style auth flows, and the default environment values may not match the older README examples.
- `backend/main.py` inserts `backend/` into `sys.path` so bare imports work when running from the repo root.
- Some code comments and docs are more current than the older status reports. Prefer live code and the newer README files when there is a conflict.

## 8. Change Log

- 2026-06-16: Created this memory file and the companion `context.md` file to capture project knowledge, workflow, and conversation history.
- 2026-06-16: Added ERP school-plan mirroring. The backend now stores `school_plan` on the mirrored user and school documents, and the admin / super-admin school views display it.

## 9. How To Use This File

When the project changes, append a short dated note here with:

- what was changed,
- what workflow or behavior changed,
- what still needs verification,
- and any new follow-up work.

Keep entries short, factual, and current.