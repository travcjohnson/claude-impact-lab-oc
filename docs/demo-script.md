# Local rehearsal script (BE-06)

Everything below runs from a clean checkout with no key and no model. A secret, if you later add one, goes in the environment (see `.env.example`), never in Git. Use **synthetic or event-permitted** PDFs only.

## Start
```bash
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install -r backend/requirements-dev.txt
npm --prefix frontend run build
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
```
Open http://127.0.0.1:8000/ , select **Review packet**, choose a PDF, press **Extract text with local backend**, save a page note, record a next step.

## What works today
Upload, text/OCR with original page numbers and per-page flags, search, page notes, next-step confirmation, unsent draft. The local browser also supports draft-contract field review, allowed-action reasons and reviewed export when analysis produces fields. Timing events and summary remain API-only (see `docs/backend-review-contract.md`).

## What is mocked or missing
No model analysis runs unless an adapter is configured (`IHH_ANALYSIS_ADAPTER`), and that has never been exercised against a real model. The local field-review browser workflow has been verified with a synthetic analysis adapter; this does not validate model extraction. History and timing are in server memory and vanish on restart. No authentication. Approval and denial are disabled.

## Timing a rehearsal
```bash
curl -s -X POST localhost:8000/api/referrals/$ID/timing -H 'content-type: application/json' -d '{"event":"pause","reason":"coordinator-break"}'
curl -s -X POST localhost:8000/api/referrals/$ID/timing -H 'content-type: application/json' -d '{"event":"resume"}'
curl -s localhost:8000/api/referrals/$ID/timing
curl -s localhost:8000/api/timing/summary
```
Use `wait_start` / `wait_end` (reason `hospital` or `authorization`) for time spent waiting on others. Record the manual baseline for the same packet separately; a rehearsal on a synthetic packet says nothing about real time saved.

## Regression walkthrough
`python3 -m unittest discover -s backend/tests -v` includes the end-to-end test: upload → analysis (synthetic fake) → every cited page opens and contains its quote → page note → corrections → pause/resume → confirmation (repeat is idempotent) → unsent export → a later correction invalidates the confirmation, draft and export.

## Public presentation: short walkthrough

1. Hospital role: select the synthetic example, inspect missing versus redacted items, acknowledge the gaps and simulate submission.
2. IHH role: open DEMO-004 in the inbox and request clarification.
3. Hospital role: answer or attach the synthetic note.
4. IHH role: inspect the response, record human review and download the mock CRM handoff.
5. Use DEMO-001 for linked evidence and inline field review. Explain that the public workflow is synthetic; real text extraction and server field review run locally.

The two-hour clock is a provisional demo target. Source information conflicts about whether two hours is the baseline or target; do not claim achieved time savings. Keep a local rehearsal available as a fallback. Public queue state resets on refresh.

## Final delivery checks

- Integrate Neetal's final frontend changes when available, then repeat the mobile/keyboard and end-to-end walkthrough on that exact deployed version.
- Review and merge the integration PR into main; deployment currently follows codex/frontend-live, so a live site alone does not mean main contains the final work.
- Real-model extraction remains unvalidated. If demonstrating it, verify the configured model and use permitted inputs; otherwise explicitly demonstrate the synthetic adapter/local OCR paths.
- Compare closed implementation PRs with issue acceptance criteria before closing tickets. Implementation merges do not prove real-model validation, measured time savings or production readiness.
- Public navigation and deployment exclude the internal team board. GitHub Issues/Projects remains the team tracker.

The app now starts on a dedicated Referral inbox screen. **Review packet** opens or resumes the separate packet workspace. Sidebar selection and breadcrumbs follow the current screen; returning through DEMO-001 preserves its review state. New responses sort ahead of waiting requests even when another request remains unanswered.

## Walkthrough and continuity

- Use **Take a tour** for role-specific guidance; Escape or Skip / close returns to
  the current work without changing it.
- Open DEMO-001 from the inbox. In **Continue onboarding**, change a proposed
  coordination step and explicitly save demo progress on this device.
- Refresh and reopen DEMO-001 to demonstrate the retained checklist and historical
  clarification snapshot. Switch to Person receiving care for a simpler checklist.
- Explain the boundary: browser-only demo metadata, no retained uploaded packet or
  clinical record, no cross-device sharing. Clearing saved progress resets it.
