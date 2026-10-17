# Role workspaces — frontend prototype

The visible role selector previews three audiences. It is not authentication or authorization. All external-role content is synthetic, remains in the browser, and is separate from the local PDF/staff review state.

- Person receiving care: plain-language example status, next steps and questions to ask their existing care team. No clinical findings, packet upload, internal review tools, invented contacts, placement promises or outgoing messages.
- Hospital referral staff: synthetic packet preparation and simulated handoff. Receipt is explicitly unconnected; nothing is added to IHH's queue.
- IHH intake staff: existing source review, corrections, confirmation and unsent draft workflow. Role changes respect the local review's unsaved-work confirmation; synthetic staff review state is retained when returning.

## Backend work before real use

Identity must come from an authenticated server session, with verified organization membership. Do not trust the browser role selector or a role sent in request JSON. Authorize each referral/document endpoint: the person receiving care sees only their own approved status/actions; hospital staff see only authorized referrals for their organization; IHH staff receive explicitly assigned permissions. Test cross-person and cross-organization access denial, including document URLs and exports.

Define separate response shapes for client-facing status, hospital handoff and internal review. Do not return internal findings, staff notes or full packets to the client view and merely hide them in HTML. Agree which statuses staff publish, what consent/access delegation is required, how identities are verified and how corrections are audited. Use a server acknowledgment for submissions; never present a local click as successful delivery. Actual messages and IHH connections remain outside this event prototype.

Frontend validation: `node frontend/tests/roles-browser.cjs` with the local backend serving the UI. This uses synthetic fixtures and tests role-specific actions, preserved staff state, mobile overflow and unsaved-note protection.
