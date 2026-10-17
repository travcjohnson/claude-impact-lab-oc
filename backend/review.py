"""BE-04: field-level human review, allowed actions, and the reviewed export.

Pure functions over one packet record. The caller holds the service lock and passes a private copy,
so a rejected request never leaves a half-applied edit. Nothing here calls a model.

Policy (conservative on purpose; clinical override policy is NOT established, so we escalate instead):
* The original extraction (`field['value']`, status, evidence) is never overwritten. A human
  correction is stored beside it in `field['review']`, with reviewer label, reason, source page and history.
* A field can be marked `verified` only if its original status was `extracted`. Missing, redacted,
  conflicting and unreadable fields stay open for clarification; ticking "checked" cannot resolve them.
* A redacted value cannot be reconstructed; the only accepted value is "unknown".
* Any field review bumps the version and clears the confirmed outcome (so the draft and export vanish).
  Findings that depend on a field are marked stale only when that field's effective value changes.
* Approve/deny stay unavailable. `allowed_actions` says why, in static strings (no document text).
* Reviewer labels are local demo labels. `reviewerId` stays null: there is no authentication, and the
  history lives in server memory only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.analysis import ID_RE

UNKNOWN = 'unknown'
MIN_CORRECTION_NOTE = 12
STALE_MESSAGE = 'Review changed. Reload the latest version.'
LABEL_NOTE = 'Reviewer labels are local demo labels, not authenticated identity. History is not durable.'


class FieldReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    value: str = Field(min_length=1, max_length=4000)      # use "unknown" rather than leaving it blank
    assessment: Literal['verified', 'unresolved']
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(default='', max_length=4000)
    page: int | None = Field(default=None, ge=1)            # source page that supports the correction

    @field_validator('value', 'reviewer', 'note', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).lower() if isinstance(value, bool) else str(value)


def _reject(status: int, detail: str):
    raise HTTPException(status, detail)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def find_field(record: dict, field_id: str) -> dict:
    if not ID_RE.match(field_id or ''):
        _reject(404, 'Unknown field.')
    for field in record['formFields']:
        if field['id'] == field_id:
            return field
    _reject(404, 'Unknown field.')


def effective_value(field: dict):
    review = field['review']
    return review['effectiveValue'] if review.get('reviewed') else field['value']


def apply_field_review(record: dict, field_id: str, body: FieldReviewInput, now=now_iso) -> dict:
    """Mutates `record` (a private copy) or raises HTTPException. Returns the change summary."""
    if body.version != record['version']:
        _reject(409, STALE_MESSAGE)
    if record['job']['state'] != 'text_ready':
        _reject(409, 'Wait for document processing to finish.')
    if record['analysis']['status'] != 'needs_review' or not record['formFields']:
        _reject(409, 'There are no analysis fields to review. Use page notes for manual review.')
    field = find_field(record, field_id)
    status, original = field['status'], field['value']
    value = body.value

    if status == 'redacted' and value.lower() != UNKNOWN:
        _reject(422, 'Redacted values cannot be reconstructed. Enter "unknown" and route to an authorized reviewer.')
    if body.assessment == 'verified' and status != 'extracted':
        _reject(422, f'This field was originally {status}, so it cannot be marked verified. '
                     'Keep it unresolved and request clarification or clinical review.')
    original_text = _text(original)
    corrected = (value != original_text) if original_text is not None else (value.lower() != UNKNOWN)
    effective_before = effective_value(field)
    effective_after = value if corrected else original
    changed = effective_after != effective_before
    if corrected or changed:
        if len(body.note) < MIN_CORRECTION_NOTE:
            _reject(422, f'Explain the correction in at least {MIN_CORRECTION_NOTE} characters.')
        if changed and field['review'].get('reviewed') and body.note == field['review'].get('note'):
            _reject(422, 'Add a new explanation for this change; the previous note describes an earlier value.')
        if body.page is None:
            _reject(422, 'Name the source page that supports the correction.')
    if body.page is not None and body.page > len(record['pages']):
        _reject(422, 'Page does not exist in this document.')

    before = field['review']
    effective_before = effective_value(field)
    effective_after = value if corrected else original
    new_version = record['version'] + 1
    entry = {
        'at': now(), 'version': new_version, 'reviewerLabel': body.reviewer, 'sourcePage': body.page,
        'before': {'effectiveValue': effective_before, 'assessment': before.get('assessment'),
                   'note': before.get('note'), 'reviewerLabel': before.get('reviewerLabel')},
        'after': {'effectiveValue': effective_after, 'assessment': body.assessment, 'note': body.note or None,
                  'reviewerLabel': body.reviewer},
    }
    field['review'] = {
        'reviewed': True, 'reviewerId': None, 'reviewerLabel': body.reviewer, 'note': body.note or None,
        'assessment': body.assessment, 'correctedValue': value if corrected else None,
        'effectiveValue': effective_after, 'sourcePage': body.page, 'version': new_version,
        'history': [*before.get('history', []), entry],
    }

    stale_ids = []
    if effective_after != effective_before:
        for finding in record['findings']:
            if field_id in finding['fieldIds']:
                finding.update(stale=True, reviewed=False,
                               staleReason=f'Field {field_id} was corrected after this finding was generated.')
                stale_ids.append(finding['id'])
    had_outcome = record['outcome'] is not None
    record['version'] = new_version
    record['outcome'] = None
    return {'fieldId': field_id, 'version': new_version, 'invalidatedFindingIds': stale_ids,
            'invalidatedConfirmation': had_outcome, 'invalidatedDraftAndExport': had_outcome}


def blockers(record: dict) -> dict:
    fields = record['formFields']
    return {
        'unreviewedFieldIds': [f['id'] for f in fields if not f['review'].get('reviewed')],
        'unresolvedFieldIds': [f['id'] for f in fields
                               if f['review'].get('reviewed') and f['review'].get('assessment') != 'verified'],
        'staleFindingIds': [f['id'] for f in record['findings'] if f.get('stale')],
    }


def allowed_actions(record: dict) -> dict:
    """What the person may do now, and why not. Reasons are static text, never document content."""
    ready = record['job']['state'] == 'text_ready'
    analysis = record['analysis']['status']
    fields, b = record['formFields'], blockers(record)
    wait = [] if ready else ['Wait for document processing to finish.']

    field_reasons = list(wait)
    if analysis != 'needs_review' or not fields:
        field_reasons.append(f'There are no analysis fields to review (analysis is {analysis}). Use page notes.')

    confirm = list(wait)
    if analysis in ('queued', 'checking'):
        confirm.append('Analysis is still running.')
    if not record['reviews']:
        confirm.append('Save a page review note first.')
    if b['unreviewedFieldIds']:
        confirm.append(f"Review every extracted field ({len(b['unreviewedFieldIds'])} not yet reviewed).")

    decision = ['Admission decisions are disabled in this prototype; approval and denial need complete rule '
                'evaluation and review gates that do not exist yet.']
    if analysis != 'needs_review':
        decision.append(f'Clinical analysis has not produced a result for review (analysis is {analysis}).')
    if not record['criteriaCoverage'].get('complete'):
        decision.append('Applicable-rule coverage is incomplete.')
    if b['unreviewedFieldIds'] or b['unresolvedFieldIds']:
        decision.append('Some fields are unreviewed or unresolved.')
    if b['staleFindingIds']:
        decision.append('Some findings are stale after a correction.')
    deny = decision + ['Denial would need a reviewed reason and a reviewed unmet applicable criterion; none exists.']

    confirmed = ['No current confirmed next step. Review and confirm first.'] if record['outcome'] is None else []
    return {
        'savePageNote': {'allowed': not wait, 'reasons': wait},
        'saveFieldReview': {'allowed': not field_reasons, 'reasons': field_reasons},
        'confirmNextStep': {'allowed': not confirm, 'reasons': confirm, 'decisions': ['clarification', 'clinical-review']},
        'approve': {'allowed': False, 'reasons': decision},
        'deny': {'allowed': False, 'reasons': deny},
        'draft': {'allowed': not confirmed, 'reasons': confirmed},
        'export': {'allowed': not confirmed, 'reasons': confirmed},
        'blockers': b,
    }


def with_actions(record: dict) -> dict:
    record['allowedActions'] = allowed_actions(record)
    return record


def _item(field: dict) -> dict:
    review = field['review']
    return {'id': field['id'], 'originalValue': field['value'], 'originalStatus': field['status'],
            'effectiveValue': effective_value(field), 'correctedValue': review.get('correctedValue'),
            'assessment': review.get('assessment'), 'reviewerLabel': review.get('reviewerLabel'),
            'note': review.get('note'), 'sourcePage': review.get('sourcePage'),
            'evidence': field['evidence'], 'alternatives': field['alternatives'],
            'history': review.get('history', [])}


def build_export(record: dict) -> dict:
    """The current human-confirmed snapshot. Caller guarantees `record['outcome']` is current."""
    out, analysis = record['outcome'], record['analysis']
    verified = {f['id'] for f in record['formFields']
                if f['review'].get('reviewed') and f['review'].get('assessment') == 'verified'}
    confirmed = [_item(f) for f in record['formFields'] if f['id'] in verified]
    unresolved = [_item(f) for f in record['formFields'] if f['id'] not in verified]
    return {
        'mode': 'local-review-export', 'referralId': record['referralId'], 'version': record['version'], 'sent': False,
        'analysis': {k: analysis.get(k) for k in ('status', 'synthetic', 'adapter', 'model', 'contractStatus')},
        'nextStep': {'decision': out['decision'], 'reviewerLabel': out['reviewer'], 'rationale': out['rationale'],
                     'confirmedAt': out.get('confirmedAt')},
        'confirmedFields': confirmed,
        'unresolved': {'fields': unresolved,
                       'staleFindingIds': blockers(record)['staleFindingIds'],
                       'unresolvedRuleIds': record['criteriaCoverage'].get('unresolved', []),
                       'coverageComplete': bool(record['criteriaCoverage'].get('complete'))},
        'unreviewedMachineFindings': [{'id': f['id'], 'ruleId': f['ruleId'], 'status': f['status']}
                                      for f in record['findings'] if not f.get('stale')],
        'pageNotes': record['reviews'],
        'authorization': {'status': record['authorization'].get('status'), 'established': False},
        'clinicalEligibility': 'not evaluated',
        'notes': [LABEL_NOTE, 'Nothing has been sent. Authorization and clinical eligibility are not established.']
                 + (['Analysis output is a SYNTHETIC fixture, not real extraction.'] if analysis.get('synthetic') else []),
    }


def draft_sections(record: dict) -> list[str]:
    """Extra draft lines built from the reviewed snapshot; empty when no analysis fields exist."""
    if not record['formFields']:
        return []
    verified = {f['id'] for f in record['formFields']
                if f['review'].get('reviewed') and f['review'].get('assessment') == 'verified'}
    confirmed = [f for f in record['formFields'] if f['id'] in verified]
    open_items = [f for f in record['formFields'] if f['id'] not in verified]

    def line(f):
        pages = sorted({e['page'] for e in f['evidence']} | ({f['review']['sourcePage']} if f['review'].get('sourcePage') else set()))
        shown = effective_value(f)
        return f"- {f['id']}: {UNKNOWN if shown is None else shown} (original: {f['status']}; page(s): {', '.join(map(str, pages)) or 'none cited'})"

    lines = ['', 'CONFIRMED BY REVIEWER' if confirmed else 'CONFIRMED BY REVIEWER: none', *map(line, confirmed)]
    lines += ['', 'OPEN / UNRESOLVED (needs clarification or clinical review)' if open_items else 'OPEN / UNRESOLVED: none',
              *map(line, open_items)]
    if blockers(record)['staleFindingIds']:
        lines += ['', 'Some machine findings were invalidated by corrections and are not included.']
    return lines
