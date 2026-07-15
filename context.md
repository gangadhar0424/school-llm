# School LLM Context Log

This file records the user prompts, assistant responses, and progress updates for this workspace. It is meant to be append-only and should preserve the conversation history in a compact form.

## Entry Template

- Date:
- User prompt:
- Assistant response summary:
- Progress updates made while working:
- Files changed:
- Validation performed:
- Follow-up notes:

## 2026-06-16

### User Prompt 1

"go through entire project read each file of code and understand each functionality and workflow and then create me memory.md file that stores the chats we have and the upgradations we make. if a new ai model reads this file the model should be able to know what was done what is running in the application and in future what we may do. these all details should be in that and another file like context.md which should store the prompts i give and what answer and updates it gave"

### Assistant Response Summary

I reviewed the repository docs and the main backend/frontend entrypoints, then summarized the active application architecture and runtime workflow.

Key findings captured for the new docs:

- School LLM is a FastAPI backend plus a Next.js 16 frontend.
- The browser talks to FastAPI only through Next.js route handlers and an httpOnly-cookie auth flow.
- The runtime data lives under `runtime_data/` for ChromaDB, uploaded PDFs, generated audio, and generated videos.
- The current production-hardening focus is administrator-controlled daily rate limiting.
- The repo has a few doc/code mismatches, so the new memory file explicitly notes them for future edits.

### Progress Updates Made While Working

- Confirmed there was no existing workspace memory to reuse.
- Read the top-level README, status report, frontend README, frontend proxy, backend config, backend main entrypoint, and the rate-limit module.
- Used a repo exploration pass to summarize the cross-role workflows and startup services.
- Captured the current app flow, running services, and future work in the new documentation files.

### Files Changed

- `memory.md`
- `context.md`

### Validation Performed

- Reviewed the generated content against the current repo documentation and code structure.

### Follow-up Notes

- Future prompts and responses should be appended here in dated sections.
- If the backend or frontend architecture changes, update `memory.md` first, then record the change here.

### User Prompt 2

"ERP sends data about what plan did the school bought that data should be shown in super and also admin."

### Assistant Response Summary

I traced the ERP-to-app school metadata path and added a `school_plan` field to the mirrored ERP context.

The backend now:

- extracts the plan from likely ERP payload keys,
- stores it on mirrored user documents and school registry documents,
- exposes it through the existing admin and super-admin school payloads.

The frontend now:

- shows the plan in the admin school header/card,
- shows the plan in the super-admin school list,
- shows the plan badge on the super-admin school detail page.

### Progress Updates Made While Working

- Confirmed the app already mirrored school name and school ID, so the new field could ride the same path.
- Updated the ERP auth parser, mirrored user record, school registry, and route payloads.
- Added frontend types and UI copy for admin and super-admin school screens.
- Ran a targeted error sweep over every touched file; no errors were reported.

### Files Changed

- `backend/auth_context.py`
- `backend/auth_backend.py`
- `backend/database.py`
- `backend/main.py`
- `backend/routes/super_admin.py`
- `frontend_next/src/lib/types.ts`
- `frontend_next/src/app/admin/school/page.tsx`
- `frontend_next/src/app/admin/school/school-client.tsx`
- `frontend_next/src/app/super-admin/schools/schools-client.tsx`
- `frontend_next/src/app/super-admin/schools/[schoolId]/school-detail-client.tsx`

### Validation Performed

- `get_errors` on all touched backend and frontend files returned no errors.