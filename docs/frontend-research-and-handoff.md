# Referral intake: frontend research and backend handoff

Prepared October 17, 2026. Scope: Challenge 1, adult recuperative care; frontend prototype and integration specification. No IHH system integrations or real message sending.

## Decision for today's prototype

Make a coordinator faster at finding, verifying, and carrying forward information: **packet → prefilled fields → source-linked criteria review → human-confirmed next step → editable response draft**. The interface is an evidence workspace, not an autonomous admission decision-maker.

The user reports that full-packet review takes approximately two hours and wants 25–75% less time. This is a discovery input, not a measured baseline. The repo separately states a two-hour response promise. Do not equate hands-on review duration with elapsed turnaround time.

The user subsequently supplied a ZIP described as the form that takes time to fill out. Its download failed because it exceeds the executor's 32 MiB transfer limit. Its contents have **not** been inspected. Repository descriptions refer to multi-document referral packets, while the IHH form is one component. Discovery still needs to establish who fills the hospital form, what IHH re-enters, and whether the main bottleneck is review, transcription, or waiting. No findings below are derived from the uploaded ZIP.

## Evidence reviewed

### IHH / event sources (controlling requirements)

- [Challenge 1 brief](https://github.com/travcjohnson/claude-impact-lab-oc/blob/main/challenges/1-referral-intake/README.md): 15–35 faxed pages, manual review against six pages of criteria, two-hour response promise. Findings deep in the chart may contradict the form.
- [Adult criteria](https://github.com/travcjohnson/claude-impact-lab-oc/blob/main/challenges/1-referral-intake/criteria/admission-criteria.md) and [machine-readable criteria](https://github.com/travcjohnson/claude-impact-lab-oc/blob/main/challenges/1-referral-intake/criteria/admission-criteria.json): stable rule IDs, document precedence, conditional rules, and known ambiguities. Questions (`ask`) are not automatically pass/fail criteria.
- [Referral form/checklist](https://github.com/travcjohnson/claude-impact-lab-oc/blob/main/challenges/1-referral-intake/criteria/referral-form-and-checklist.md): online/email/fax receipt, clarification requests, approval/denial response, DOC-1 through DOC-10, authorization and staff-only fields.
- [Packet README](https://github.com/travcjohnson/claude-impact-lab-oc/blob/main/challenges/1-referral-intake/packets/README.md): 11 packets, 282 scanned pages; rotation, duplicates, missing forms, redacted dates, and contradictions. These are descriptions, not our packet-level analysis.
- [Judging](https://github.com/travcjohnson/claude-impact-lab-oc/blob/main/docs/judging.md): day-one impact 40%, product/idea 35%, demo clarity 25%; unseen packets may be tested.
- [Ground rules](https://github.com/travcjohnson/claude-impact-lab-oc/blob/main/docs/ground-rules.md): prototype only; use event de-identified records appropriately; no live IHH integration or real outbound messages; clearly disclose mocks.

Read the fork's source files. Independently fetched the original upstream brief and adult Markdown/JSON criteria on October 17; all three matched the fork byte for byte. The original PDFs exist under `challenges/1-referral-intake/criteria/source/`. No referral packet has been reviewed. Do not feed `eval/decisions.json` to the review pipeline; it contains outcome labels, not recorded clinical reasons.

### Comparable modernization research (retrieved October 17, 2026)

| Source and evidence strength | What changed / what is reported | Transferable UI/backend pattern | Limits |
|---|---|---|---|
| [Innovation Care Partners / ReferralMD](https://referralmd.com/solutions/innovation-care-partners-referral-management-success-story/) — named customer, vendor-published case study | Replaced a sunsetting referral platform. Standardized workflows, centralized status, automated alerts, and bidirectional Epic integration. Reports outbound referral processing moving from 5.1 to 4.0 days, and volume from 19,975 to 33,759 monthly referrals without staffing growth. | Single review state, explicit ownership, attention queue, avoidance of duplicate entry, instrumentation. | Observational vendor report; different setting and days-long workflow. Not an IHH time-saving estimate. Other large “faster” percentages on this page compare results with targets, not observed historical baselines; do not repeat them as before/after gains. |
| [House Calls / ReferralMD](https://referralmd.com/solutions/house-calls/) — named customer, vendor-published qualitative account | Describes less referral processing work and improved communication for in-home care. | Capture once, reuse verified information, carry context into a response. | No numerical baseline, timing method, or quantified effect supplied. Supports a workflow hypothesis, not a percentage claim. |
| [Integritus Healthcare / ReferralMD](https://referralmd.com/solutions/integritus-healthcare/) — named nonprofit customer, vendor-published qualitative account | Describes referral management and communication improvements across rehabilitation/skilled nursing operations; emphasizes usability and referral-volume handling. | A consistent worklist and readable review state; make operational reporting possible later. | No defensible time-saving magnitude. Skilled nursing is not recuperative care. |
| [CarePort Referral Management](https://careporthealth.com/products/referral-management/) and [CarePort Intake](https://careporthealth.com/intake/) — product documentation | Describes one system for incoming referrals, customizable worklists, electronic responses, status updates, non-electronic intake, EHR integration to avoid re-keying, and payer authorization tracking. | Accommodate today's PDFs/faxes while giving the receiving team one workspace; separate authorization from clinical review. | Product capabilities, not independent outcome evidence. The site's “8 min” response statistic does not define IHH's full clinical-review task; do not use it as our benchmark. |
| [NIMRC / NHCHC, Lessons Learned: CalAIM Implementation of Recuperative Care](https://nhchc.org/wp-content/uploads/2024/01/Lessons-Learned-Cal-AIM-implementation-of-recuperative-care-benefit-8.pdf) — sector-specific qualitative research, January 2024 | Describes fragmented hospital/plan portals and substantial referral/authorization administrative burden. Hospital feedback identifies authorization delays. Recommends standardized processes and minimum necessary referral information. | Keep clinical readiness, document completeness, and payer authorization distinct. Build an explicit clarification list rather than treating every empty field as a rejection. | Historical qualitative context, not current IHH operations or a current payer-policy determination. |

Tennr was considered, but a homepage request returned 403 and a guessed customer route returned 404. No Tennr claims are relied upon. Initial www-domain requests for other vendors failed; the canonical ReferralMD domain and actual CarePort product routes above were subsequently accessible. No network bypass was used.

**Conclusion:** evidence supports centralizing information, standardizing work states, and avoiding repeated entry. It does not establish that a frontend alone will reduce IHH review time by 25–75%. OCR, evidence retrieval, rules, and operational waiting determine much of the benefit.

## Frontend implementation and UX rationale

Run the dependency-free app in `frontend/` (see its README).

1. **Add packet:** local PDF validation and preview. Uploading an arbitrary file never produces synthetic findings. The separate synthetic demo is labeled before and throughout use.
2. **Prefilled form:** six example fields, including transfer independence, medication self-administration, COVID result/date, authorization, and authorized stay. Each field has an explicit status, source-page link, human confirmation, and correction note. This is a subset, not a completed IHH form.
3. **Evidence review:** three example criteria, source-page viewer, pagination, zoom/rotation, review filters, and reviewer corrections. Synthetic page text is visibly invented and not represented as an actual fax image or AI extraction.
4. **Confirm outcome:** all example findings must be reviewed. Require reviewer initials/name, rationale, and attestation. Clarification/escalation leave the referral open. A demo denial requires an unmet criterion. Approval is unavailable because full-rule coverage is absent.
5. **Draft:** editable response with source-rule summaries, explicit authorization uncertainty, and downloadable JSON review record. No emails/faxes, no backend storage, and no durable or authenticated clinical audit.

Design: restrained green/cream palette, serif headings, compact labeled statuses, visible keyboard focus, responsive layouts, and text labels alongside color. Speed comes from proximity of evidence and review actions, not from pressure to approve quickly. No patient-identifying fixtures. No invented confidence percentage or performance score.

Keep form-field verification separate from rule interpretation: confirming a negative test result does not confirm its date, and confirming the presence of an authorization request does not confirm approval. A corrected field must trigger reevaluation of dependent findings once integrated with a backend; until then the UI explicitly treats them separately.

## Backend priorities and acceptance criteria

### P0: first working vertical slice

| Workstream | Backend responsibility | Acceptance criterion / frontend need |
|---|---|---|
| Ingest | Accept permitted PDF; validate signature and actual parseability; size/page limits; assign opaque packet ID and content hash; reject corrupt/encrypted/unsupported files with useful error. | Async job response; no fabricated success on failed analysis. Preserve original page numbering. |
| Page processing | Image/PDF rendering, orientation correction, OCR or vision extraction; track unreadable/blank/duplicate pages. Keep original alongside any normalized page. | Pages stay traceable. Low-quality extraction is explicit and reviewable, never silently assumed correct. |
| Form extraction | Populate the exact IHH form schema; distinguish present, absent, redacted, conflicting, and unreadable. Preserve source spans/regions. | Every non-null extracted fact has source evidence. No demographics or timing inferred from redactions. |
| Evidence retrieval | Look across the chart, including PT/OT/nursing/progress notes, not just the cover form. | Return multiple citations when sources disagree; preserve both values and do not guess chronology without dates. |
| Criteria application | Load versioned adult criteria with stable IDs; implement precedence and conditional rules; separate documents and questions from exclusions. | Rule-level outputs cite both criterion and packet evidence. Report evaluated vs applicable rule coverage. Unknown ≠ meets; missing ≠ failed. Full coverage is required before enabling approval. |
| Human review | Store field edits, original extraction, finding revisions, reviewer identity, reasons, and timestamps. | Authenticated server-side review and authoritative outcome validation; reject stale edits via version/ETag. UI controls alone are not enforcement. |
| Response draft | Construct a draft from reviewed facts and disposition, not unchecked extraction. | Editable draft. No automatic sending. A correction invalidates stale findings and previous confirmation. |

Do not prioritize EHR, live fax, payer-network integration, or messaging for today's prototype. The event disallows IHH integrations and real message sending. PDF-in → source-grounded structured result → reviewed draft-out is the useful first slice.

### Proposed API, not implemented

- `POST /api/referrals` multipart PDF → `202 {referralId, jobId, version}`.
- `GET /api/jobs/{jobId}` → `queued | rendering | extracting | checking | needs_review | failed`, stage, per-page progress, recoverable errors. Actual processing status, never a simulated “AI complete” animation.
- `GET /api/referrals/{id}` → versioned form fields, documents, findings, coverage, payer-authorization status, and file metadata.
- `GET /api/referrals/{id}/pages/{page}` → protected page asset; source regions expressed in normalized coordinates with orientation specified.
- `PATCH /api/referrals/{id}/review` with version + reviewer edits → revised version and invalidated dependent findings. Reject concurrent stale updates with 409.
- `POST /api/referrals/{id}/outcome` with version, disposition, rationale, attestation → server-validated review record. Use an idempotency key to prevent duplicate confirmations.
- `POST /api/referrals/{id}/draft` → unsent draft from the confirmed snapshot.

Example shape (types / placeholders; no actual record):

```ts
type Evidence = {
  documentId: string;
  page: number; // 1-based original PDF page
  quote: string | null; // exact text, not paraphrased as a quote
  region: [number, number, number, number] | null; // x,y,width,height in 0..1
  sourceQuality: 'readable' | 'uncertain' | 'unreadable';
};
type Field = {
  id: string;
  value: string | boolean | number | null;
  status: 'extracted' | 'missing' | 'redacted' | 'conflicting' | 'unreadable';
  evidence: Evidence[];
  alternatives: {value: string; evidence: Evidence[]}[];
  review: {reviewed: boolean; reviewerId: string | null; note: string | null};
};
type Finding = {
  id: string;
  ruleId: string;
  criteriaVersion: string;
  status: 'meets' | 'unmet' | 'unknown' | 'conflict' | 'not_applicable' | 'clinical_review';
  fieldIds: string[];
  evidence: Evidence[];
  rationale: string;
  reviewed: boolean;
};
// Also return criteriaCoverage {applicable, evaluated, unresolved},
// authorization {status:'unknown'|'requested'|'approved'|'denied', evidence},
// and reviewVersion. Redacted dates stay null + redacted, not fabricated dates.
```

Use rules from the repository, never a handwritten model-only approximation. Current synthetic frontend assessment states are deliberately smaller than the full contract; normalize backend states explicitly. Do not treat the client export as an authoritative server record.

### Form groups to align with the backend teammate

| IHH form group | Source / extraction approach | Review concerns |
|---|---|---|
| Referring party | Referral form and cover sheet | Redacted identities remain redacted; avoid fabricated contact details. |
| Demographics, insurance, language, housing | Form and face sheet | Record conflicts; no identity inference in event packets. |
| Admission details, wounds, TB/imaging | Chart and referral form | Source notes can contradict the summary; capture arrangements and dates separately. |
| ADLs, mobility, medications, oxygen, infection | PT/OT/nursing and clinical notes | “Independent” must be tied to the actual activity. Medication list alone is insufficient. |
| Behavioral/cognitive status | Relevant chart evidence | Flag ambiguous rules for clinical review. |
| Authorized stay / authorization number | Plan documents | Request ≠ approval; clinical eligibility ≠ payer authorization. |
| Staff-only review and disposition | Human workflow | Reviewed by, dates, approval/denial, reason; preserve review history and responsibility. |
| Referral checklist | Document classification + prerequisites | DOC-10 is a 30-day medication supply, not simply a PDF to detect. Some items apply conditionally. |

## Time-saving measurement plan

Interpret the user's “faster” goal as **reduction in duration**; this differs mathematically from an increase in processing rate.

| Provisional goal | Baseline | Target duration | Minutes saved |
|---|---:|---:|---:|
| 25% less time | 120 min | 90 min | 30 min |
| 50% less time | 120 min | 60 min | 60 min |
| 75% less time | 120 min | 30 min | 90 min |

These are arithmetic scenarios anchored to user input, not validated commitments, vendor benchmarks, or measured prototype results. Prefer 25% as the first experimental threshold; do not promise the larger gains before testing.

Candidate measures considered: active review duration, end-to-end turnaround, extraction latency, field corrections, page searches, completeness, approval rate, and safety/accuracy. Select:

1. **Primary: coordinator active review minutes per completed case.** Sum active intervals between review start/resume and pause/confirm. Explicitly instrument pause; don't infer active work from a background browser tab. Include time to verify and correct extraction. Compare median matched-case manual vs assisted review; report paired differences, sample size, range, and case complexity. Formula: `(manual_minutes - assisted_minutes) / manual_minutes * 100`. Reject missing/zero baselines rather than dividing by zero. This measures staff effort, but alone can hide waiting and rushed decisions.
2. **Secondary: receipt-to-human-disposition elapsed minutes.** Server receipt timestamp to final approve/deny timestamp. Clarification/escalation are intermediate states; report open cases separately, not as fast completions. Separate hospital/authorization waiting from active work. Median and tail latency only after enough observations; the 11 event packets are a small usability/evaluation set.
3. **Guardrails:** (a) critical eligibility evidence missed or unsupported factual claims, adjudicated by an IHH reviewer; (b) factual/citation correctness of reviewed fields and dispositions. Record denominators and failure details. Do not declare safety from agreement with 11 binary labels; no historical rationale is supplied.

Drivers: extraction time/error rate and coordinator correction burden. Do not use approval rate as success: more approvals can reflect wrong rule application. Operational owners: frontend instruments review interactions; backend owns timestamps, versions, and extraction events; IHH clinical reviewer adjudicates quality; team lead compares manual/assisted results.

Experiment: use permitted de-identified packets, independent manual and assisted reviews, counterbalanced packet assignment to reduce learning effects, and include difficult scans/missing documents. Compare the same task scope and case mix. Keep outcome labels hidden until evaluation. Report unfinished/failed analyses, not just completed successes. Browser demo timing must not be represented as clinical-review savings.

The prototype exports a small local event history (demo loaded, source opened, finding/field reviewed, outcome confirmed, draft exported). It does **not** implement active-duration measurement, real receipt timing, or secure telemetry. Backend must add job timestamps, failures, review pause/resume, correction invalidations, and final-disposition semantics.

## Discovery questions to resolve with IHH

- Does “two hours” mean hands-on review, elapsed response time, or both? How much is waiting for clarification or authorization?
- Who fills the hospital referral form, and what does the IHH coordinator re-enter into another system?
- Which fields/documents most often require correction or follow-up?
- Can a coordinator decide independently, and which findings require a clinical escalation?
- What exactly counts as a response within the service promise when the packet is incomplete?
- What criteria establish payer authorization, and what clinical vs administrative blockers can run in parallel?

## Demo script

1. Open the frontend and state that this is a synthetic example, not AI processing of a real packet.
2. Choose **Try a synthetic referral**; show the conflicting transfer statements on pages 1 and 2.
3. Open **Review prefilled form**, confirm/correct a field, and follow its source link.
4. Confirm each finding while preserving unknown/redacted states. Show that a correction needs a reason.
5. Continue; choose clarification, enter initials and a rationale, attest, and confirm.
6. Edit/download the unsent draft and review record. Explain the backend integration points and that approval/full criteria evaluation are not yet implemented.
7. Separately demonstrate local PDF preview, explicitly noting that it does not run analysis.

## Follow-up: original blank form inspected

Read the text of the actual two-page `criteria/source/ihh-recuperative-care-referral-form.pdf` on October 17, 2026, rather than relying solely on the Markdown transcription. Form identifier: RC0725-SH.

- Page 1 contains recuperative-care information, the referral checklist, simplified admission criteria, and the two-hour notification/decision language. Apply the internal criteria precedence described above; do not implement the simplified form as the sole eligibility authority.
- Page 2 instructs the referring party to complete and submit the form with supporting documents. Groups are referring party, patient information, hospital admission details, health/living situation, behavioral/mental health status, and authorized length of stay.
- The separate **ILLUMINATION STAFF ONLY** section contains received date, reviewer, approval yes/no, approval date, authorization number, denial reason, admission date/time, exit date, and extension details.
- Therefore, the automation must distinguish source facts from staff-generated review data. Extracting existing hospital form/chart facts can reduce re-entry; it does not justify manufacturing a staff decision, authorization number, or approval date. Ask IHH which fields they actually re-enter and in which tool before claiming the precise transcription workload is established.
- Upload-to-prefill should capture both a raw extracted value and a reviewer-confirmed value, each with source provenance and status. Administrative receipt/review timestamps come from the real workflow, not dates redacted from the clinical packet.

Attempted the official Google Drive packet folder directly. The proxy returned `Tunnel connection failed: 403 Forbidden`. Added `drive.google.com` and `drive.usercontent.google.com` to the existing network draft without removing earlier domains. This save does not establish runtime access. The large uploaded ZIP and the individual referral packets remain uninspected; no packet-specific clinical conclusions have been made.

## Follow-up: direct packet access succeeded

A subsequent retry on October 17 reached the official Google Drive folder (HTTP 200). Downloaded the folder's `R01.pdf` directly from `drive.usercontent.google.com`; validated the PDF signature and read its metadata: 34 pages, 12,765,188 bytes, not encrypted. It is stored **outside the repository and the development server root**, at `/workspace/ihh-packets-private/R01.pdf`. No publication or runtime-network change was performed by the agent in this retry; observed access succeeded. This supersedes the access blocker above for these two Drive destinations. The uploaded ZIP itself remains uninspected.

Visually inspected **page 2 only** for form structure. It contains a scanned, skewed referral form with handwriting, checkboxes, blacked-out identity/date fields, and a staff-only review section. Its layout and field set differ from the standalone blank RC0725-SH form in `criteria/source/`. This is a structural observation, not a full packet review or eligibility conclusion; no evaluation outcome labels were used. No patient-specific clinical content or packet images are copied into the repository.

Backend implications:

- Support multiple form layouts/versions; do not extract fields solely with fixed x/y positions from the blank form.
- Detect page orientation/skew before extraction while preserving original page references.
- Distinguish checked, unchecked, unreadable, blank, and redacted. An unmarked checkbox is not automatically a negative clinical fact.
- Keep handwriting extraction reviewable and link values to the original image region.
- Preserve the distinction between source-form assertions and corroborating chart evidence. Page 2 alone cannot establish admission eligibility.
- Avoid treating redacted patient/date fields as missing documents or trying to reconstruct them.
