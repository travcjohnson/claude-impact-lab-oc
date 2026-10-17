# PR #1 review triage

Review against the integration branch on October 17, 2026. Automated comments were checked against current source, not treated as instructions or proof. No teammate feature PR or Natal design branch was visible at review time; unseen work has not been reviewed.

## Frontend findings addressed

- PDF preview MIME/isolation: explicitly create an application/pdf blob and sandbox the iframe. Provide a PDF download fallback for browsers that cannot render an isolated preview. Synthetic MIME-confusion browser check covers this.
- Finding drafts lost under zoom/page controls: retain draft status/note separately, invalidate review and confirmation on edit.
- Outcome rationale and editable response lost under navigation: retain in session state; changes to evidence require renewed attestation.
- Unknown/conflicting/redacted examples becoming definitive failure/success: validate against fixed-source-supported transitions. These fixed examples cannot establish an unmet criterion through a note alone.
- Correction explanations reused/removed: preserve original status/value; require explanations for corrections, including returning to the original value, and a fresh note for a subsequent correction.
- Global navigation bypassing local review guard: shared can-leave guard plus browser unload protection. Existing local draft retention and 409 recovery remain tested.
- Local static server exposed on all interfaces: frontend startup now defaults to 127.0.0.1.
- Deployment ordering: latest-wins concurrency covers the entire deployment workflow, with a separate group for each PR. An older push/manual run cannot continue building while a newer deployment run proceeds in the same group.
- Local search response: reject invalid/out-of-range original-page references before rendering result links. Clinical schema mismatch remains explicit.

Earlier local note/rationale/draft retention findings were already addressed in 3e8dded and are regression-tested. These are implementation results, not a blanket resolution of all PR review threads.

## Remaining owner work

| Finding | Owner / ticket | Status |
|---|---|---|
| Mobile sidebar hides guide/task navigation | Natal, FE-01 #9 / FE-02 #10 | Add a mobile navigation path in her design lane; do not remove accessibility or mock context. No pushed design changes yet. |
| Short native text lost if OCR unavailable | Harjeev, BE-02 #3 | Preserve available native text with explicit quality/error flags; verify implementation when pushed. |
| Search query terms in default access logs | Vibhu, BE-01 #2 | Choose a logging/request policy that avoids packet terms in logs; no contract change by frontend alone. Current test-plan startup uses --no-access-log. |
| API access boundary and review identity | Vibhu, BE-01 #2 / BE-04 #5 | Loopback and host/origin guards exist; they are not authentication or production authorization. |
| Backend browser test hardcodes Chromium path | Vibhu, BE-06 #7 | Honor documented runtime override; do not assume /usr/bin/chromium on every teammate machine. |
| Packet-derived archive in history/diff | Team lead with BE-07 #8 owners | Existing documented handling question remains. No history rewrite, removal of teammates' work or claim of organizer approval made here. |

[Acceptance checklist](integration-acceptance.md) separates current regression checks from backend integration gates that are still pending. No time-saving or clinical-accuracy claim follows from passing synthetic tests.
