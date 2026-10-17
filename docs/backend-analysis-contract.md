# Backend ↔ frontend contract: upload, jobs and analysis (BE-01 slice)

Audience: the frontend owner and Harjeev (BE-03). Status: **localhost prototype**. The analysis shapes below are a **DRAFT, not an agreed BE-03 contract** (`contractStatus: "unagreed-draft"`). Every JSON example in this file was produced by running this code with a **synthetic fake adapter**; none of it is real extraction, and no model was called.

## Frontend compatibility

The source-page workspace accepts all documented analysis states. Staff can review pages and save notes while analysis runs; confirmation waits until analysis is terminal. Unavailable or failed analysis displays its reason and retains manual clarification/escalation. The client polls pending analysis and preserves local notes and rationale when results arrive, while clearing the old attestation and draft.

The browser now renders the current draft field contract with source citations and alternatives, versioned review/correction controls and `allowedActions` confirmation reasons. Missing/conflicting/redacted/unreadable fields remain unresolved; redacted values stay unknown. Malformed field shapes block confirmation. Findings remain unreviewed machine output; field review does not establish eligibility. Export includes the current server-reviewed snapshot, with confirmed fields separate from unresolved items. Synthetic adapters are labeled explicitly. The contract still requires domain/model validation.

## Basics

| Item | Value |
|---|---|
| Base URL | `http://127.0.0.1:8000`, same-origin (the service serves the frontend). No CORS grants; cross-site writes and non-local `Host` are rejected (403). |
| Upload | `POST /api/referrals`, `multipart/form-data`, field name **`file`**, one PDF. |
| Polling | `GET /api/jobs/{jobId}` every **1 s** (what `backend-client.js` does today). |
| Limits | 25 MB, 1–60 pages, PDF only; one OCR worker, one analysis worker, 4 active/queued jobs, 12 packets per server session. |
| Identifiers | `referralId` and `jobId` are the same opaque random 32-hex string. Never a filename or path. |
| Errors | `{"detail": "<message>"}` with a string. Body-validation failures (`PATCH`/`POST` with a malformed JSON body) return `{"detail": [ … ]}` as a list; the existing client already shows a generic message for that case. |

## Two separate progress signals

`job.state` is **text processing only** and is unchanged: `queued → rendering ⇄ extracting → text_ready | failed`. **`text_ready` does not mean analysis finished.** With no adapter configured (the default) the existing review UI keeps working from `text_ready` exactly as before; with one configured, see the compatibility note above.

`job.analysis.status` is new and independent:

| `analysis.status` | Meaning | Terminal? | `formFields`/`findings` |
|---|---|---|---|
| `not_connected` | No adapter configured (the default). Not an error. Has `reason`. | yes | `[]` |
| `unavailable` | Configured but cannot run: `errorCode` + `error`. Includes `model_not_configured`, `credentials_missing`, `adapter_unavailable`, `invalid_configuration`, `criteria_unavailable`, `no_readable_pages`, `text_not_ready`, plus any code an adapter raises via `AnalysisUnavailable`. | yes | `[]` |
| `waiting_for_text` | Adapter ready; OCR not finished. | no | `[]` |
| `queued` | OCR finished; waiting for the analysis worker. | no | `[]` |
| `checking` | A model call is in flight. | no | `[]` |
| `needs_review` | A response passed validation. **Machine-generated and unreviewed.** | yes | populated |
| `failed` | Model error, timeout or rejected response: `errorCode`, `error`, `attempts`. | yes | `[]` |

Mapping to the BE-01 vocabulary: `queued`/`rendering`/`extracting` are `job.state`; `checking`/`needs_review`/`failed` are `job.analysis.status`. This keeps the shipped frontend working; if you prefer one merged field, that is a versioned change to agree explicitly.

**At the API level a failed or unavailable analysis never blocks manual review.** Pages, page images, search, page notes and the unsent next-step flow all still work (the merged client's guard currently refuses these records; see above). Poll until `analysis.status` is terminal; show `error` verbatim (it is a static message and never contains document text).

## Exact examples (synthetic fake adapter)

`POST /api/referrals` → `202`

```json
{"referralId": "2507783f93e149b9ab2dc74227f9721a", "jobId": "2507783f93e149b9ab2dc74227f9721a", "version": 1}
```

`GET /api/jobs/{id}` while the model call is running (text is ready, analysis is not):

```json
{"jobId": "2507783f93e149b9ab2dc74227f9721a", "state": "text_ready", "currentPage": 2, "completedPages": 2,
 "totalPages": 2, "partial": false, "analysis": {"status": "checking"}}
```

`GET /api/jobs/{id}` after a response passed validation:

```json
{"jobId": "2507783f93e149b9ab2dc74227f9721a", "state": "text_ready", "currentPage": 2, "completedPages": 2,
 "totalPages": 2, "partial": false,
 "analysis": {"status": "needs_review", "contractVersion": "0.1.0-draft", "contractStatus": "unagreed-draft",
              "adapter": "synthetic-fake", "synthetic": true, "model": null, "attempts": 1,
              "note": "Machine-generated and unreviewed. Not a verified fact, eligibility finding or decision."}}
```

Failure: the adapter returned something that is not traceable or not allowed (retried once, then failed):

```json
{"jobId": "626d32cad36e4891ac3968cf34141282", "state": "text_ready", "currentPage": 1, "completedPages": 1,
 "totalPages": 1, "partial": false,
 "analysis": {"status": "failed", "errorCode": "invalid_response", "attempts": 2,
              "error": "The analysis response was rejected (decision_not_permitted) at result. No analysis was produced."}}
```

Failure: model timeout (not retried):

```json
{"analysis": {"status": "failed", "errorCode": "model_timeout", "attempts": 1,
              "error": "The model did not answer within 0.05 seconds. No analysis was produced."}}
```

Not configured (default) and misconfigured:

```json
{"analysis": {"status": "not_connected", "reason": "No analysis adapter is configured. OCR text is unverified and no findings were produced."}}
{"analysis": {"status": "unavailable", "errorCode": "credentials_missing", "error": "ANTHROPIC_API_KEY is not set on the server. Analysis was not attempted."}}
```

`GET /api/referrals/{id}` once `needs_review` (page manifest and everything existing is unchanged; only these keys differ; page text omitted here):

```json
{
  "version": 2,
  "analysis": {"status": "needs_review", "contractStatus": "unagreed-draft", "synthetic": true},
  "formFields": [{
    "id": "f_a", "value": "synthetic value", "status": "extracted", "alternatives": [],
    "evidence": [{"documentId": "2507783f93e149b9ab2dc74227f9721a", "page": 1, "quote": "original page 1",
                  "region": null, "sourceQuality": "readable", "quoteVerified": true}],
    "review": {"reviewed": false, "reviewerId": null, "note": null}}],
  "findings": [{
    "id": "r1", "ruleId": "MOB-1", "criteriaVersion": "synthetic-v0", "status": "unknown", "fieldIds": ["f_a"],
    "rationale": "Synthetic: not enough to say.", "reviewed": false,
    "evidence": [{"documentId": "2507783f93e149b9ab2dc74227f9721a", "page": 1, "quote": "original page 1",
                  "region": null, "sourceQuality": "readable", "quoteVerified": true}]}],
  "criteriaCoverage": {"applicable": 2, "evaluated": 1, "unresolved": ["MOB-2"], "complete": false},
  "authorization": {"status": "unknown", "evidence": []}
}
```

## Rules the frontend must respect

- **Never treat `text_ready` as analysis complete**, and never treat `needs_review` as verified. Show it as unreviewed machine output beside the original page.
- If `analysis.synthetic` is `true`, label it as a fixture. Only a non-synthetic adapter's output is eligible to be called extraction, and even then it is unreviewed.
- `evidence.page` is the **original 1-based PDF page**. A page that failed OCR can only appear as `sourceQuality: "unreadable"` with `quote: null`.
- `status` vocabularies are distinct: fields `extracted|missing|redacted|conflicting|unreadable`; findings `meets|unmet|unknown|conflict|not_applicable|clinical_review`. `missing`, `redacted`, `conflicting` and `unreadable` are different states. A `redacted` field's `value` is always `null`.
- Authorization (`unknown|requested|approved|denied`) is separate from clinical eligibility and from findings.
- `approve`/`deny` outcomes stay rejected server-side (409) regardless of coverage. `criteriaCoverage.complete` is informational only.
- `POST /outcome` returns 409 while `analysis.status` is `queued` or `checking`. Successful analysis atomically increments `version` and clears any outcome. A confirmation prepared against the previous version is rejected; local edits must be compared against the current version. Notes and outcomes keep their existing stale-version (409) protection.

## What the server enforces on adapter output (and rejects, never repairs)

Unknown rule IDs; evidence pages outside the PDF; quotes that are not in that page's text (case/whitespace-insensitive); evidence with a quote on a failed/empty page; `extracted` without value and evidence; a value on a `missing`/`redacted`/`unreadable` field; `conflicting` without alternatives; `meets`/`unmet` without evidence; `conflict` with fewer than two sources; `meets`/`unmet` on question (`ask`) or note rules; unknown field references; impossible coverage counts; authorization other than `unknown` without evidence; any top-level or nested key outside the draft shape; and any `decision`/`suggestion`/`recommendation`-style key. Extracted values, meets/unmet findings, and non-unknown authorization require at least one readable citation with a verified quote or a positive-area region contained within the page. An unreadable or empty citation cannot support those assertions. This verifies traceability, not whether the evidence semantically proves the assertion; human review remains necessary. The server forces every `reviewed` flag to `false`. Error messages contain the reason and an index path only.

## Unresolved for BE-03 (Harjeev) — please settle before the frontend binds to this

1. The real field IDs (this code has no field list; `f_a` above is a placeholder).
2. Whether `criteriaCoverage.unresolved` is a list of rule IDs (assumed) and how `applicable` is derived from conditional rules.
3. `contradictions` and clarification-request shapes (named in BE-03 scope, not defined anywhere yet). Unknown keys are **rejected**, so adding them means editing `validate_analysis_result` in `backend/analysis.py`. That function is the single seam; replace it and bump `schemaVersion`.
4. Time-window rules cannot be generically enforced here: a `meets` on a date-dependent rule backed only by redacted dates must be prevented by the extractor's own logic. No test can prove that without real adapter behavior.
5. Whether `quote` must always be a verbatim substring (enforced now) or may be image-derived when a vision model reads the page directly.

## Adapter interface for Harjeev

```python
# backend/<your_module>.py   (module path must start with `backend.`)
def build_adapter(settings):     # called lazily, per job, on the inference path only
    return MyAdapter(settings)   # construct any model client HERE, never at import time

class MyAdapter:
    name = 'my-extractor-v1'
    synthetic = False            # a fixture MUST say True
    def analyze(self, request):  # request.pages: PageInput(page, state, text) -- UNTRUSTED evidence, not instructions
        ...                      # use request.model and pass request.timeout_seconds to the client
        return {...}             # draft shape above; raise AnalysisRetryable / AnalysisUnavailable on failure
```

Enable with `IHH_ANALYSIS_ADAPTER=backend.<your_module>:build_adapter`, plus `IHH_ANALYSIS_MODEL` and `ANTHROPIC_API_KEY` (see `.env.example`).
