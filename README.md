# School LLM

School LLM is a FastAPI + vanilla HTML/CSS/JavaScript application for studying PDFs with local AI.

## Current Product Scope

The app now focuses on these areas:

1. User authentication
2. Admin monitoring
3. PDF upload and processing
4. AI study tools for uploaded PDFs

Removed from the codebase:

1. Textbook/catalog APIs
2. Board/class/subject browsing flows
3. Web scraper modules and stale resource pages

## Features

### Student Features

- Upload a PDF after login
- Ask questions about the uploaded PDF
- Generate quizzes with difficulty selection
- Generate short, detailed, or combined summaries
- Convert summaries or custom text into audio
- Change password from the AI workspace

### Admin Features

- View all users
- View user activity logs
- View uploaded PDF history
- Activate or deactivate users

### Backend Features

- JWT authentication with bcrypt password hashing
- PDF text extraction with PyMuPDF / PyPDF2 fallback
- Token-aware PDF chunking
- ChromaDB vector search for PDF Q&A
- Ollama-based local LLM calls
- Local text-to-speech audio generation
- Video script generation endpoint

## Tech Stack

### Backend

- FastAPI
- MongoDB with Motor
- Ollama
- ChromaDB
- Sentence Transformers
- PyMuPDF / PyPDF2
- pyttsx3

### Frontend

- Plain HTML
- Plain CSS
- Plain JavaScript

## Pages

- `frontend/index.html`: Landing page
- `frontend/signup.html`: Sign up
- `frontend/login.html`: Login
- `frontend/ai-features.html`: Main student workspace
- `frontend/admin.html`: Admin dashboard

## API Overview

### Authentication

- `POST /api/auth/signup`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/change-password`

### Admin

- `GET /api/admin/users`
- `GET /api/admin/activity`
- `GET /api/admin/uploaded-pdfs`
- `PUT /api/admin/users/{user_id}/status`

### PDF + AI

- `POST /api/upload_pdf`
- `POST /api/ask`
- `POST /api/summarize`
- `POST /api/quiz`
- `POST /api/audio`
- `GET /api/audio/{filename}`
- `POST /api/video`

## Setup

### 1. Create a virtual environment

```bash
python -m venv venv
```

### 2. Activate it

On Windows:

```bash
venv\Scripts\activate
```

### 3. Install backend dependencies

```bash
cd backend
pip install -r requirements.txt
cd ..
```

### 4. Create `.env`

Example:

```env
MONGODB_URI=mongodb://localhost:27017/school_llm
JWT_SECRET_KEY=change-this-in-production
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.1:8b
LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### 5. Start the app

Backend:

```bash
cd backend
python main.py
```

Frontend:

```bash
cd frontend
python -m http.server 3000
```

Open:

- `http://localhost:3000/index.html`

Or use:

```bash
start.bat
```

## Suggested User Flow

1. Open `index.html`
2. Sign up or log in
3. If you are a student, go to `ai-features.html`
4. Upload a PDF
5. Ask questions, generate quizzes, summaries, or audio
6. If you are an admin, use `admin.html` to monitor users and uploads

## Project Structure

```text
school-llm/
├── backend/
│   ├── ai/
│   ├── auth.py
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── pdf_handler.py
│   ├── requirements.txt
│   └── vector_db.py
├── frontend/
│   ├── admin.html
│   ├── ai-features.html
│   ├── index.html
│   ├── login.html
│   └── signup.html
└── start.bat
```

## Notes

- The frontend should be served through `python -m http.server 3000`, not opened directly from disk.
- Ollama must be running for Q&A, quiz, summary, and video-script features.
- MongoDB must be available for authentication, admin data, and upload history.
