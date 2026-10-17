# Adoption and demo strategy: reduce friction before automating judgment

## Product position

Help an experienced IHH coordinator get to a defensible next step with less searching and re-entry. Preserve their judgment and existing source documents. We do not know what other hackathon teams are building; the following are differentiation hypotheses grounded in the event's manual-review workflow, not claims of uniqueness.

## Angles beyond a PDF summary

1. **Next-action clarity.** Distinguish missing documentation, uncertain clinical evidence, a conflicting source, and an arrangement awaiting confirmation. Each should produce a targeted question or review action. Do not collapse them into a generic failure or red badge.
2. **The second fax.** Once follow-up information arrives, show what changed, which questions it answers, and which reviewed findings become stale. This can reduce repeated reading. It requires document versions and dependency-aware invalidation; not implemented today.
3. **Clinical and operational readiness stay separate.** Evidence supporting clinical criteria is different from authorization, equipment, home-health coordination, or bed availability. Display only confirmed facts and mark other readiness items unknown. Do not promise a placement based on a clinical summary.
4. **Clarification as a useful output.** A concise draft that collects unresolved requests may reduce follow-up work. Test with staff whether requests can be bundled, who receives them, and which items can proceed independently. Do not claim fewer calls without measuring them.
5. **Correctability as a trust feature.** Preserve the original extraction and the coordinator's correction. Show the evidence and why the next step changed. A checked box is not resolution of a failed rule; a correction must invalidate stale outcomes.
6. **Evidence of limits.** Distinguish missing, redacted, conflicting, and unreadable. A failed text search does not establish absence. Avoid unsupported confidence percentages; show the source and its quality limitations.

## Rollout in useful increments

| Stage | What changes for the coordinator | What remains familiar | Exit condition before expanding |
|---|---|---|---|
| 1. Search and source navigation | Search a packet, open the relevant page, record a note | Original paperwork and human decisions | Coordinators can find/check evidence reliably; page-number errors are resolved |
| 2. Verified prefill | Suggested form values with page citations and explicit unknowns | Staff verify and correct the form | Correction burden is lower than the re-entry work saved; no unsupported identity/date values |
| 3. Completeness and contradictions | System flags unresolved items across documents | Staff decide what matters and what to ask | Critical gaps are not hidden; staff can resolve or escalate every flag |
| 4. Draft follow-up | Prepare an editable clarification/disposition draft from reviewed evidence | Existing communication process; no automatic send | Staff say drafts reduce editing and follow-up work; corrections invalidate drafts |
| 5. New-information review | Diff follow-up packets and reopen affected findings | Human confirmation and clinical escalation | Version/citation integrity and stale-decision tests pass |

These are stages with quality gates, not a calendar promise. Trial a stage alongside the existing process with a small group of willing coordinators. Let them stop using an unhelpful feature. Capture corrections as product feedback, not automatic clinical-policy changes. Avoid forced duplicate entry in a pilot: agree which record remains authoritative and how verified results move into it.

## Competition demonstration

Aim for one complete, understandable scenario rather than a broad menu of disconnected features:

1. Explain the manual-review friction and show the real packet structure, using only permitted de-identified material.
2. Search for an item and jump to the original page. Demonstrate that the source remains available.
3. Show a separately labeled synthetic example of conflicting evidence; do not present a fixture as model-generated analysis of the uploaded packet.
4. Show the coordinator recording uncertainty and preparing a focused clarification.
5. Change a review note and show the earlier draft becoming invalid. This demonstrates that human review has consequences.
6. State exactly what is implemented: real local PDF/text processing and review flow; clinical extraction and full eligibility are not connected. Give the next implementation step.

Use measured review task time and correctness where available. A rapid UI interaction is not evidence of a 25–75% clinical time reduction. The user-reported 120-minute baseline is provisional; the repo's two-hour response promise measures a potentially different interval.

## Questions for IHH before a pilot

- What part of the work feels most repetitive: searching, re-entry, criteria checking, or follow-up?
- Which sources and staff judgments are trusted today?
- What information most often arrives in a second packet?
- Which next actions can happen in parallel, and who owns each?
- Where must the final reviewed record live so the tool does not introduce another inbox?
- Which errors would cause staff to stop trusting the tool?

## Current implementation versus next work

Implemented locally: upload validation, page rendering, native text/OCR, original-page preservation, packet search, page review notes, guarded clarification/escalation, and stale-draft invalidation. No model/API key is needed for this step.

Not yet implemented: model-generated clinical form prefill, full criteria evaluation, follow-up document diff, authorization/bed feeds, production authentication/storage, or public backend hosting. The GitHub Pages site remains a static frontend with a separate synthetic demonstration; it does not process uploaded packets on a remote backend.
