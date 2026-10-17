"""LOOP-02: attach a clarification request and a (simulated) response to the ORIGINAL referral.

Pure functions over one packet record, same contract as `backend.review`: the caller holds the service
lock and passes a private copy, so a rejected call never leaves a half-applied edit. Each operation
mutates that copy or raises HTTPException, and returns an explicit change summary for the persistence
layer (LOOP-01 / #22). Nothing here touches app.py, a database, a model, or any outgoing channel.

Policy:
* States: `waiting` -> `response_needs_review` -> `reviewed`. `reviewed` means a person looked at the new
  evidence and re-reviewed the affected fields. It does NOT mean clinically resolved or eligible.
* A response never changes a field's original value, status, evidence or redaction. New evidence is stored
  beside the field (`field['followUpEvidence']`); a person still corrects via `review.apply_field_review`.
* New evidence reopens the affected fields (`review.reviewed` -> False, history kept), marks dependent
  findings stale, and clears the confirmed outcome (so draft and export vanish). If a request names no
  fields we cannot map the effect, so ALL fields are reopened with an explicit reason.
* Responses must cite a document that belongs to THIS referral. Cross-referral references, stale versions
  and conflicting duplicate retries are rejected; an identical retry (same idempotency key) is a no-op.
* The responder is an explicit synthetic stand-in. `synthetic: false` is rejected: no claim of real
  hospital identity or authentication, and nothing is sent (`sent` is always False).
* This module never confirms an outcome and never marks eligibility.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.analysis import ID_RE
from backend.review import STALE_MESSAGE, effective_value, now_iso

WAITING, NEEDS_REVIEW, REVIEWED = 'waiting', 'response_needs_review', 'reviewed'
MIN_NOTE = 12


class Citation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    page: int = Field(ge=1)
    quote: str | None = Field(default=None, max_length=2000)      # None keeps a redacted/unreadable page honest
    sourceQuality: Literal['readable', 'unreadable', 'redacted'] = 'readable'


class DocumentRef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    documentId: str = Field(pattern=ID_RE.pattern)
    referralId: str = Field(pattern=ID_RE.pattern)                 # the referral this document claims to belong to
    version: int = Field(ge=1)
    pageCount: int = Field(ge=1, le=500)
    sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


class Responder(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=80)
    synthetic: bool


class RequestInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    idempotencyKey: str = Field(pattern=ID_RE.pattern)
    question: str = Field(min_length=1, max_length=2000)
    fieldIds: list[str] = Field(default_factory=list, max_length=50)
    requester: str = Field(min_length=1, max_length=80)

    @field_validator('question', 'requester', mode='before')
    @classmethod
    def trim(cls, v):
        return v.strip() if isinstance(v, str) else v


class ResponseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    idempotencyKey: str = Field(pattern=ID_RE.pattern)
    responder: Responder
    text: str = Field(default='', max_length=4000)                  # may be empty: "no information available"
    document: DocumentRef | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=50)

    @field_validator('text', mode='before')
    @classmethod
    def trim(cls, v):
        return v.strip() if isinstance(v, str) else v


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(min_length=1, max_length=4000)

    @field_validator('reviewer', 'note', mode='before')
    @classmethod
    def trim(cls, v):
        return v.strip() if isinstance(v, str) else v


def _reject(status: int, detail: str):
    raise HTTPException(status, detail)


def _state(record: dict) -> dict:
    return record.setdefault('followUp', {'requests': []})


def find_request(record: dict, request_id: str) -> dict:
    for item in _state(record)['requests']:
        if item['id'] == request_id:
            return item
    _reject(404, 'Unknown follow-up request.')


def _check_writable(record: dict, version: int):
    if version != record['version']:
        _reject(409, STALE_MESSAGE)
    if record['job']['state'] != 'text_ready':
        _reject(409, 'Wait for document processing to finish.')


def _bump(record: dict) -> tuple[int, bool]:
    had_outcome = record['outcome'] is not None
    record['version'] += 1
    record['outcome'] = None
    return record['version'], had_outcome


def create_request(record: dict, body: RequestInput, now=now_iso) -> dict:
    """Open a clarification request. Waiting for a reply does not change any evidence, so reviewed fields
    stay reviewed; the version still advances so concurrent editors notice."""
    state = _state(record)
    prior = next((r for r in state['requests'] if r['idempotencyKey'] == body.idempotencyKey), None)
    if prior:
        same = (prior['question'], prior['fieldIds'], prior['requester']) == (body.question, body.fieldIds, body.requester)
        if not same:
            _reject(409, 'This idempotency key was already used for a different request.')
        return {'requestId': prior['id'], 'version': record['version'], 'replay': True, **_none_changed()}
    _check_writable(record, body.version)
    known = {f['id'] for f in record['formFields']}
    if len(set(body.fieldIds)) != len(body.fieldIds) or any(i not in known for i in body.fieldIds):
        _reject(422, 'Request names a field that is not on this referral.')
    request_id = f'q-{len(state["requests"]) + 1}'
    new_version = record['version'] + 1
    record['version'] = new_version
    state['requests'].append({
        'id': request_id, 'referralId': record['referralId'], 'state': WAITING, 'idempotencyKey': body.idempotencyKey,
        'question': body.question, 'fieldIds': list(body.fieldIds), 'requester': body.requester,
        'createdAt': now(), 'createdAtVersion': new_version, 'sent': False, 'responses': [],
    })
    return {'requestId': request_id, 'version': new_version, 'replay': False, **_none_changed()}


def _none_changed() -> dict:
    return {'reopenedFieldIds': [], 'invalidatedFindingIds': [], 'invalidatedConfirmation': False,
            'invalidatedDraftAndExport': False, 'reopenReason': None}


def record_response(record: dict, request_id: str, body: ResponseInput, now=now_iso) -> dict:
    """Attach a simulated reply (and optional source document) to the original referral."""
    req = find_request(record, request_id)
    prior = next((r for r in req['responses'] if r['idempotencyKey'] == body.idempotencyKey), None)
    if prior:
        if prior['payload'] != body.model_dump():
            _reject(409, 'This idempotency key was already used for a different response.')
        return {'requestId': request_id, 'responseId': prior['id'], 'version': record['version'], 'replay': True,
                **_none_changed()}
    _check_writable(record, body.version)
    if not body.responder.synthetic:
        _reject(422, 'Only the explicit synthetic responder is supported. Real responder identity is not verified.')
    if req['state'] != WAITING:
        _reject(409, 'This request already has a response. Review it before sending another request.')
    doc = body.document
    if doc is not None:
        if doc.referralId != record['referralId']:
            _reject(422, 'Document belongs to a different referral and cannot be attached here.')
        if any(d['documentId'] == doc.documentId and d['version'] == doc.version
               for r in _state(record)['requests'] for x in r['responses'] for d in [x['document']] if d):
            _reject(409, 'This document version is already attached to the referral.')
    elif body.citations:
        _reject(422, 'Citations need an attached document.')
    for c in body.citations:
        if doc and c.page > doc.pageCount:
            _reject(422, 'Citation page does not exist in the attached document.')
        if c.sourceQuality != 'readable' and c.quote:
            _reject(422, 'A redacted or unreadable page cannot carry a quote.')
    if not body.text and doc is None:
        _reject(422, 'A response needs text, a document, or both. An empty reply stays unrecorded; the question remains open.')

    response_id = f'{request_id}-r{len(req["responses"]) + 1}'
    new_version, had_outcome = _bump(record)
    document = None if doc is None else doc.model_dump()
    citations = [c.model_dump() for c in body.citations]
    req['responses'].append({
        'id': response_id, 'idempotencyKey': body.idempotencyKey, 'payload': body.model_dump(), 'receivedAt': now(),
        'atVersion': new_version, 'responder': body.responder.model_dump(), 'text': body.text,
        'document': document, 'citations': citations, 'sent': False,
    })
    req['state'] = NEEDS_REVIEW

    mapped = bool(req['fieldIds'])
    targets = [f for f in record['formFields'] if (f['id'] in req['fieldIds'] if mapped else True)]
    reason = (f'New evidence arrived for request {request_id} (response {response_id}); re-check this field against it.'
              if mapped else
              f'Response {response_id} to request {request_id} did not name affected fields, so all fields were '
              'reopened conservatively.')
    reopened, stale_ids = [], []
    for f in targets:
        f.setdefault('followUpEvidence', []).append(
            {'responseId': response_id, 'requestId': request_id, 'document': document, 'citations': citations})
        if f['review'].get('reviewed'):
            f['review'] = {**f['review'], 'reviewed': False, 'reopenReason': reason, 'reopenedAtVersion': new_version}
            reopened.append(f['id'])
    target_ids = {f['id'] for f in targets}
    for finding in record['findings']:
        if target_ids & set(finding['fieldIds']):
            finding.update(stale=True, reviewed=False, staleReason=reason)
            stale_ids.append(finding['id'])
    return {'requestId': request_id, 'responseId': response_id, 'version': new_version, 'replay': False,
            'reopenedFieldIds': reopened, 'invalidatedFindingIds': stale_ids, 'invalidatedConfirmation': had_outcome,
            'invalidatedDraftAndExport': had_outcome, 'reopenReason': reason, 'mappedToFields': mapped}


def response_changes(record: dict, request_id: str) -> dict:
    """What staff should look at: the latest response, original vs current value of each affected field,
    and which of them still need a fresh human review. Read-only."""
    req = find_request(record, request_id)
    if not req['responses']:
        return {'requestId': request_id, 'state': req['state'], 'response': None, 'fields': []}
    ids = set(req['fieldIds']) or {f['id'] for f in record['formFields']}
    rows = []
    for f in record['formFields']:
        if f['id'] not in ids:
            continue
        rows.append({'id': f['id'], 'originalValue': f['value'], 'originalStatus': f['status'],
                     'effectiveValue': effective_value(f), 'needsReview': not f['review'].get('reviewed'),
                     'assessment': f['review'].get('assessment'), 'reopenReason': f['review'].get('reopenReason'),
                     'newEvidence': [e for e in f.get('followUpEvidence', []) if e['requestId'] == request_id]})
    last = req['responses'][-1]
    return {'requestId': request_id, 'state': req['state'],
            'response': {k: last[k] for k in ('id', 'responder', 'text', 'document', 'citations', 'receivedAt', 'sent')},
            'fields': rows}


def review_response(record: dict, request_id: str, body: ReviewInput, now=now_iso) -> dict:
    """A person marks the response as reviewed. Allowed only after every affected field was re-reviewed
    against it. This does not resolve anything clinically and does not confirm an outcome."""
    req = find_request(record, request_id)
    _check_writable(record, body.version)
    if req['state'] != NEEDS_REVIEW:
        _reject(409, 'There is no response waiting for review.')
    if len(body.note) < MIN_NOTE:
        _reject(422, f'Explain what was checked in at least {MIN_NOTE} characters.')
    ids = set(req['fieldIds']) or {f['id'] for f in record['formFields']}
    pending = [f['id'] for f in record['formFields'] if f['id'] in ids and not f['review'].get('reviewed')]
    if pending:
        _reject(409, f'Re-review the affected fields first ({len(pending)} still open).')
    unresolved = [f['id'] for f in record['formFields']
                  if f['id'] in ids and f['review'].get('assessment') != 'verified']
    new_version, had_outcome = _bump(record)
    req['state'] = REVIEWED
    req['reviewedAt'], req['reviewedAtVersion'] = now(), new_version
    req['review'] = {'reviewerLabel': body.reviewer, 'note': body.note, 'reviewerId': None,
                     'stillUnresolvedFieldIds': unresolved,
                     'meaning': 'Evidence was reviewed by a person. Not a clinical resolution or eligibility finding.'}
    return {'requestId': request_id, 'version': new_version, 'stillUnresolvedFieldIds': unresolved,
            'invalidatedConfirmation': had_outcome, 'confirmedOutcome': False}


def open_requests(record: dict) -> list[dict]:
    """Compact list for inbox / allowed-actions use: requests not yet reviewed, with their state."""
    return [{'id': r['id'], 'state': r['state'], 'fieldIds': r['fieldIds'], 'question': r['question']}
            for r in _state(record)['requests'] if r['state'] != REVIEWED]
