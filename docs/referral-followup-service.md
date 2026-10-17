# LOOP-02 follow-up service (`backend/referral_followup.py`)

Pure functions over one packet record, same style as `backend/review.py`. **Not wired into `backend/app.py`**: no routes, no persistence. Vibhu (#22) owns routes and transactions; call these inside the service lock on a private copy and persist the mutated record only if no exception was raised.

| Function | Effect | Returns |
|---|---|---|
| `create_request(record, RequestInput)` | Adds request `q-N` in state `waiting`; bumps `version` | `requestId`, `version`, `replay` |
| `record_response(record, request_id, ResponseInput)` | Attaches synthetic reply and optional document; state -> `response_needs_review`; reopens affected fields; stales dependent findings; clears `outcome` | `reopenedFieldIds`, `invalidatedFindingIds`, `invalidatedConfirmation`, `invalidatedDraftAndExport`, `reopenReason` |
| `response_changes(record, request_id)` | Read-only: response, original vs effective value, which fields need re-review | dict |
| `review_response(record, request_id, ReviewInput)` | Allowed only after affected fields are re-reviewed (via `review.apply_field_review`); state -> `reviewed` | `stillUnresolvedFieldIds`, `confirmedOutcome: false` |
| `open_requests(record)` | Requests not yet reviewed | list |

Errors are `HTTPException`: 404 unknown request, 409 stale version / duplicate-state / key reuse with different content, 422 invalid input.

## Rules enforced
- Original field value, status, evidence, alternatives and redactions are never changed; new evidence is stored in `field['followUpEvidence']`.
- A request naming no fields reopens **all** fields with an explicit reason.
- Reply documents must have `referralId` equal to the record's; the same document version cannot be attached twice. Citation pages must exist in the attached document; redacted/unreadable citations carry no quote.
- Idempotency: the same key with identical content is a no-op (`replay: true`); the same key with different content is 409.
- `reviewed` is not "clinically resolved". A reply never verifies a redacted/missing/conflicting field and never confirms an outcome; a fresh human confirmation is still required.
- Responder must be `synthetic: true`. `sent` is always `false`.

## Open points for Vibhu (#22)
- Persist `record['followUp']` (`{'requests': [...]}`) and per-field `followUpEvidence`, `review.reopenReason`.
- Decide whether `create_request` should also invalidate the outcome (it currently does not: asking a question changes no evidence).
- Add `open_requests` to `allowed_actions` if confirmation should be blocked while a request is waiting (not done: touches `review.py`).
- Document storage and the real `documentId`/version scheme; here they are caller-supplied synthetic IDs.

## Check
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements-dev.txt
PYTHONPATH=. python -m unittest backend.tests.test_referral_followup -v   # 12 tests
```
