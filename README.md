# School LLM

AI-powered learning platform for studying PDFs with local LLMs. Students upload
their textbooks and chapter notes; teachers build and grade assignments; admins
manage the roster, permissions, and per-feature rate limits.

- **Backend:** FastAPI · MongoDB · ChromaDB · Ollama (default) with Anthropic
  Claude as a configurable fallback · Sentence Transformers for embeddings ·
  PyMuPDF for PDF text extraction · pyttsx3 for narration · MoviePy for video
- **Frontend:** Next.js 16 (App Router) · React 19 · TypeScript · Tailwind 4 ·
  Radix UI primitives · TanStack Query
- **Auth:** JWT issued by FastAPI, stored as an httpOnly cookie by the Next.js
  proxy layer

## Roles & features

### Student

- Upload PDFs and run AI tools against them: Q&A (single doc + multi-doc),
  quiz generator (MCQ / true-false / fill-in / short / long), summaries,
  text-to-speech narration, voice chat (browser STT → Q&A → TTS), animated
  videos
- Attempt teacher assignments with handwritten-answer OCR upload
- Browse history of every Q&A session, quiz attempt, summary, audio, and video

### Teacher

- Build assignments by hand or generate them with AI from any uploaded PDF
- Mix question types in one assignment via the "Question Paper" generator
  (single rate-limited call instead of one per section)
- View student submissions, override AI grades per question, leave comments

### Admin

- System-wide analytics + activity logs (with CSV export)
- User management, role + class/section assignment
- Per-role / per-feature permissions matrix
- Per-role / per-feature daily rate limits (-1 = unlimited, 0 = disabled)
- In-app **Answer Evaluator** for testing the grading rubric on arbitrary
  question + student-answer pairs
- AI Evaluation runs (Q&A, summaries, quizzes, teacher questions) with
  faithfulness + relevance scoring

## Repo layout

```text
school-llm/
├── backend/                FastAPI app
│   ├── ai/                 Q&A, quiz, summary, audio, video, ollama_client
│   ├── middleware/         rate_limiter, llm_gate
│   ├── routes/, services/, evaluation/
│   ├── main.py             routes + lifespan + CORS
│   ├── auth.py, auth_backend.py, auth_context.py
│   ├── config.py, database.py, rate_limiting.py
│   └── requirements.txt
├── frontend_next/          Next.js 16 frontend (see its own README)
├── venv/                   Python virtualenv (gitignored)
├── .env                    backend secrets (gitignored)
└── README.md
```

## Setup

### 1. Python virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

### 2. Create `.env` in the repo root

```env
MONGODB_URI=mongodb://localhost:27017/school_llm
JWT_SECRET_KEY=change-this-in-production

# LLM provider chain — Ollama first, optional Claude fallback
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen2.5:3b
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

### 3. Node toolchain for the frontend

Node 22 LTS. Install dependencies:

```powershell
cd frontend_next
npm install
```

### 4. Optional `.env.local` for the frontend

```powershell
# frontend_next/.env.local
BACKEND_URL=http://localhost:8000
COOKIE_SECURE=0      # set to 1 in production behind HTTPS
```

## Run

Two terminals:

```powershell
# Terminal 1 — backend
cd C:\Users\ganga\Desktop\school-llm
.\venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --port 8000
```

```powershell
# Terminal 2 — frontend
cd C:\Users\ganga\Desktop\school-llm\frontend_next
npm run dev
```

Open **http://localhost:3000** and log in (or sign up).

FastAPI auto-docs are at **http://localhost:8000/docs**.

## Architecture (one paragraph)

The browser only ever talks to the Next.js dev server. Next.js Route Handlers
under `/api/*` proxy to FastAPI server-side, attaching the JWT from an
httpOnly cookie. The catch-all proxy at `/api/backend/[...path]` covers every
backend endpoint with one handler. `proxy.ts` (Next.js 16's renamed
`middleware.ts`) bounces unauthenticated visits to protected `/student`,
`/teacher`, or `/admin` routes back to `/login` before any RSC rendering.
The result: zero CORS, no token in localStorage, single-source-of-truth auth.

## Operational notes

- Ollama must be running for Q&A / quiz / summary / video. If Ollama is down
  and `ANTHROPIC_API_KEY` is set, the backend falls back to Claude.
- MongoDB must be reachable for auth, assignments, history, and rate-limit
  counters.
- Audio + video files are served back through `/api/backend/audio/{name}` and
  `/api/backend/video/{name}` so the cookie travels — no separate auth needed
  on the file URLs.
