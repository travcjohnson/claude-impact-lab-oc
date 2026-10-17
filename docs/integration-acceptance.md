# Integration acceptance — Team 1

Use this checklist when Harjeev and Vibhu push their implementations. It is a test plan, not a claim that missing clinical functionality is complete. Record the tested commit, browser, backend configuration (no secret values), synthetic versus real data, results and remaining failures in the PR.

## Before integration

- Confirm feature branches include the current `codex/frontend-live` implementation. Preserve local work; no reset or force-push.
- Harjeev supplies BE-03 schema/version and a synthetic fixture with field IDs, original-page evidence, uncertainty states and coverage. Vibhu supplies review/error/draft shapes and revision semantics. The frontend owner implements one adapter.
- Compare changed functions in `backend/app.py` before merging. Natal owns styles/index; coordinate any markup selectors with her.
- Review pending backend findings: short-native-text preservation when OCR fails; request access boundaries; search terms in access logs; backend browser binary configuration. See `docs/pr-review-triage.md`.

## Current runnable checks

From the repository root, with prerequisites in frontend/README.md and backend/README.md:

```bash
npm --prefix frontend test
npm --prefix frontend run build
python3 -m unittest discover -s backend/tests -v
```

Serve `frontend/dist` on a loopback port for the static browser checks; set `FRONTEND_URL` to that internal server. Run `frontend/tests/browser.cjs` and `frontend/tests/field-review-browser.cjs` with Node. For local API tests, run the backend on loopback port 8000 with access logging disabled (`python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log`). Then run:

```bash
node frontend/tests/backend-recovery-browser.cjs
node frontend/tests/processing-browser.cjs
node backend/tests/browser.cjs
```

The first two mock API responses with synthetic data to test failures; they do not establish extraction accuracy. The last uses the real local backend and the public blank form. No event packet content belongs in committed tests, screenshots or logs.

## Real-field integration gates — pending backend contract

| Scenario | Required observable behavior |
|---|---|
| One valid packet | Actual job state leads to that packet's fields, never demo fallback. Each citation opens its original page. |
| Partial OCR | Failed/unreadable page remains at its original number; usable pages remain accessible. Search absence is not evidence absence. |
| Missing/redacted/conflicting evidence | Distinct visible states persist through review and export; uncertainty cannot silently become an eligibility pass/fail. |
| Malformed model/schema output | Bounded retry or actionable error; no fabricated field, source, rule ID or successful analysis. |
| Correction | Original extraction retained; changed value, reviewer, rationale and revision captured. Repeated correction needs an explanation for that change. |
| Concurrent review / 409 | Local edits retained; show current server state for comparison. No blind retry overwrites another review. |
| Confirmation retry | Backend idempotency checked separately from client double-click suppression. Timeout after acceptance must not duplicate a decision. |
| Export | Current server-confirmed snapshot, evidence and unresolved items; stale output blocked. Edited unsent text distinguishable from confirmed source record. |
| Navigation / interruption | Page changes and source controls preserve drafts. Leaving unsaved local review warns; processing view can be left safely. Restart/refresh limitations are explicit. |
| New packet | No previous packet's notes, fields, outcome or draft leaks into it. |
| Clinical scope | No approval with missing applicable-rule coverage; no denial based only on unavailable evidence. Authorization remains separate. |
| Natal's design | Review her pushed diff at 390/768/1440 px, keyboard-only and 200% zoom. Preserve IDs, uncertainty labels, error states and behavior tests. |

Do not call the real-field milestone complete until these gates run against the agreed backend. Current public Pages is a static demonstration, not hosted clinical processing. API hosting, authenticated users, durable records and production data approval remain pilot prerequisites.
