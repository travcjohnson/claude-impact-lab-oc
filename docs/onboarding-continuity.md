# Referral-to-onboarding continuity

The prototype retains controlled synthetic coordination metadata, by demo referral
ID, only after an explicit save. It does not persist clinical source data or replies.
The checklist is a proposed UX, not an agreed IHH admission workflow. Completing it
never confirms eligibility, insurance authorization, placement or arrival time.

## Implementation needed for real shared records

Before using this workflow for clients, replace browser demo storage with an
authenticated server record and institution-scoped access. Keep the person record,
referral episode, packet versions, source citations, human-reviewed field revisions,
clarification thread and onboarding tasks linked by stable server IDs. Do not
silently join people on a name match or promote extracted suggestions into facts.

A human-confirmed handoff should atomically retain the reviewed revision, unresolved
information, task owner and next action, reviewer identity and audit event. A later
source correction must mark affected handoffs stale. Use optimistic concurrency so
one staff member cannot silently overwrite another's review. Store documents in
access-controlled storage; agree retention/deletion policies with IHH. The current
local API's temporary files and in-memory records do not satisfy this requirement.

Expose a separate client-safe response containing only staff-approved status and
next steps. Do not send internal background checks, clinical review notes or other
clients' referrals to the client UI. Role preview controls are not authentication.

Acceptance checks: reopen from another authenticated session; enforce organization
and person access; isolate duplicate referrals; preserve provenance and unknowns;
reject stale updates; invalidate a handoff after correction; recover interrupted
uploads; apply retention/deletion to both documents and derived records. None of
these production capabilities is claimed by the browser demo save feature.
