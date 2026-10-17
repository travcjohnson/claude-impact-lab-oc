"""BE-04 tests: field-level human review, invalidation, idempotent confirmation, reviewed export.

SYNTHETIC ONLY. The analysis result comes from a fake adapter with hand-built fields; no model is called
and nothing here validates real extraction. These tests prove the server enforces human-review rules
over whatever analysis exists, including the stale-draft and "tick checked" bugs named in BE-04.
"""
import time
import unittest

from fastapi.testclient import TestClient

from backend.analysis import AnalysisRuntime
from backend.app import create_app
from test_analysis import FakeAdapter, ev, runtime
from test_api import pdf_bytes


def rich_result(request):
    """Five fields in five different original states, and findings that depend on them."""
    pid = request.referral_id
    p1, p2 = ev(1, 'original page 1', doc=pid), ev(2, 'original page 2', doc=pid)
    field = lambda i, v, s, e=(), alts=(): {'id': i, 'value': v, 'status': s, 'evidence': list(e), 'alternatives': list(alts)}
    return {
        'schemaVersion': '0.1.0-draft',
        'formFields': [
            field('mobility', 'independent', 'conflicting', [p1], [{'value': 'needs assistance', 'evidence': [p2]}]),
            field('covid_result', 'negative', 'extracted', [p1]),
            field('covid_date', None, 'redacted'),
            field('self_med', None, 'missing'),
            field('page3_text', None, 'unreadable'),
        ],
        'findings': [
            {'id': 'f1', 'ruleId': 'MOB-4', 'criteriaVersion': 'synthetic-v0', 'status': 'conflict', 'fieldIds': ['mobility'],
             'evidence': [p1, p2], 'rationale': 'Synthetic: sources disagree.'},
            {'id': 'f2', 'ruleId': 'INF-2', 'criteriaVersion': 'synthetic-v0', 'status': 'unknown',
             'fieldIds': ['covid_result', 'covid_date'], 'evidence': [p1], 'rationale': 'Synthetic: date unknown.'},
            {'id': 'f3', 'ruleId': 'COG-1', 'criteriaVersion': 'synthetic-v0', 'status': 'unknown', 'fieldIds': ['self_med'],
             'evidence': [p2], 'rationale': 'Synthetic: not documented.'},
        ],
        'criteriaCoverage': {'applicable': 3, 'evaluated': 3, 'unresolved': []},     # "complete" on purpose
        'authorization': {'status': 'unknown'},
    }


class ReviewApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(ocr=lambda i: 'Synthetic OCR', analysis=runtime(FakeAdapter(rich_result))))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.id = self.client.post('/api/referrals', files={'file': ('t.pdf', pdf_bytes(3), 'application/pdf')}).json()['referralId']
        for _ in range(300):
            if self.client.get('/api/jobs/' + self.id).json()['analysis']['status'] == 'needs_review':
                break
            time.sleep(0.02)
        else:
            self.fail('analysis never reached needs_review')
        self.base = f'/api/referrals/{self.id}'

    # -- helpers
    def record(self):
        return self.client.get(self.base).json()

    def field(self, record, fid):
        return next(f for f in record['formFields'] if f['id'] == fid)

    def edit(self, fid, version=None, **kw):
        body = {'version': version or self.record()['version'], 'value': 'unknown', 'assessment': 'unresolved', 'reviewer': 'QA', **kw}
        return self.client.patch(f'{self.base}/fields/{fid}', json=body)

    def note(self):
        version = self.record()['version']
        return self.client.patch(self.base + '/review', json={'version': version, 'page': 1, 'reviewer': 'QA',
                                                              'note': 'Source page checked for this synthetic test.'})

    def review_all(self):
        """Verify the one extracted field; leave every other field explicitly unresolved."""
        assert self.edit('covid_result', value='negative', assessment='verified').status_code == 200
        for fid in ('mobility', 'covid_date', 'self_med', 'page3_text'):
            assert self.edit(fid, value='unknown' if fid != 'mobility' else 'independent').status_code == 200, fid

    def confirm_body(self, **kw):
        return {'version': self.record()['version'], 'decision': 'clarification', 'reviewer': 'QA',
                'rationale': 'Synthetic request for clarification.', 'attested': True, **kw}

    def confirmed(self):
        self.assertEqual(self.note().status_code, 200)
        self.review_all()
        body = self.confirm_body()
        self.assertEqual(self.client.post(self.base + '/outcome', json=body).status_code, 200)
        return body

    # -- field review
    def test_verifying_keeps_the_original_and_records_a_label_not_an_identity(self):
        response = self.edit('covid_result', value='negative', assessment='verified', page=1)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        f = self.field(body, 'covid_result')
        self.assertEqual((body['version'], f['value'], f['status']), (3, 'negative', 'extracted'))     # original untouched
        r = f['review']
        self.assertEqual((r['reviewed'], r['reviewerId'], r['reviewerLabel'], r['correctedValue'], r['effectiveValue']),
                         (True, None, 'QA', None, 'negative'))
        self.assertEqual(body['change']['invalidatedFindingIds'], [])          # value unchanged: findings stay valid
        self.assertEqual(len(r['history']), 1)
        self.assertEqual((r['history'][0]['before']['assessment'], r['history'][0]['after']['assessment']), (None, 'verified'))
        self.assertIn('allowedActions', body)

    def test_a_correction_needs_reason_and_source_and_marks_only_dependent_findings_stale(self):
        for kw, why in [({}, 'no reason'), ({'note': 'too short'}, 'short reason'),
                        ({'note': 'Therapy note says positive on page 2.'}, 'no source page'),
                        ({'note': 'Therapy note says positive on page 2.', 'page': 9}, 'page out of range')]:
            self.assertEqual(self.edit('covid_result', value='positive', **kw).status_code, 422, why)
        self.assertEqual(self.record()['version'], 2)                           # rejected edits change nothing
        ok = self.edit('covid_result', value='positive', note='Therapy note says positive on page 2.', page=2)
        self.assertEqual(ok.status_code, 200)
        body = ok.json()
        self.assertEqual(body['change']['invalidatedFindingIds'], ['f2'])       # f2 depends on covid_result; f1/f3 do not
        findings = {f['id']: f for f in body['findings']}
        self.assertTrue(findings['f2']['stale'] and not findings['f2']['reviewed'])
        self.assertNotIn('stale', findings['f1'])
        f = self.field(body, 'covid_result')
        self.assertEqual((f['value'], f['review']['correctedValue'], f['review']['effectiveValue'], f['review']['sourcePage']),
                         ('negative', 'positive', 'positive', 2))
        back = self.edit('covid_result', value='negative', assessment='verified', note='Rechecked original source and reversed the prior correction.', page=1).json()      # restore the original
        self.assertIsNone(self.field(back, 'covid_result')['review']['correctedValue'])
        self.assertEqual(len(self.field(back, 'covid_result')['review']['history']), 2)

    def test_reversal_requires_new_reason_and_source(self):
        note = 'Synthetic correction based on source page two.'
        self.assertEqual(self.edit('covid_result', value='positive', note=note, page=2).status_code, 200)
        version = self.record()['version']
        self.assertEqual(self.edit('covid_result', value='negative', assessment='verified').status_code, 422)
        self.assertEqual(self.edit('covid_result', value='negative', note=note, page=1).status_code, 422)
        self.assertEqual(self.record()['version'], version)
        self.assertEqual(self.edit('covid_result', value='negative', note='Rechecked the original and reversed the previous correction.', page=1).status_code, 200)

    def test_ticking_checked_cannot_resolve_conflicting_missing_redacted_or_unreadable(self):
        for fid, status, original in [('mobility', 'conflicting', 'independent'), ('self_med', 'missing', 'unknown'),
                                      ('covid_date', 'redacted', 'unknown'), ('page3_text', 'unreadable', 'unknown')]:
            before = self.record()['version']
            r = self.edit(fid, value=original, assessment='verified')     # only the tick, no value change
            self.assertEqual(r.status_code, 422, fid)
            self.assertIn(f'originally {status}', r.json()['detail'])
            self.assertEqual(self.record()['version'], before)
            self.assertEqual(self.edit(fid, value=original, assessment='unresolved').status_code, 200, fid)   # staying open is fine
        # the verified rule outranks the correction rule: a changed value does not get a friendlier error
        self.assertIn('originally missing', self.edit('self_med', value='Nurse says yes.', assessment='verified').json()['detail'])

    def test_redacted_values_cannot_be_reconstructed(self):
        r = self.edit('covid_date', value='2025-01-01', note='Date read from another source.', page=1)
        self.assertEqual(r.status_code, 422)
        self.assertIn('cannot be reconstructed', r.json()['detail'])
        ok = self.edit('covid_date', value='unknown').json()
        self.assertIsNone(self.field(ok, 'covid_date')['review']['correctedValue'])

    def test_a_human_supplied_value_for_a_missing_field_stays_unverified_and_staleness_follows(self):
        r = self.edit('self_med', value='Nurse note says yes.', note='Nurse note on page 2 states this.', page=2)
        body = r.json()
        f = self.field(body, 'self_med')
        self.assertEqual((f['value'], f['status'], f['review']['effectiveValue'], f['review']['assessment']),
                         (None, 'missing', 'Nurse note says yes.', 'unresolved'))
        self.assertEqual(body['change']['invalidatedFindingIds'], ['f3'])

    def test_validation_unknown_fields_and_stale_or_competing_writes(self):
        v = self.record()['version']
        self.assertEqual(self.edit('nope').status_code, 404)
        attempt = {'version': v, 'value': 'x', 'assessment': 'unresolved', 'reviewer': 'QA'}
        # a traversal-style id never reaches the handler (falls to the allowlisted asset route): rejected, nothing served
        self.assertIn(self.client.patch(f'{self.base}/fields/..%2Fsecret', json=attempt).status_code, (404, 405))
        self.assertEqual(self.client.patch(f'{self.base}/fields/bad%20id', json=attempt).status_code, 404)   # reaches the handler: id format rejected
        self.assertEqual(self.record()['version'], v)
        for bad in ({'reviewer': ' '}, {'assessment': 'checked'}, {'value': ''}, {'extra': 1}, {'value': 'x' * 4001}):
            self.assertEqual(self.edit('covid_result', **bad).status_code, 422, bad)
        first = self.edit('self_med', version=v)
        second = self.edit('covid_date', version=v)          # a competing writer still holding the old version
        self.assertEqual((first.status_code, second.status_code), (200, 409))
        self.assertEqual(self.edit('covid_date', version=v + 1).status_code, 200)

    def test_default_mode_has_no_fields_to_review_and_no_export(self):
        with TestClient(create_app(ocr=lambda i: 'Synthetic OCR', analysis=AnalysisRuntime(env={}))) as c:
            pid = c.post('/api/referrals', files={'file': ('t.pdf', pdf_bytes(1), 'application/pdf')}).json()['referralId']
            for _ in range(200):
                if c.get('/api/jobs/' + pid).json()['state'] == 'text_ready':
                    break
                time.sleep(0.02)
            r = c.patch(f'/api/referrals/{pid}/fields/anything', json={'version': 1, 'value': 'x', 'assessment': 'unresolved', 'reviewer': 'QA'})
            self.assertEqual(r.status_code, 409)
            actions = c.get(f'/api/referrals/{pid}').json()['allowedActions']
            self.assertFalse(actions['saveFieldReview']['allowed'])
            self.assertTrue(actions['savePageNote']['allowed'])
            self.assertEqual(c.get(f'/api/referrals/{pid}/export').status_code, 409)

    # -- confirmation, draft, export
    def test_confirmation_needs_every_field_reviewed_then_draft_and_export_separate_confirmed_from_open(self):
        self.assertEqual(self.note().status_code, 200)
        gated = self.client.post(self.base + '/outcome', json=self.confirm_body())
        self.assertEqual(gated.status_code, 409)
        self.assertIn('Review every extracted field', gated.json()['detail'])
        reasons = self.record()['allowedActions']['confirmNextStep']
        self.assertFalse(reasons['allowed'])
        self.assertTrue(any('5 not yet reviewed' in r for r in reasons['reasons']))
        self.review_all()
        self.assertTrue(self.record()['allowedActions']['confirmNextStep']['allowed'])
        self.assertEqual(self.client.post(self.base + '/outcome', json=self.confirm_body()).status_code, 200)

        text = self.client.get(self.base + '/draft').json()['text']
        self.assertIn('CONFIRMED BY REVIEWER', text)
        self.assertIn('OPEN / UNRESOLVED', text)
        self.assertIn('- covid_result: negative', text)
        self.assertLess(text.index('- covid_result'), text.index('OPEN / UNRESOLVED'))      # confirmed ones come first
        self.assertIn('- self_med: unknown (original: missing', text)
        self.assertNotIn('accept', text.lower())
        self.assertIn('Clinical eligibility and authorization have not been established.', text)

        export = self.client.get(self.base + '/export').json()
        self.assertEqual([f['id'] for f in export['confirmedFields']], ['covid_result'])
        self.assertEqual({f['id'] for f in export['unresolved']['fields']}, {'mobility', 'covid_date', 'self_med', 'page3_text'})
        self.assertEqual((export['sent'], export['version'], export['analysis']['synthetic']), (False, self.record()['version'], True))
        self.assertTrue(any('SYNTHETIC' in n for n in export['notes']))
        self.assertTrue(any('not authenticated' in n for n in export['notes']))
        self.assertEqual(export['confirmedFields'][0]['originalValue'], 'negative')
        self.assertEqual(export['confirmedFields'][0]['history'][0]['reviewerLabel'], 'QA')
        self.assertEqual((export['clinicalEligibility'], export['authorization']['established']), ('not evaluated', False))

    def test_any_later_edit_or_uncheck_invalidates_confirmation_draft_and_export(self):
        body = self.confirmed()
        self.assertTrue(self.record()['allowedActions']['export']['allowed'])
        unchecked = self.edit('covid_result', value='negative', assessment='unresolved')       # the "uncheck" bug
        self.assertEqual(unchecked.status_code, 200)
        self.assertTrue(unchecked.json()['change']['invalidatedConfirmation'])
        after = self.record()
        self.assertIsNone(after['outcome'])
        self.assertEqual((self.client.get(self.base + '/draft').status_code, self.client.get(self.base + '/export').status_code), (409, 409))
        self.assertFalse(after['allowedActions']['draft']['allowed'])
        self.assertEqual(self.client.post(self.base + '/outcome', json=body).status_code, 409)     # old version is stale
        self.assertEqual(self.client.post(self.base + '/outcome', json=self.confirm_body()).status_code, 200)

    def test_page_note_edit_also_invalidates_export(self):
        self.confirmed()
        self.assertEqual(self.note().status_code, 200)
        self.assertEqual(self.client.get(self.base + '/export').status_code, 409)

    def test_duplicate_confirmation_is_idempotent_but_conflicts_and_stale_replays_are_not(self):
        self.assertEqual(self.note().status_code, 200)
        self.review_all()
        body = self.confirm_body()
        first = self.client.post(self.base + '/outcome', json=body)
        self.assertEqual(first.status_code, 200)
        version, confirmed_at = first.json()['version'], first.json()['outcome']['confirmedAt']

        replay = self.client.post(self.base + '/outcome', json=body)          # exact repeat (e.g. a double click)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()['idempotentReplay'])
        self.assertEqual((replay.json()['version'], replay.json()['outcome']['confirmedAt']), (version, confirmed_at))
        self.assertNotIn('idempotentReplay', self.record())

        conflicting = self.client.post(self.base + '/outcome', json={**body, 'rationale': 'A different synthetic rationale.'})
        self.assertEqual(conflicting.status_code, 409)                        # same version, different content
        self.assertEqual(self.record()['outcome']['rationale'], 'Synthetic request for clarification.')

        self.assertEqual(self.edit('covid_result', value='negative', assessment='verified').status_code, 200)
        self.assertEqual(self.client.post(self.base + '/outcome', json=body).status_code, 409)    # replay after an edit

    def test_confirmation_validation_still_rejects_missing_reviewer_rationale_and_attestation(self):
        self.assertEqual(self.note().status_code, 200)
        self.review_all()
        for bad in ({'attested': False}, {'reviewer': ' '}, {'rationale': 'too short'}, {'decision': 'unknown'}):
            self.assertIn(self.client.post(self.base + '/outcome', json=self.confirm_body(**bad)).status_code, (409, 422), bad)
        self.assertIsNone(self.record()['outcome'])

    def test_approval_and_denial_stay_disabled_and_explain_why(self):
        self.confirmed()
        for decision in ('approve', 'deny'):
            r = self.client.post(self.base + '/outcome', json=self.confirm_body(decision=decision))
            self.assertEqual(r.status_code, 409)
            self.assertIn('Admission decisions are disabled', r.json()['detail'])
        actions = self.record()['allowedActions']
        self.assertFalse(actions['approve']['allowed'] or actions['deny']['allowed'])
        self.assertTrue(any('disabled' in r for r in actions['approve']['reasons']))
        self.assertTrue(any('unresolved' in r for r in actions['approve']['reasons']))
        self.assertTrue(any('reviewed unmet applicable criterion' in r for r in actions['deny']['reasons']))
        self.assertEqual(self.record()['criteriaCoverage']['complete'], True)      # even complete coverage does not unlock it

    def test_history_accumulates_and_the_original_is_never_overwritten(self):
        self.edit('self_med', value='Nurse note says yes.', note='Nurse note on page 2 states this.', page=2)
        self.edit('self_med', value='Nurse note says no.', note='Corrected after rereading page 2 carefully.', page=2)
        self.edit('self_med', value='unknown', note='Reverted to unknown after reviewing conflicting source text.', page=2)
        f = self.field(self.record(), 'self_med')
        history = f['review']['history']
        self.assertEqual((f['value'], f['status'], len(history)), (None, 'missing', 3))
        self.assertEqual([h['after']['effectiveValue'] for h in history], ['Nurse note says yes.', 'Nurse note says no.', None])
        self.assertEqual([h['before']['effectiveValue'] for h in history], [None, 'Nurse note says yes.', 'Nurse note says no.'])
        self.assertEqual([h['version'] for h in history], sorted({h['version'] for h in history}))


if __name__ == '__main__':
    unittest.main()
