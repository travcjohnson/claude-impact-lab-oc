# Intake — frontend prototype

A dependency-free browser prototype for IHH Challenge 1. This is frontend work, not an installed clinical service.

## Run

From `frontend/`:

```bash
npm start
```

This uses Python 3's static server on port 4173, serving the repository parent directory so the local criteria and handoff links work. Navigate to the `/frontend/` path in your development browser. Alternatively run `python3 -m http.server 4173 --bind 127.0.0.1` from the repository root. Do not expose a server containing patient records publicly.

No npm installation, API keys, external fonts, or build step needed. Node.js is only needed for the npm shortcut and unit tests. Python 3 serves the files; the app is vanilla JavaScript/CSS with ES modules.

## What works

- Local PDF file validation (extension, size, basic PDF signature) and browser PDF preview. Parsing/rendering support ultimately depends on the browser; a PDF header check does not prove a valid, unencrypted PDF.
- Separate synthetic example with three source pages and three criterion checks.
- Six mock prefilled form fields; review/correction notes and source navigation.
- Finding review/filtering, source page navigation, zoom, rotation, and corrections.
- Human confirmation with rationale, reviewer and attestation; incomplete review and unsupported denial blocked.
- Editable unsent response; downloadable JSON review record including field edits and local event history.
- Responsive desktop/mobile layouts and visible keyboard focus.

## Mocked / unavailable

All demo text and findings are synthetic fixtures. Uploaded PDFs never inherit those findings. On the public static site, there is no OCR, AI service, full rule evaluation, insurance verification, server persistence, authentication, clinical audit, real sending, completed IHH PDF export, or measured time-saving result. The optional localhost backend now provides real text extraction/OCR, page search, review notes, and guarded clarification drafts; see ../backend/README.md. Approval is disabled because three checks cannot establish full eligibility. Form-field edits do not automatically recompute criterion findings; backend integration must add dependency invalidation.

Data stays in browser memory; refresh clears it. Download exports only the local demo review. No localStorage or remote upload. The app does not use event evaluation labels.

## Tests

```bash
npm test
```

Six Node unit tests cover confirmation guards, unknown/redacted preservation, denial rules, required rationale/attestation, upload limits, and fixture rule IDs/wording against the repo's criteria JSON.

Browser smoke tests: start the server, then `node tests/browser.cjs`. Requires Playwright and Chromium in your environment; set `PLAYWRIGHT_MODULE` to the installed module location if not on Node's module path, and `CHROMIUM_PATH` if Chromium is not `/usr/bin/chromium`. The test uses the repo's blank referral-form PDF (not a patient packet), writes synthetic screenshots/export under `/tmp`, and verifies upload validation, prefill corrections, source review, outcome guards, confirmation/export, session reset, and mobile overflow.

See [research, metrics and backend handoff](../docs/frontend-research-and-handoff.md) for sources, API contract, workflow semantics, priorities, and demo script.

## Publish updates

The public frontend uses GitHub Pages from the `gh-pages` branch. Source is on `codex/frontend-live`.

```bash
npm test
npm run deploy
```

The deploy command builds an explicit allowlist of static files into ignored `dist/` and pushes a new commit to `gh-pages` without switching or modifying the source index. Only app assets, the public criteria text, the handoff, and the temporary team-board data are published. No referral PDFs, ZIPs, OCR, or colleague case fixtures are included. GitHub can take a short time to rebuild; this is not automatic deployment on every source edit.

`frontend/team/tasks.json` is the shared temporary board data. Edit its status/assignees on `codex/frontend-live`, then use Refresh on the board; the board fetches that GitHub file and labels any fallback snapshot. The requested GitHub Project is not created: the integration can read projects but `createProjectV2` is denied. GitHub Issues is also disabled, and this integration cannot enable it.

## Local document-processing mode

Run the FastAPI service described in [backend/README.md](../backend/README.md), then open its root page locally. After selecting a permitted PDF, choose **Extract text with local backend**. This sends the file to the service on your own computer and enables real page images/text, search, review notes and an unsent next-step draft. It does not generate clinical fields or eligibility decisions. GitHub Pages remains static; it does not expose this localhost backend.

## Field verification and reviewed summary

In the synthetic demo, choose **Review prefilled form**. The workspace keeps source pages beside six example fields, preserves original suggestions, records correction notes and reviewer labels, and separates reviewed-but-unresolved fields from source-verified fields. All fields must be reviewed before a person can attest and prepare a summary. Text and JSON exports include unresolved items and explicitly identify synthetic data. Editing a field removes the prior export and requires review again; related synthetic findings also require renewed review.

`field-review-model.js` is a UI-only synthetic fixture/state model, **not the BE-03 backend schema**. `field-review.js` renders that state. No arbitrary uploaded PDF is routed through these fixtures. The local OCR workflow still runs through `backend-client.js`; real extracted fields and server-authoritative review/export are awaiting the shared Harjeev/Vibhu contract. The only backend change for this UI is adding the two static module names to the local asset allowlist.

Reviewer labels/history are browser memory, not authenticated or durable records. Missing, conflicting and redacted example fields cannot be promoted to verified by a checkbox. The exported scope is six example fields, not the full IHH intake form. No clinical eligibility or insurance authorization is established.

Run `npm test` for the state guards. For the field workflow browser test, serve the built frontend, set `FRONTEND_URL` to that internal test server, then run `node frontend/tests/field-review-browser.cjs` from the repository root. This requires Playwright and Chromium; `PLAYWRIGHT_MODULE` and `CHROMIUM_PATH` can select installed paths. The existing `frontend/tests/browser.cjs` also accepts `FRONTEND_URL`.

The attention checklist and **Next unreviewed field** button move keyboard focus directly to the relevant field. Source viewing includes a return-to-field action. A confirmed summary also offers a focused clarification text draft containing only unresolved items and original example-page references. Redacted timing is routed to an authorized reviewer, never reconstructed. Any field edit invalidates both summary and clarification downloads. All these outputs remain synthetic and unsent.

## Automatic frontend deployment

`.github/workflows/frontend-pages.yml` tests and builds frontend changes pushed or merged into `codex/frontend-live`, checks the exact static artifact allowlist, then deploys through GitHub Pages Actions. Pull requests targeting that branch or `main` run the build checks without deploying. The Python backend is not published. Changes only to backend files do not trigger this frontend workflow.

Repository Pages must use **Settings → Pages → Build and deployment → Source: GitHub Actions**. The `github-pages` environment must allow deployments from `codex/frontend-live`; repository policy must permit the official checkout, setup-node, upload-pages-artifact and deploy-pages actions. No personal access token or extra secret is required. Once this source is selected, the old `npm run deploy` branch-push script no longer publishes the site; use the workflow. The Actions UI's manual Run workflow button may require this workflow to exist on the default branch first.

The current deployment branch is deliberately `codex/frontend-live`. Merging only to `main` does not deploy. When the team moves integration to `main`, update the push branch, both deployment guards and environment branch policy together. Failed tests/builds prevent deployment and preserve the last successful site. The workflow's allowlist must be updated deliberately when adding a new public static asset.

## Local review recovery

The local text-review client preserves per-page note drafts, rationale, next-step choice and edited unsent text while navigating pages. Unsaved page notes block confirmation/export. Save failures retain inputs; 409 responses expose a reload action that preserves local drafts and shows the currently saved server note for comparison. Writes are guarded against concurrent clicks, and requests have a 30-second timeout. Leaving this view with unsaved page notes asks before discarding them; refresh still loses session memory.

Export rechecks the server record and matching draft version before downloading. The export records the server draft separately from the user's edited unsent text. This is a checked snapshot, not a server-side immutable audit or an atomic cross-request transaction. The merged BE-04 API provides exact-confirmation replay and authoritative field review. The client uses its current draft field contract and includes the server-reviewed export when fields exist.

The current adapter validates the existing text-only response identity, version and original page numbering, and rejects unknown analysis states. It accepts documented analysis states for manual source review without interpreting populated clinical fields as verified facts. It does not guess BE-03's future field schema or use synthetic fallback results. Test `node frontend/tests/backend-recovery-browser.cjs` with the local server running: its API is mocked with synthetic data to exercise failure paths. `node backend/tests/browser.cjs` separately exercises the real service with the public blank form.

Pages Actions activation was verified after the repository owner updated Source and environment branch rules. Subsequent eligible pushes to `codex/frontend-live` now publish automatically after the workflow passes. Do not use the old gh-pages branch-push script to publish.

Analysis regression check: `node frontend/tests/analysis-state-browser.cjs` (local server running). Synthetic responses exercise pending analysis followed by completion, failure or unavailability; notes/rationale survive, old attestation clears, and confirmation uses the current revision. Backend assertion and version regressions are in `backend/tests/test_analysis.py`.

The demo role selector separates the person receiving care, hospital referral staff and IHH intake staff. External views use synthetic examples only; this is not sign-in or access control. See [role workspaces and backend requirements](../docs/role-workspaces.md).

## Careward design

The approved interface name is **Careward · Referral coordination**. The green palette is retained with self-hosted Source Sans 3, larger readable type, restrained panels and visible mobile navigation. See [design conventions and presentation handoff](../docs/careward-design.md). Font license ships with the static assets.

## Shared referral loop

The synthetic inbox, hospital completeness check, clarification thread and mock CRM handoff share browser-session state across roles. See [the workflow handoff and demo steps](../docs/referral-loop-handoff.md). Source fields now open inline in evidence review. Uploaded PDFs remain a separate local preview/OCR path.

## Real local field-review regression

Start `python3 backend/tests/field_browser_server.py` in one terminal, then run `node frontend/tests/backend-fields-browser.cjs`. This serves the real API on loopback port 8001 with an injected synthetic analysis adapter and invented PDF; it never calls a model. The browser test covers all-field review, source navigation, retained edits on concurrent 409/reload, uncertainty gates, confirmed export and reversal validation. Stop the test server afterward. Production model extraction and clinical accuracy are not validated by this test.

The internal team board is excluded from the public build and navigation. Its source remains in the repository for reference; GitHub Issues/Projects is the current team tracker.

### Walkthrough and demo onboarding continuity

“Take a tour” opens a keyboard-accessible walkthrough for the selected role without
leaving the current review. In an inbox referral, “Continue onboarding” retains
proposed coordination tasks after an explicit **Save demo progress on this device**.
The client preview shows the saved checklist for the last selected demo referral.

Only fixed demo IDs, enumerated checklist states, a save timestamp, and clarification
categories/statuses are stored in localStorage. Replies, source fields, decisions,
PDFs and real API referral IDs are excluded. Saved clarification categories are a
historical snapshot, not restored clinical evidence; the queue remains session-only.
Clear saved progress removes that referral's snapshot. Storage failures display an
error rather than claiming a save. This is not a shared or production client record.

Check with `node frontend/tests/onboarding-browser.cjs` (static build on port 4176).
