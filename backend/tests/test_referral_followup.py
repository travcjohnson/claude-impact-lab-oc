"""LOOP-02 tests: follow-up request/response attached to the original referral.

SYNTHETIC ONLY: hand-built records, a synthetic responder, no model, no network, no outgoing messages.
Re-review uses the real backend.review so there is no second confirmation engine.
"""
import copy
import unittest

from fastapi import HTTPException

from backend import referral_followup as fu
from backend.review import FieldReviewInput, apply_field_review

RID, OTHER = 'ref0001', 'ref0002'
DOC = {'documentId': 'doc-reply-1', 'referralId': RID, 'version': 1, 'pageCount': 2}
RESP = {'label': 'Synthetic hospital responder', 'synthetic': True}


def record():
    def field(i, v, s):
        return {'id': i, 'value': v, 'status': s, 'evidence': [], 'alternatives': [],
                'review': {'reviewed': False, 'reviewerId': None}}
    return {
        'referralId': RID, 'version': 5, 'job': {'state': 'text_ready'}, 'pages': [{'page': 1}, {'page': 2}],
        'analysis': {'status': 'needs_review'}, 'reviews': {'1': {'note': 'x'}}, 'outcome': None,
        'formFields': [field('mobility', 'independent', 'conflicting'), field('covid_result', 'negative', 'extracted'),
                       field('covid_date', None, 'redacted')],
        'findings': [{'id': 'f1', 'ruleId': 'MOB-4', 'status': 'conflict', 'fieldIds': ['mobility']},
                     {'id': 'f2', 'ruleId': 'INF-2', 'status': 'unknown', 'fieldIds': ['covid_date']}],
        'criteriaCoverage': {'complete': False},
    }


def review_all(rec):
    """A person re-reviews every field (verified only where the original allowed it)."""
    for f in rec['formFields']:
        ok = f['status'] == 'extracted'
        apply_field_review(rec, f['id'], FieldReviewInput(
            version=rec['version'], value='unknown' if f['value'] is None else str(f['value']),
            assessment='verified' if ok else 'unresolved', reviewer='Synthetic reviewer'))


def confirm(rec):
    rec['outcome'] = {'decision': 'clarification', 'reviewer': 'Synthetic reviewer', 'rationale': 'x', 'attested': True}
    rec['version'] += 1


def ask(rec, fields=('mobility',), key='k1'):
    return fu.create_request(rec, fu.RequestInput(version=rec['version'], idempotencyKey=key, question='Can the patient transfer alone?',
                                                  fieldIds=list(fields), requester='Synthetic staff'))


def reply(rec, rid='q-1', key='r1', doc=DOC, **kw):
    cites = kw.pop('citations', [{'page': 1, 'quote': 'Synthetic: needs assistance for transfers'}])
    return fu.record_response(rec, rid, fu.ResponseInput(version=rec['version'], idempotencyKey=key, responder=RESP,
                                                         text=kw.pop('text', 'Synthetic reply.'), document=doc, citations=cites, **kw))


class FollowUpTests(unittest.TestCase):
    def test_full_loop_original_to_fresh_confirmation(self):
        rec = record(); review_all(rec); confirm(rec)
        self.assertIsNotNone(rec['outcome'])
        original = copy.deepcopy(rec['formFields'][0])
        out = ask(rec); self.assertEqual(out['requestId'], 'q-1')
        self.assertIsNotNone(rec['outcome'], 'asking a question does not change evidence')
        self.assertEqual(fu.open_requests(rec)[0]['state'], fu.WAITING)

        res = reply(rec)
        self.assertEqual(res['reopenedFieldIds'], ['mobility'])
        self.assertEqual(res['invalidatedFindingIds'], ['f1'])
        self.assertTrue(res['invalidatedConfirmation'] and res['invalidatedDraftAndExport'])
        self.assertIsNone(rec['outcome'])
        mob = rec['formFields'][0]
        # original value/status/evidence untouched; new evidence sits beside it
        for k in ('value', 'status', 'evidence', 'alternatives'):
            self.assertEqual(mob[k], original[k])
        self.assertEqual(mob['followUpEvidence'][0]['document']['documentId'], 'doc-reply-1')
        self.assertFalse(mob['review']['reviewed']); self.assertIn('q-1', mob['review']['reopenReason'])
        self.assertTrue(rec['findings'][0]['stale']); self.assertNotIn('stale', rec['findings'][1])
        self.assertEqual(rec['formFields'][1]['review']['reviewed'], True, 'unrelated field stays reviewed')

        changes = fu.response_changes(rec, 'q-1')
        self.assertEqual(changes['state'], fu.NEEDS_REVIEW)
        self.assertTrue(changes['fields'][0]['needsReview']); self.assertEqual(changes['response']['sent'], False)

        # cannot mark reviewed before the field is re-reviewed
        with self.assertRaises(HTTPException) as e:
            fu.review_response(rec, 'q-1', fu.ReviewInput(version=rec['version'], reviewer='R', note='Checked the new page against the field.'))
        self.assertEqual(e.exception.status_code, 409)

        apply_field_review(rec, 'mobility', FieldReviewInput(version=rec['version'], value='independent', assessment='unresolved', reviewer='R'))
        done = fu.review_response(rec, 'q-1', fu.ReviewInput(version=rec['version'], reviewer='R', note='Checked the new page against the field.'))
        self.assertEqual(done['stillUnresolvedFieldIds'], ['mobility'], 'conflict stays unresolved; reply does not resolve it')
        self.assertFalse(done['confirmedOutcome']); self.assertIsNone(rec['outcome'])
        self.assertEqual(fu.open_requests(rec), [])
        # a fresh human confirmation is still a separate step
        confirm(rec); self.assertIsNotNone(rec['outcome'])

    def test_reply_never_resolves_redacted_or_missing(self):
        rec = record(); ask(rec, ['covid_date']); reply(rec)
        f = rec['formFields'][2]
        self.assertIsNone(f['value']); self.assertEqual(f['status'], 'redacted')
        with self.assertRaises(HTTPException) as e:
            apply_field_review(rec, 'covid_date', FieldReviewInput(version=rec['version'], value='2026-01-01', assessment='unresolved', reviewer='R'))
        self.assertEqual(e.exception.status_code, 422)

    def test_unmapped_request_reopens_everything_with_reason(self):
        rec = record(); review_all(rec); ask(rec, []); res = reply(rec)
        self.assertFalse(res['mappedToFields'])
        self.assertEqual(sorted(res['reopenedFieldIds']), ['covid_date', 'covid_result', 'mobility'])
        self.assertIn('conservatively', res['reopenReason'])
        self.assertEqual({f['id'] for f in rec['findings'] if f.get('stale')}, {'f1', 'f2'})

    def test_cross_referral_document_and_unknown_field_rejected(self):
        rec = record(); ask(rec)
        before = copy.deepcopy(rec)
        with self.assertRaises(HTTPException) as e:
            reply(rec, doc={**DOC, 'referralId': OTHER})
        self.assertEqual(e.exception.status_code, 422); self.assertEqual(rec, before, 'rejected call leaves no partial edit')
        with self.assertRaises(HTTPException) as e:
            ask(rec, ['nope'], key='k2')
        self.assertEqual(e.exception.status_code, 422)
        with self.assertRaises(HTTPException):
            fu.create_request(rec, fu.RequestInput(version=rec['version'], idempotencyKey='k3', question='q', fieldIds=['mobility', 'mobility'], requester='s'))

    def test_stale_versions_rejected(self):
        rec = record(); ask(rec)
        stale = rec['version'] - 1
        with self.assertRaises(HTTPException) as e:
            fu.record_response(rec, 'q-1', fu.ResponseInput(version=stale, idempotencyKey='r9', responder=RESP, text='late'))
        self.assertEqual(e.exception.status_code, 409)
        with self.assertRaises(HTTPException) as e:
            fu.create_request(rec, fu.RequestInput(version=stale, idempotencyKey='k9', question='q', requester='s'))
        self.assertEqual(e.exception.status_code, 409)

    def test_duplicate_retry_is_noop_but_conflicting_reuse_is_rejected(self):
        rec = record(); ask(rec)
        again = ask(rec)                     # same key, same content, now at an old version: still a no-op
        self.assertTrue(again['replay']); self.assertEqual(len(fu._state(rec)['requests']), 1)
        first = reply(rec); v = rec['version']
        retry = fu.record_response(rec, 'q-1', fu.ResponseInput(version=v - 1, idempotencyKey='r1', responder=RESP,
                                   text='Synthetic reply.', document=fu.DocumentRef(**DOC), citations=[fu.Citation(page=1, quote='Synthetic: needs assistance for transfers')]))
        self.assertTrue(retry['replay']); self.assertEqual(rec['version'], v); self.assertEqual(retry['responseId'], first['responseId'])
        with self.assertRaises(HTTPException) as e:
            fu.record_response(rec, 'q-1', fu.ResponseInput(version=v, idempotencyKey='r1', responder=RESP, text='different'))
        self.assertEqual(e.exception.status_code, 409)
        with self.assertRaises(HTTPException) as e:
            fu.create_request(rec, fu.RequestInput(version=v, idempotencyKey='k1', question='different question', requester='s'))
        self.assertEqual(e.exception.status_code, 409)

    def test_same_document_version_cannot_be_attached_twice(self):
        rec = record(); ask(rec); reply(rec)
        ask(rec, ['covid_result'], key='k2')
        with self.assertRaises(HTTPException) as e:
            reply(rec, rid='q-2', key='r2')
        self.assertEqual(e.exception.status_code, 409)
        reply(rec, rid='q-2', key='r2', doc={**DOC, 'version': 2})   # a new version of it is fine

    def test_second_response_to_unreviewed_request_rejected(self):
        rec = record(); ask(rec); reply(rec)
        with self.assertRaises(HTTPException) as e:
            reply(rec, key='r2', doc={**DOC, 'version': 2})
        self.assertEqual(e.exception.status_code, 409)

    def test_synthetic_responder_only_and_nothing_is_sent(self):
        rec = record(); ask(rec)
        with self.assertRaises(HTTPException) as e:
            fu.record_response(rec, 'q-1', fu.ResponseInput(version=rec['version'], idempotencyKey='r1', responder={'label': 'Hospital X', 'synthetic': False}, text='hi'))
        self.assertEqual(e.exception.status_code, 422)
        reply(rec)
        r = fu._state(rec)['requests'][0]
        self.assertIs(r['sent'], False); self.assertIs(r['responses'][0]['sent'], False)

    def test_empty_reply_and_bad_citations_rejected(self):
        rec = record(); ask(rec)
        with self.assertRaises(HTTPException):
            fu.record_response(rec, 'q-1', fu.ResponseInput(version=rec['version'], idempotencyKey='r1', responder=RESP, text=''))
        with self.assertRaises(HTTPException) as e:
            reply(rec, citations=[{'page': 3, 'quote': 'x'}])
        self.assertEqual(e.exception.status_code, 422)
        with self.assertRaises(HTTPException):
            reply(rec, citations=[{'page': 1, 'quote': 'invented text', 'sourceQuality': 'redacted'}])
        with self.assertRaises(HTTPException):
            reply(rec, doc=None)           # citations without a document
        self.assertEqual(fu.find_request(rec, 'q-1')['state'], fu.WAITING, 'no rejected call changed state')

    def test_redacted_citation_without_quote_is_kept(self):
        rec = record(); ask(rec)
        reply(rec, citations=[{'page': 2, 'quote': None, 'sourceQuality': 'redacted'}])
        self.assertIsNone(rec['formFields'][0]['followUpEvidence'][0]['citations'][0]['quote'])

    def test_unknown_request_and_review_without_response(self):
        rec = record(); ask(rec)
        with self.assertRaises(HTTPException) as e:
            fu.find_request(rec, 'q-9')
        self.assertEqual(e.exception.status_code, 404)
        with self.assertRaises(HTTPException) as e:
            fu.review_response(rec, 'q-1', fu.ReviewInput(version=rec['version'], reviewer='R', note='Checked the new page against the field.'))
        self.assertEqual(e.exception.status_code, 409)
        self.assertEqual(fu.response_changes(rec, 'q-1')['response'], None)


if __name__ == '__main__':
    unittest.main()
