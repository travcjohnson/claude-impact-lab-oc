# LOOP-05 validation and rehearsal (readiness gate, not a clinical claim)

Nothing here shows the extraction is clinically reliable. It shows which software behaviours are repeatable on synthetic data, what has **not** been run, and what must happen before real clinical use.

## Run it
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements-dev.txt
PYTHONPATH=. python -m backend.rehearsal --out /tmp/rehearsal.json   # synthetic only; no credentials; exit 0 if all pass
PYTHONPATH=. python -m unittest backend.tests.test_rehearsal -v
```
Use `--out` for machine-readable JSON: some PyMuPDF versions print a deprecation banner to stdout when `backend/app.py` imports `fitz`.

Optional real-adapter section, only with permitted inputs and secrets supplied outside Git:
```bash
export IHH_ANALYSIS_ADAPTER=backend.<module>:build_adapter IHH_ANALYSIS_MODEL=<verified id> ANTHROPIC_API_KEY=<from your secret store>
PYTHONPATH=. python -m backend.rehearsal --real /path/to/approved/pdfs
```
It reports `NOT RUN` (with the missing variable *names*, never values) unless all are present. A real run prints only counts and error codes: no text, quotes, values or filenames. Do not paste its output into issues if the packets are event material; counts are safe, anything else is not.

## What the synthetic rehearsal demonstrates (17 checks)
| Acceptance item | Check | Status |
|---|---|---|
| Citations, missing/redacted fields | every cited page opens and the quote is on that exact page; redacted field keeps no value | Run, passes |
| Blank / failed pages | blank page flagged; all-blank packet never reaches analysis | Run, passes |
| Extraction failures | invalid response, timeout, adapter unavailable: no fabricated fields, manual review still works | Run, passes |
| Retry without duplicates | identical confirmation resent after "timeout" is an idempotent replay; invalid uploads create no referral | Run, passes |
| No lost edits | stale competing edit gets 409 and changes nothing; edit after confirmation invalidates draft and export | Run, passes |
| No unsupported eligibility claim | approve refused; export unsent, keeps the unresolved field; authorization stays unknown | Run, passes |
| Active vs waiting time | timing returns active, processing, elapsed separately; unknown is null; `savingsPercent` is null | Run, passes |

Covered by pre-existing tests, not duplicated: validator rejections, bounded retry (`test_analysis.py`), rotation and native-text fallback (`test_pages.py`), timing arithmetic (`test_timing.py`), blind scoring (`test_evaluation.py`).

## Not run (honest list)
- Real adapter on real packets: no approved inputs/credentials were available in this session.
- Scanned/rotated **real** faxes through real OCR: only invented PDFs were used. OCR is stubbed in the rehearsal.
- Blind evaluation scoring: separate procedure (`backend/evaluation.py`); labels were not read.
- Manual-vs-assisted comparison, sample size, quality checks: needs real staff time. No time saving is claimed and none can be inferred from this rehearsal.
- Browser walkthrough: no frontend change here; `backend/tests/browser.cjs` needs Playwright/Chromium.
- Python 3.12: ran on 3.10.

## Known failure modes still open
- Server memory only: restart loses everything (see LOOP-06 #27).
- Reviewer labels are free text, not identity.
- Quote verification is a text match; it cannot prove the model read a handwritten or checkbox mark correctly.
- Time-window rules on redacted dates depend on the extractor's own logic; no generic test can prove them.
- Search terms can appear in access logs if the server runs with default uvicorn access logging; start with `--no-access-log` (already in the test plan).
- Existing failing test on the base branch: `test_evaluation.SuggestTests.test_never_opens_the_labels_file` (unrelated, pre-existing).

## Staff validation and sign-off before any real clinical workflow
1. IHH names an accountable clinical owner and an intake owner; neither is the builder.
2. Blind evaluation on approved packets, with every disagreement reviewed by a clinician. Agree acceptable miss rates for each rule *before* looking at results.
3. Side-by-side timing: coordinators do equivalent packets manually and assisted; record sample size, active vs waiting time, corrections and missed critical items separately.
4. Failure drills with staff: OCR failure, model outage, conflicting sources, redaction, stale edit.
5. Written decisions on data handling (approved AI data processing, retention, access) and a supported destination for outputs.
6. Pilot narrowly (one coordinator, alongside the existing process), reviewed export only, no automatic decisions.
Sign-off is a human decision recorded outside this repo; this document grants none.
