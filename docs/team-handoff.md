# Team 1 — build handoff

The next milestone is one complete flow: permitted PDF → source-linked intake fields → coordinator corrections → reviewed summary and unsent clarification export. Start with intake assistance; clinical eligibility and insurance authorization remain separate and require human review. No automatic admission decisions.

## Where everyone works

- [GitHub Issues](https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1/issues) is the primary tracker. Each issue has scope, acceptance criteria and assignees. Record progress, blockers and PR links there. Do not put packet text or screenshots in issues.
- Integration branch: `codex/frontend-live`. The latest frontend/backend work is not yet merged to `main`. [PR #1](https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1/pull/1) contains that integration.
- Create a task branch from the latest integration branch and open a PR back to `codex/frontend-live`. Avoid simultaneous direct edits to the shared branch. Keep your existing local changes safe; never reset them to follow these instructions.
- The public [demo](https://phileokairos-pixel.github.io/claude-impact-lab-oc---team-1/) is static. It has a synthetic workflow and local PDF preview; real OCR runs only with the local backend. The [site board](https://phileokairos-pixel.github.io/claude-impact-lab-oc---team-1/team/) links to issues but is not a live status mirror.
- Project owner: check that all seven issues appear and grant the teammates write access in the Project settings. Repository collaboration does not prove access to a private user-owned Project. The automation integration currently cannot read or write the Project.

## Ownership and the next deliverable

| Owner | Work now | Deliverable to unblock the next person |
|---|---|---|
| Harjeev | [BE-03 / #4](https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1/issues/4), building on BE-02 / #3 | Versioned schema and synthetic response fixture, then real extraction with page evidence and explicit uncertainty |
| VibhuA-ai | [BE-04 / #5](https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1/issues/5), building on BE-01 / #2 | Human-confirmed field corrections, preserved extracted originals, stale-output invalidation and reviewed export |
| phileokairos-pixel with Codex | Field verification UI and export preview | Source beside value, clear unresolved states, correction history and usable next-step output against Harjeev’s agreed fixture |
| Harjeev, with VibhuA-ai | BE-07 / #8; BE-05 / #6 after extraction works | Synthetic committed examples; private evaluation and reproducible results without labels leaking into inference |
| VibhuA-ai | BE-06 / #7 after the flow integrates | Timed walkthrough, failures and limitations recorded; no unsupported time-saving claims |

Vibhu has resumed API/workflow ownership. Start with BE-04 human review/export, coordinate BE-01 analysis integration with Harjeev, then add BE-06 measurement. phileokairos-pixel and Codex focus on frontend/design and integration. Finish the contract and one vertical slice before adding production infrastructure.

## Start from a clean checkout

For a new clone:

```bash
git clone https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1.git
cd claude-impact-lab-oc---team-1
git fetch origin codex/frontend-live
git switch -c my-ticket-branch origin/codex/frontend-live
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r backend/requirements-dev.txt
tesseract --version
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Replace `my-ticket-branch` with a unique branch name. Python 3.12+, Node.js with `node --test` support, and Tesseract are prerequisites. Install Tesseract through your platform's normal package manager if missing; on Debian/Ubuntu the package is `tesseract-ocr`. See [backend setup](../backend/README.md). The backend serves the frontend too; a separate frontend server is unnecessary for this flow. No API key is needed for the current local OCR backend. Model extraction is not yet connected; any model/key requirement must be documented by its implementer and supplied securely, never in Git or chat.

In another terminal at the repository root with the virtual environment active:

```bash
python3 -m unittest discover -s backend/tests -v
npm --prefix frontend test
npm --prefix frontend run build
```

The existing implementation previously passed eight API tests and six frontend tests. That does not establish accuracy of extracted clinical facts. Check `/health` locally, upload a synthetic PDF or the public blank referral form, verify original-page images and text, add a review note, confirm clarification, then edit the note and verify the old draft becomes unavailable. Approved event packets stay outside Git and static publishing roots.

## Contract checkpoint before parallel implementation

Harjeev delivers the schema and a synthetic fixture first in BE-03. Frontend and API work then use that exact artifact. [The existing design handoff](frontend-research-and-handoff.md) describes the proposed fields; it is not proof that extraction is implemented.

Agree on stable field IDs; original extracted value versus reviewed value; original PDF page evidence; missing, redacted, conflicting and unreadable states; analysis coverage; revision and validation-error shape. Keep `text_ready` distinct from analysis completion. Existing `GET /api/referrals/{id}` currently returns empty `formFields` and `findings`; new work must preserve current upload, page, search and review behavior or provide a coordinated adapter.

To avoid overlapping edits, Harjeev should put extraction/schema logic in a dedicated module and identify the intended `backend/app.py` integration changes in his PR. The API owner coordinates changes to that shared file. Frontend integration belongs in `frontend/backend-client.js`; the synthetic demonstration remains labeled separately. Do not invent a second conflicting field schema in the UI.

## Definition of an integrated slice

- Values link to real source pages; an absent or failed extraction is shown explicitly, never supplied by the synthetic demo.
- A person can confirm or correct a value without erasing the original extraction and evidence.
- Changing evidence/review invalidates prior confirmed output; stale requests are rejected server-side.
- Export distinguishes confirmed facts from unresolved items and includes evidence references and review context. It never implies insurance authorization or admission approval that has not been established.
- A malformed response, failed OCR page or missing model credential produces a useful visible error with manual review still possible.
- The changed API tests and a real local browser walkthrough pass. Each PR states the test commands, results, remaining mock behavior and limitations. One teammate reviews it before integration.

Once the slice passes, rerun the end-to-end walkthrough from the integration branch. Deploy the static frontend deliberately with `npm --prefix frontend run deploy`; it does not host the Python backend. Review PR #1 for merging into `main` only after team integration checks. Do not force-push shared branches.

## Implementation path after the event

The current backend uses temporary local storage and unauthenticated reviewer labels. A real IHH pilot still needs an agreed operational owner, approved hosting and access controls, durable review history, retention/deletion controls, approved AI data handling if used, validated extraction and a supported destination for reviewed outputs. These are implementation gates, not features already delivered. No live IHH integrations or real outbound messaging during the event.

Begin a pilot with one coordinator and a narrow intake step alongside the existing process; use reviewed exports until a destination system is confirmed. Expand from search to verified prefill to completeness checks only after staff can correct errors and the team has measured quality. See [staged rollout](adoption-and-demo-strategy.md).

The reported 120-minute packet review is a starting hypothesis, not a measured study. Targets of 90/60/30 minutes represent 25/50/75% less time. Measure hands-on review, total elapsed turnaround, corrections and missed critical information separately before claiming savings.

## Frontend integration update: field review

The synthetic field-review/export UI is implemented in `frontend/field-review.js` and `frontend/field-review-model.js`. It retains extracted originals, corrections, reviewer/history, unresolved items, original example-page links and a revision-bound text/JSON export. Related synthetic findings are invalidated after field edits. It is a UI-only fixture, not an alternative server contract or real extraction.

Harjeev: provide the validated BE-03 schema/fixture before replacing the synthetic data boundary. Vibhu: connect the server-authoritative review revision, correction history, allowed actions and confirmed export; do not rely on the browser's guards as authorization. Frontend integration will adapt the agreed contract through `backend-client.js`. Do not route uploaded PDFs through the synthetic store. Both new JS modules are allowed by the local static-file handler so existing local startup remains usable.

## Automatic deployment workflow

The `Test and deploy intake frontend` workflow validates frontend pull requests and deploys frontend changes on `codex/frontend-live` once Pages Source is set to GitHub Actions. See `frontend/README.md` for the one-time Pages/environment settings. PRs never deploy; merging only to `main` is not a deployment trigger. Backend hosting remains separate. After Actions publishing is enabled, use the workflow rather than the older branch-based deploy command above.

## Two frontend lanes

Natal (@neetalp) owns presentation, responsive layout and accessibility in FE-01/FE-02 (#9/#10). phileokairos-pixel with Codex owns API integration, review behavior and exports in FE-03/FE-04 (#11/#12). Read [frontend lane boundaries](frontend-lanes.md) before editing shared frontend files. Each ticket includes a coding-assistant prompt and test expectations.
