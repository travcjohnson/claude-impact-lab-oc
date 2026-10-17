# Frontend lanes — Team 1

Both lanes start task branches from the latest `origin/codex/frontend-live`, not `main`, and open PRs back to `codex/frontend-live`. Preserve local work before changing bases. No force-push or automatic merge. GitHub Issues is the primary tracker; the site board is a navigation snapshot.

| Lane | Owner | Files | Tickets |
|---|---|---|---|
| Presentation and accessibility | Natal, @neetalp | `frontend/styles.css`, `frontend/index.html`, optional new `frontend/tests/presentation-browser.cjs` | [FE-01 #9](https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1/issues/9), then [FE-02 #10](https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1/issues/10) |
| Integration and review behavior | @phileokairos-pixel with Codex | `frontend/backend-client.js`, `app.js`, `field-review.js`, `field-review-model.js`, existing behavior tests | [FE-03 #11](https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1/issues/11), then [FE-04 #12](https://github.com/phileokairos-pixel/claude-impact-lab-oc---team-1/issues/12) |

Natal can begin immediately with the existing synthetic demo and local OCR UI. The integration lane waits for the agreed BE-03/BE-04 schema/API before wiring real extracted fields; no invented competing contract. Visual polish must retain uncertainty, mock labels and unavailable clinical actions.

Shared interface rule: preserve existing IDs/data attributes and semantics used by JavaScript/tests. Natal proposes exact dynamic-markup changes through her PR; the integration owner coordinates those JS changes. Likewise, the integration owner requests CSS/layout changes from Natal. This lets accessibility defects get fixed without simultaneous broad edits to the same files. Confirm proposed new selectors before implementation.

Each PR includes scope, changed files, tests and known limitations. Run frontend tests and the static build; verify desktop/mobile and relevant keyboard or error flows using synthetic data. Screenshot evidence must contain no patient data. Do not claim runtime AI/extraction from a fixture.

The static build publishes only an explicit allowlist. Coordinate new assets with the integration owner and workflow allowlist. Pages Actions activation is separately dependent on repository settings; a successful merge does not prove a successful deployment. No public backend is hosted by Pages.

Repository write access is verified for @neetalp. Access to a private user-owned GitHub Project is separate and cannot be verified by this integration; the Project owner must grant it if needed.
