# Careward · Referral coordination

Approved product name: Careward. Keep IHH attribution and the prototype/synthetic labels. The name has not been checked for trademark or domain availability.

## Visual conventions

- Preserve deep green navigation (#173f36), primary actions (#245d4d), warm white surfaces and muted green backgrounds.
- Source Sans 3 is self-hosted from @fontsource-variable/source-sans-3 5.3.1 (Latin variable normal WOFF2, SIL Open Font License bundled under frontend/assets). No runtime font CDN or extra JavaScript dependency. System fallback covers characters outside the bundled subset.
- Body text 16px, explanatory text 16–17px, headings 30–36px, section headings 21–24px. Semibold for hierarchy; uppercase is limited to small context labels. Document facsimiles may retain serif text.
- Use dividers and spacing to separate work, modest 6–10px corners and one primary action per section. Avoid decorative stars, marketing headlines and repetitive numbered feature cards inside the workspace.
- Keep role identity and demo scope visible. Mobile navigation remains available instead of disappearing. Minimum primary control height 44px, visible keyboard focus, readable status text and responsive stacking.

## Presentation handoff

The coordinator implemented this visual pass in frontend/styles.css, index.html, app.js, backend-client.js and team/index.html at the user's request. Natal should rebase her presentation lane onto the latest integration branch before further CSS/index changes. Preserve existing control IDs and behavior. The final Careward CSS section overrides the earlier prototype styles; consolidate rules during a later focused stylesheet cleanup.

The backend static allowlist, build script and Pages artifact allowlist include only the specific font and license files. Preserve that narrow allowlist.

This pass refines the existing upload/review/role screens. A real multi-referral work queue still needs a backend listing contract, authorized scope and real workflow statuses; it is not implemented by this visual update.

Validation: frontend unit suite, build, role/mobile workflow, synthetic demo, field review, API recovery and backend suite passed. Confirmed the local server loads the actual font and inspected desktop/client mobile screenshots using synthetic content.


## Readability follow-up

The application now uses the platform system sans-serif stack for a wider, familiar
reading face, with a consistent 16px body, 14px labels and restrained heading weights.
Green palette remains unchanged. Source Sans assets remain packaged for existing
references. Coordination tasks include visible explanations and associated help text;
the tablet layout stacks these panels and the inbox table fits its available width.
This stylesheet update follows Aaron’s explicit typography request; reconcile it
with Neetal’s presentation changes when her branch is available.
