# Careward shared referral loop

## Delivered frontend behavior

The IHH home screen now starts with a synthetic referral inbox. Rows show source, received time (Pacific), information completeness, next action and a provisional two-hour countdown. Sort by target, newest or responses. The clock updates without losing form input. Source completeness is not inferred when a fixture has no assessment. Mobile rows stack into readable cards.

Hospital staff select a synthetic packet, see present/missing/unknown/redacted information and explicitly acknowledge gaps before simulating submission. One receipt creates DEMO-004 in the same browser's IHH inbox; repeated submission cannot duplicate it. A redacted date stays unknown, not an upload demand or reconstructed fact. No unsupported hard-stop clinical recommendation is made.

IHH opens a referral and creates a plain-language clarification request. The hospital view exposes an answer form, a synthetic attachment option and an information-unavailable option. Draft responses survive role switching. The reply moves the referral to response-needs-review. IHH can download the authored synthetic note and explicitly mark the response reviewed. That action does not establish eligibility or authorization. Confirming a clarification outcome in the linked DEMO-001 evidence review also opens the shared requests.

Each referral has manual discovery checklist entries for duplicate/provider involvement/court/background/CRM/bed checks. All start not checked; recording a demo check does not execute or verify those operations. The mock CRM export includes revision, events, unresolved questions and manual steps; for DEMO-001 it also carries forward reviewed source fields separately from unresolved/edited fields. No CRM or message delivery exists.

Source fields now open within the findings workspace rather than replacing it. Their review state persists; a changed field invalidates its dependent finding and confirmation. Field verification and clinical criterion judgment remain different actions. Confirming a finding advances to the next unreviewed finding. Hospital-facing response drafts use plain-language requests.

## Explicit limits

All shared records, receipts, attachments and questions are synthetic session state and disappear on refresh. Existing local PDF preview/OCR remains a separate path; uploaded packets never become invented queue findings. A non-DEMO-001 queue record cannot open another referral's clinical source fixture. The role selector is not authentication, and the synthetic hospital preview is not organization-scoped access control. Do not deploy this flow for actual patient information.

Two hours was described both as baseline and target in supplied information. The queue uses it only as a provisional demo target; no measured savings or service deadline is claimed. Active time is not inferred from wall-clock time.

## Backend integration boundaries reviewed

- PR #14 / docs/backend-review-contract.md: versioned field PATCH, allowedActions and human-confirmed export. The local frontend now implements its field review gate and server-reviewed export; the shared synthetic queue is still a separate demo.
- PR #18 (merged by the team during this work): extraction adapter and schema remain draft and require agreed field IDs/model validation.
- PR #20 has been merged into the still-open #14 branch: elapsed vs active timing, explicit pause/wait events, null unknowns and no claimed savings. The demo clock does not replace this instrumentation.
- Still needed: authenticated organization-scoped referral listing, durable submission IDs/receipts, completeness assessment provenance, clarification thread/attachment endpoints, staff review versions and audit. Do not introduce a parallel clinical schema by copying these browser fixtures.

The team merged #16–#19 into the integration branch during this frontend work; those changes were incorporated and the combined 80-test backend suite passed. #14 (including #20 timing) is now merged; local field review is connected, but the shared queue is not a multi-user backend. The public UI is still synthetic, not a live backend integration.

## Demonstration

1. Hospital role: select synthetic packet, review gaps, acknowledge and simulate submission.
2. IHH role: open DEMO-004, request therapy clarification.
3. Hospital role: answer or mark unavailable; optionally attach the synthetic note.
4. IHH role: inspect the response/attachment, mark reviewed, record manual steps and export the mock handoff.
5. DEMO-001 offers linked clinical evidence and inline field review; other records deliberately do not borrow its sources.

Tests: `npm --prefix frontend test`; `node frontend/tests/referral-flow-browser.cjs` with local backend running; existing demo/field/role/recovery flows. All examples are synthetic.
