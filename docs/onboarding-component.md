# Onboarding presentation handoff (#25 → #24)

Aaron owns all frontend work, including #9/#10/#25. Backend owners should not
edit these files: Vibhu owns API/persistence (#22), Harjeev follow-up services (#23).

`frontend/onboarding.js` exports `renderHandoffPanel(root, view, callbacks)`.
It renders only; no fetch or storage occurs inside that renderer. The existing
`renderOnboarding` adapter supplies explicit synthetic browser storage; the tour
and client preview remain in the same module rather than a parallel implementation.

View shape:
- referralId, revision, mode (`synthetic-demo` or local server adapter mode)
- confirmedNextStep: nullable display string; null means coordination only
- unresolvedSummary: visible summary; never infer resolution from checklist status
- owner, nextAction, followUpAt (optional YYYY-MM-DD planning date)
- ownerOptions/actionOptions: arrays of {value, label}, supplied by the adapter
- tasks: [{label, status}], status not_started/in_progress/done
- message: current saved/unsaved state
- snapshot: optional controlled synthetic metadata; validated before rendering

Callbacks:
- onChange(draft): retain unsaved edits in the adapter’s session state
- onSave({referralId, expectedVersion, owner, nextAction, followUpAt, tasks}): async
  return {saved:true, message} only after the server confirms the current write.
  The server adapter must validate returned identity/version, map its exact API
  schema and keep client/server snapshots separate. This is not a new API contract.
- Reject saves with status 409 for stale state: entries remain visible, save is
  disabled, and optional onReload(draft) lets the adapter compare/reload safely.
- onClear is used only by the synthetic storage adapter; onReload is optional.

During save, controls are disabled and aria-busy/status are exposed. Failed saves
retain entries and permit retry. A response arriving after navigation does not
update a replacement screen. Unknown handoff/placement remains unknown. Client
preview receives only controlled demo tasks/next action, never internal checks or
clinical notes. Actual client-safe server response remains a backend requirement.

Demo storage whitelist now also allows enumerated responsible team/next action and
a validated planning date; arbitrary staff names, notes and clinical values remain
excluded. Old saved demo records load with unassigned/review defaults.

## Verification

- `npm --prefix frontend test` (23 tests)
- `npm --prefix frontend run build`
- Static dist server on 4176; `node frontend/tests/presentation-browser.cjs`
- `node frontend/tests/onboarding-browser.cjs`
- `node frontend/tests/referral-flow-browser.cjs` and roles-browser.cjs (API server 8000)
- Automated accessibility scan: install axe-core in a temporary tool directory,
  then `AXE_SCRIPT=/path/to/axe.min.js node frontend/tests/accessibility-browser.cjs`.
  Tested with axe-core 4.14.0; scans inbox, workflow, upload, review, fields, hospital,
  client. Automated checks are not a blanket WCAG certification.

Responsive checks cover 390/640/768/940/1440 widths at a 650px viewport height;
640px is an equivalent reflow width for a 1280px display at 200% zoom, not an actual
browser-zoom test. Keyboard tests cover handoff fields, modal Tab trapping and
Escape/focus restoration. Full assistive-technology/manual zoom audit remains open
in #10; unsupported claims must not be inferred from these checks.

## Confirmed demo next step

The synthetic review now records a bounded handoff (decision enum, timestamp,
revision, stale flag) on DEMO-001 and links directly to its onboarding panel. New
referrer evidence, source-field edits or revised findings invalidate that handoff.
The UI reopens review and blocks stale CRM export. No clinical confirmation is
persisted in localStorage; only controlled coordination metadata survives refresh.
This demonstrates the intended transition without inventing the pending server API.
