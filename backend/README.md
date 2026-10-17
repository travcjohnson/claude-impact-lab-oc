# Local packet-processing backend

This implements the first adoption step: a permitted PDF becomes searchable text alongside its original pages, with explicit human review and an unsent clarification/escalation draft. By default it does not extract clinical form fields, apply admission criteria, call an AI provider, or make eligibility recommendations. An **optional analysis adapter boundary** (see below) lets the BE-03 extraction module plug in; nothing is connected until it is explicitly configured, and no real extractor exists in this repository yet.

## Start

From the repository root, with Python 3.12+:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r backend/requirements.txt
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Tesseract must be installed for image-only scans (`tesseract --version`). On Debian/Ubuntu its package is `tesseract-ocr`; install through your environment's approved system-package workflow. PyMuPDF renders PDFs, so Poppler is not needed by this service. Native PDF text works without Tesseract; scan pages explicitly fail OCR if it is unavailable. Direct Python dependency versions are pinned; transitive dependencies are not hash-locked.

Open the server root in your local browser. It serves the same frontend with an **Extract text with local backend** action after selecting a permitted PDF. The app detects this service only on localhost. It never uploads a PDF from GitHub Pages to an arbitrary remote server.

No API keys are needed for the default OCR-only service. This is not a public backend deployment: bind only to localhost. Host and Origin guards reject nonlocal/cross-site requests. There is no production authentication, tenant isolation, durable clinical audit, or compliance certification.

## What is implemented

- Real PDF parsing and validation: extension/signature, corruption, password protection, 25 MB size and 60-page limits.
- One processing worker; up to four admitted active/queued jobs and twelve packets per session.
- Page rendering bounded to 2,000 pixels on the longest dimension (up to 3× source resolution).
- Native text extraction where available; Tesseract for pages with little/no native text, bounded to 40 seconds per page.
- Original PDF page numbers retained on every result, including failed pages. Page images remain reviewable when OCR fails.
- Page text is labeled unverified. `no_text_detected` never asserts that a page is blank or a fact is absent. Long text is capped at 100,000 characters per page and marked `truncated`.
- Packet-wide literal text search with original-page snippets (maximum twenty matches; explicit truncation). A failed search does not prove absence because OCR may miss text.
- Versioned page notes; stale writes rejected. Editing notes invalidates prior next-step confirmation and draft.
- Server-side rejection of approval/denial while clinical analysis is absent. Clarification/escalation requires a page review, rationale, reviewer label, and attestation.
- Editable unsent draft and local export. There is no email/fax sending.

## Endpoints

| Method / path | Result |
|---|---|
| GET `/health` | Capability flags, limits, ephemeral-storage description, and an offline `analysis` configuration report (never calls a model) |
| POST `/api/referrals` (multipart `file`) | 202: referral ID, job ID, initial version |
| GET `/api/jobs/{id}` | Actual queued/rendering/extracting/text_ready/failed state, processed-page counts, and a separate `analysis` status |
| GET `/api/referrals/{id}` | Original-page manifest/text, explicit disconnected analysis, reviews and current outcome |
| GET `/api/referrals/{id}/search?q=term` | Unverified text snippets with original page numbers |
| GET `/api/referrals/{id}/pages/{n}/image` | Rendered original page |
| PATCH `/api/referrals/{id}/review` | `{version, page, reviewer, note}` → revised record; invalidates prior outcome |
| POST `/api/referrals/{id}/outcome` | `{version, decision, reviewer, rationale, attested}` → guarded next step |
| PATCH `/api/referrals/{id}/fields/{fieldId}` | BE-04: `{version, value, assessment, reviewer, note, page}` → field review; keeps the original, invalidates dependent findings/outcome |
| GET `/api/referrals/{id}/export` | BE-04: reviewed snapshot (confirmed vs unresolved); 409 without a current confirmation |
| GET/POST `/api/referrals/{id}/timing` | BE-06: derived durations (null when unknown) / `{event: pause\|resume\|wait_start\|wait_end, reason?}` |
| GET `/api/timing/summary` | BE-06: counts incl. failed/unfinished; no savings claim |
| GET `/api/referrals/{id}/draft` | Unsent draft only for the current confirmed version |

`text_ready` means text processing finished, **not** clinical analysis completed. `partial: true` indicates a page needs manual attention. An approval/denial attempt is always rejected in this version; no client-side override can enable it.

Field review, allowed-action reasons and the export are described in `docs/backend-review-contract.md` (synthetic examples; reviewer labels only, in-memory history, no auth).

## Analysis adapter (optional, off by default)

`job.state` stays text-processing only. A separate `job.analysis.status` reports `not_connected` (default), `unavailable`, `waiting_for_text`, `queued`, `checking`, `needs_review` or `failed`. **`text_ready` is not analysis completion and `needs_review` is not verification.** A failed or unavailable analysis leaves `formFields`/`findings` empty and manual review fully available through the API. The browser retains manual source review for all documented analysis states, polls pending analysis, and blocks confirmation until it finishes. The browser renders the current draft fields, saves versioned human reviews and honors confirmation blockers. Unknown field shapes block confirmation without synthetic substitution. Successful analysis advances the record version, rejecting confirmations based on older data; see `docs/backend-analysis-contract.md`. Approval/denial stay rejected regardless of coverage.

Configuration is environment-only and server-side; copy `.env.example` and see it for every variable. There is deliberately **no default model ID**:

```bash
python3 -m pip install -r backend/requirements-analysis.txt   # optional SDK, pinned
export IHH_ANALYSIS_MODEL=<model id>  ANTHROPIC_API_KEY=<set securely, never in Git>
python3 -m backend.analysis check-model      # confirms the key can see that model; sends no document data
```

Guarantees, each covered by `backend/tests/test_analysis.py`: startup and `/health` need no credential and call no model; the adapter module is located with `find_spec` (not executed) for `/health`, and a model client is constructed only inside the adapter factory on the inference path; each model call has a timeout (default 120 s, max 600) and rejected or transient responses are retried within `IHH_ANALYSIS_MAX_ATTEMPTS` (default 2, max 3) while timeouts fail fast; model errors, timeouts, missing credentials, invalid or untraceable responses (unknown rule IDs, out-of-range pages, quotes not in the page text, decision-style keys) become `failed`/`unavailable` and never a successful result; error text is a static message and never includes document text, model output or credentials. Criteria are read from the explicit `challenges/1-referral-intake/criteria/` directory (override with `IHH_CRITERIA_DIR`). The archived `blind_eval.py` is not in the working tree (only inside `referral-review-repo.zip`); moving it behind a lazy client and separating `score` from `suggest` is BE-05 work.

The result shape is a **draft** (`contractStatus: "unagreed-draft"`) taken from `docs/frontend-research-and-handoff.md`; BE-03 owns the real contract and replaces `validate_analysis_result`. Full integration contract, exact JSON and open questions: [`docs/backend-analysis-contract.md`](../docs/backend-analysis-contract.md).

## Data handling and limits

PDFs and page images go in a unique restricted temporary directory outside the checkout; text and review records live in server memory. Graceful shutdown removes the directory. A hard kill can leave temporary files, so inspect and remove the corresponding `ihh-local-packets-*` directory when appropriate. Do not log OCR text or put packet artifacts into Git. Original filenames are not used as storage paths. No data is served by a generic directory mount.

Data is **not durable**. Browser refresh can lose its selected file/job ID; server restart clears all jobs and reviews. Repeating a confirmation using the old version is rejected (409); there is no full idempotency-key replay protocol. Coordinator initials are a local demo label, not authenticated identity. OCR orientation/skew correction, handwriting/checkbox accuracy, duplicate detection, and multi-form extraction remain outstanding.

## Test

```bash
python3 -m pip install -r backend/requirements-dev.txt
python3 -m unittest discover -s backend/tests -v
npm --prefix frontend test
```

API tests use synthetic documents and injected OCR for deterministic error coverage; the analysis tests use clearly labeled **synthetic fake adapters** (no model is called, so they validate the server's handling of bad or missing analysis, not extraction quality). Real Tesseract was separately exercised on a generated scanned-image PDF. The downloaded de-identified R01 packet also completed 34/34 pages with original numbers preserved; this checks pipeline execution, not OCR accuracy or clinical correctness. No patient-specific text is included in this repository.

The browser workflow was tested using the public blank referral form: actual PDF text/page images, review note, confirmation, unsent draft, invalidation after an edit, and mobile layout. The local flow test is `backend/tests/browser.cjs`, requiring Playwright/Chromium and a running server; set `PLAYWRIGHT_MODULE` when using an externally installed module.

## Handoff to Harjeev and Vibhu

- BE-01: local API slice and the analysis adapter boundary work (fake-adapter tested; `check-model` exercised only against missing/fake credentials, never a real model ID); public authenticated hosting, production robustness and a real extractor remain separate work.
- BE-02: rendering/OCR/page provenance/search work; orientation, quality assessment, structured checkbox/handwriting extraction and source regions still need attention.
- BE-03: no model or clinical extractor is connected. Implement an adapter against the boundary above (`backend/analysis.py`), settle the open contract questions in `docs/backend-analysis-contract.md`, and replace the draft validator; do not promote OCR text into verified facts.
- BE-04: local next-step guards and stale-draft invalidation work. Complete rule-dependent invalidation, authenticated reviewers, durable audit and idempotency remain.

See `docs/adoption-and-demo-strategy.md` for the staged adoption plan. Keep existing synthetic demo and real-text workflow clearly separated.

## Offline evaluation (BE-05)

`python3 -m backend.evaluation suggest|score`. Separate steps; `score` needs no key or network. See `docs/backend-tickets/BE-05-evaluation.md`. Packet text, runs and suggestions are derived clinical content: keep them under git-ignored paths such as `runtime/`.

Short readable native PDF text is retained if optional OCR fails or returns no text. The page retains original numbering and reports `native_text_fallback` plus `ocr_failed` or `ocr_no_text`; all extracted text remains unverified.
