# School LLM — Next.js frontend

Next.js 16 web app for School LLM. Pairs with the FastAPI backend in
[`../backend/`](../backend/) over an httpOnly-cookie auth flow.

- **Stack:** Next.js 16 (App Router, TypeScript) · React 19 · Tailwind 4 ·
  Radix UI primitives · TanStack Query · sonner toasts · Web Speech API for
  voice chat
- **Auth:** JWT from FastAPI, kept in an **httpOnly cookie** set by `/api/login`
- **Theming:** four palettes (Cobalt, Midnight, Onyx, Sand) via CSS variables +
  `data-theme` on `<html>`; SSR reads the saved theme so there's no flash
- **Runs against:** FastAPI on `http://localhost:8000` (see `.env.local`)

## Feature coverage

| Area | Status |
|---|---|
| Landing page | ✅ |
| Login + Signup with strict role check | ✅ |
| Logout · theme switcher · change password | ✅ |
| Student Home (usage card · PDFs grid · upload · recent activity) | ✅ |
| Student Workspace — Q&A · Multi-Doc · Quiz · Summary · Audio · Video | ✅ |
| Student Assignments — list · take with OCR · auto-graded feedback | ✅ |
| Student History — Q&A · Quiz · Summary · Audio · Video | ✅ |
| Voice Chat in Audio tab (browser STT → Q&A → TTS) | ✅ |
| Active-quiz autosave + reload-restore | ✅ |
| Teacher dashboard — Home · My Assignments · New Assignment · My Students | ✅ |
| Grade override per question with teacher comment | ✅ |
| Question Paper builder (one rate-limit unit covers all sections) | ✅ |
| Admin — Analytics · Users · Permissions · Rate Limits · Activity · PDFs · Eval · Export | ✅ |
| Answer Evaluator modal (manual + batch paste) | ✅ |
| Notifications + chat — 15s polling | ✅ (WebSocket upgrade is future work) |
| Q&A streaming | ⏳ client-side fake stream today; SSE on the backend is future work |

## Architecture (one paragraph)

The browser never touches the FastAPI backend directly. It calls Next.js
Route Handlers under `/api/*`. The catch-all `/api/backend/[...path]` proxies
any backend call after attaching the JWT from the auth cookie. The dedicated
`/api/login`, `/api/signup`, `/api/logout`, `/api/me` handlers manage the
cookie lifecycle. `proxy.ts` (Next.js 16's renamed `middleware.ts`) redirects
unauthenticated visits to protected routes to `/login` before any RSC
rendering happens.

### Folder map

```
src/
  app/
    page.tsx                 landing (auto-redirects logged-in users)
    login/                   login + signup tabs
    student/                 home · workspace · assignments · history
    teacher/                 home · assignments · new-assignment · students
    admin/                   analytics · users · permissions · rate-limits ·
                             activity · pdfs · eval · export
    api/
      login/, signup/, logout/, me/   cookie-aware auth endpoints
      user/theme/                     PUT /api/auth/theme proxy
      backend/[...path]/              catch-all FastAPI proxy
  components/
    ui/                      Radix-based shadcn-style primitives
    dashboard/               sidebar · header · notifications · chat · usage
    admin/                   answer-evaluator (modal + trigger)
    theme-selector.tsx
    providers.tsx            React Query + Toaster
  lib/
    api.ts                   server-side fetch wrapper (backend bearer)
    auth.ts                  cookie helpers + requireRole()
    client-api.ts            browser-side typed API client
    themes.ts · types.ts · utils.ts
  proxy.ts                   Next.js 16 middleware (auth gate)
```

## Local development

### Backend

From the repo root, in PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --port 8000
```

### Frontend (this app)

```powershell
cd frontend_next
npm install     # first time only
npm run dev     # → http://localhost:3000
```

### Other scripts

```powershell
npm run build       # production build
npm start           # serve the build
npm run lint        # ESLint
npx tsc --noEmit    # type check only
```

## Environment

`.env.local` (gitignored):

```
BACKEND_URL=http://localhost:8000
COOKIE_SECURE=0          # set to "1" in production behind HTTPS
```

## Auth flow

1. User submits the login form (client component, vanilla fetch).
2. Browser → `POST /api/login` (Next.js Route Handler).
3. Handler → `POST {BACKEND_URL}/api/auth/login`. Backend returns a JWT.
4. Handler → `GET {BACKEND_URL}/api/auth/me` to validate, and double-checks the
   role matches what the user selected.
5. Handler sets `schoollm_token` cookie (`httpOnly`, `SameSite=Lax`, 1 year)
   and returns the user payload.
6. Client routes to `/student`, `/teacher`, or `/admin`.

For every subsequent browser request the cookie travels automatically; the
catch-all proxy attaches it as `Authorization: Bearer <jwt>` when calling
FastAPI.

## Why httpOnly cookie (vs. localStorage)

- XSS-proof: a malicious script on the page can't read the token.
- Survives full reloads without writing JS to rehydrate.
- Same-origin: works with `SameSite=Lax` without CORS preflights for the
  browser, and Next.js → FastAPI is server-to-server (no CORS at all).

## Theme system

Four palettes (`cobalt`, `midnight`, `onyx`, `sand`) live as `@theme inline`
tokens in `src/app/globals.css`. Switching theme sets `data-theme` on `<html>`
for instant feedback, then persists via `PUT /api/auth/theme` so the next
reload (and the next device) renders correctly from SSR. The root layout
reads the cookie's `theme` on the server so there's no flash of the wrong
palette.

## Voice Chat browser support

Voice Chat (Workspace → Audio → 🎙️ Voice Chat) uses the Web Speech API.
Works on Chrome, Edge, and Safari. Firefox doesn't ship `SpeechRecognition`;
the tab shows a fallback card directing users to the Narration sub-tab,
which works on every browser.

## Known follow-ups

- **Real streaming Q&A** — `/api/ask` currently returns the full answer as
  JSON; the Q&A tab fake-streams it word-by-word for visual cadence. Backend
  SSE on `/api/ask` would replace the fake stream with a real one.
- **WebSocket notifications + chat** — polling every 15s is fine for small
  classrooms; a WebSocket endpoint on the backend would lift the load and
  cut perceived latency.
- **ERP SSO** — the backend supports `AUTH_PROVIDER=eskoolia` to authenticate
  against the eskoolia ERP. The frontend treats those users transparently
  (their `auth_source` is `"eskoolia"`); a few local-only flows (signup,
  change-password, theme save) return 409 for ERP users and the UI surfaces
  that as a friendly message.
