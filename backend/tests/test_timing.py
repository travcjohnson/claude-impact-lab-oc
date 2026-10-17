"""BE-06: timing definitions and the end-to-end review walkthrough. Synthetic PDFs and fakes only.

Nothing here measures real review time or supports a time-saving claim; it proves the arithmetic and
the end-to-end behaviour (page citations, stale-decision invalidation, failure and restart cases).
"""
import time
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend import timing
from backend.analysis import AnalysisError
from backend.app import create_app
from test_analysis import FakeAdapter, runtime
from test_api import pdf_bytes
from test_review import rich_result

T0 = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)


def ts(minutes):
    return (T0 + timedelta(minutes=minutes)).isoformat(timespec='seconds')


def ev(minutes, kind, **extra):
    return {'at': ts(minutes), 'kind': kind, 'version': 1, **extra}


class Clock:
    """Each call advances one minute, so event order is deterministic."""
    def __init__(self):
        self.minutes = -1

    def __call__(self):
        self.minutes += 1
        return ts(self.minutes)


class ComputeTests(unittest.TestCase):
    base = [ev(0, 'received'), ev(2, 'text_ready'), ev(10, 'page_note')]

    def test_active_excludes_explicit_pauses_and_waits_and_merges_overlap(self):
        # pause 20-30 and wait 25-40 overlap, so the union is 20-40 = 20 minutes
        events = sorted(self.base + [ev(20, 'pause'), ev(25, 'wait_start'), ev(30, 'resume'), ev(40, 'wait_end'),
                                     ev(50, 'confirmation', decision='clarification')], key=lambda e: e['at'])
        r = timing.compute(events, ts(60))
        self.assertEqual(r['processingSeconds'], 120)
        self.assertEqual(r['elapsedSeconds'], 50 * 60)
        self.assertEqual(r['activeSeconds'], (50 - 10 - 20) * 60)
        self.assertEqual((r['pausedSeconds'], r['waitingSeconds']), (10 * 60, 15 * 60))

    def test_pause_before_the_first_review_does_not_reduce_active_time(self):
        events = sorted(self.base + [ev(3, 'pause'), ev(5, 'resume'), ev(50, 'confirmation', decision='clarification')],
                        key=lambda e: e['at'])
        self.assertEqual(timing.compute(events, ts(60))['activeSeconds'], 40 * 60)

    def test_unknown_is_null_not_zero(self):
        r = timing.compute([ev(0, 'received')], ts(5))
        self.assertEqual(r['status'], 'unfinished')
        for key in ('processingSeconds', 'elapsedSeconds', 'activeSeconds', 'pausedSeconds'):
            self.assertIsNone(r[key], key)
        self.assertEqual(r['elapsedSoFarSeconds'], 300)
        self.assertTrue(r['activeUnknownReason'])

    def test_open_interval_makes_active_unknown(self):
        r = timing.compute(self.base + [ev(20, 'pause'), ev(30, 'confirmation', decision='clarification')], ts(40))
        self.assertIsNone(r['activeSeconds'])
        self.assertEqual(r['openIntervals'], ['pause'])
        self.assertIsNotNone(r['elapsedSeconds'])

    def test_out_of_order_events_are_flagged_not_trusted(self):
        r = timing.compute([ev(5, 'received'), ev(1, 'text_ready')], ts(9))
        self.assertIn('out_of_order_events', r['anomalies'])
        self.assertIsNone(r['processingSeconds'])

    def test_clarification_is_intermediate_never_complete(self):
        r = timing.compute(self.base + [ev(20, 'confirmation', decision='clarification')], ts(30))
        self.assertEqual(r['status'], 'confirmed-intermediate')
        self.assertEqual(r['disposition'], {'kind': 'intermediate', 'decision': 'clarification', 'complete': False})

    def test_edit_after_confirmation_returns_the_packet_to_unfinished(self):
        r = timing.compute(self.base + [ev(20, 'confirmation', decision='clarification'),
                                        ev(25, 'field_review', corrected=True, invalidatedConfirmation=True)], ts(30))
        self.assertEqual(r['status'], 'unfinished')
        self.assertIsNone(r['confirmedAt'])
        self.assertEqual(r['counts']['invalidatedConfirmations'], 1)
        self.assertEqual(r['counts']['corrections'], 1)

    def test_summary_keeps_failed_and_unfinished_and_claims_no_saving(self):
        done = self.base + [ev(40, 'confirmation', decision='clinical-review')]
        s = timing.summarize({'a': done, 'b': [ev(0, 'received'), ev(1, 'text_failed')], 'c': [ev(0, 'received')]}, ts(50))
        self.assertEqual((s['packets'], s['confirmedIntermediate'], s['textFailed'], s['unfinished']), (3, 1, 1, 1))
        self.assertEqual(s['activeSeconds']['n'], 1)
        self.assertEqual(s['activeSeconds']['unknown'], 2)
        self.assertIsNone(s['savingsPercent'])
        self.assertFalse(s['baseline']['measured'])
        self.assertEqual(s['completedAdmissionDispositions'], 0)

    def test_summary_with_nothing_has_no_statistics(self):
        s = timing.summarize({}, ts(0))
        self.assertEqual(s['activeSeconds'], {'n': 0, 'median': None, 'min': None, 'max': None, 'unknown': 0})


class EndToEnd(unittest.TestCase):
    def start(self, adapter, data=None):
        client = TestClient(create_app(ocr=lambda i: 'Synthetic OCR', analysis=runtime(adapter), clock=Clock()))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def upload(self, client, data=None):
        pid = client.post('/api/referrals', files={'file': ('t.pdf', data or pdf_bytes(3), 'application/pdf')}).json()['referralId']
        for _ in range(300):
            if client.get('/api/jobs/' + pid).json()['analysis']['status'] in ('needs_review', 'failed', 'unavailable'):
                return pid
            time.sleep(0.02)
        self.fail('analysis did not finish')

    def test_upload_to_unsent_export_with_citations_and_stale_invalidation(self):
        c = self.start(FakeAdapter(rich_result))
        pid = self.upload(c)
        base = f'/api/referrals/{pid}'
        record = c.get(base).json()

        # every cited page opens and contains the quoted text on that exact original page
        cited = [e for f in record['findings'] for e in f['evidence']] + [e for f in record['formFields'] for e in f['evidence']]
        self.assertTrue(cited)
        for e in cited:
            self.assertEqual(c.get(f"{base}/pages/{e['page']}/image").status_code, 200)
            self.assertIn(e['quote'].lower(), record['pages'][e['page'] - 1]['text'].lower())
            hits = c.get(f'{base}/search', params={'q': e['quote']}).json()['matches']
            self.assertIn(e['page'], [h['page'] for h in hits])

        v = lambda: c.get(base).json()['version']
        edit = lambda fid, **kw: c.patch(f'{base}/fields/{fid}', json={'version': v(), 'value': 'unknown', 'assessment': 'unresolved',
                                                                       'reviewer': 'QA', **kw})
        self.assertEqual(c.patch(base + '/review', json={'version': v(), 'page': 1, 'reviewer': 'QA',
                                                         'note': 'Source page checked for this synthetic test.'}).status_code, 200)
        self.assertEqual(c.post(base + '/timing', json={'event': 'pause', 'reason': 'coordinator-break'}).status_code, 200)
        self.assertEqual(c.post(base + '/timing', json={'event': 'pause'}).status_code, 409, 'cannot pause twice')
        self.assertEqual(c.post(base + '/timing', json={'event': 'resume'}).status_code, 200)
        self.assertEqual(edit('covid_result', value='negative', assessment='verified').status_code, 200)
        for fid in ('mobility', 'covid_date', 'self_med', 'page3_text'):
            self.assertEqual(edit(fid, value='independent' if fid == 'mobility' else 'unknown').status_code, 200)
        self.assertEqual(c.get(base + '/export').status_code, 409, 'no export before confirmation')
        body = {'version': v(), 'decision': 'clarification', 'reviewer': 'QA', 'rationale': 'Synthetic clarification request.', 'attested': True}
        self.assertEqual(c.post(base + '/outcome', json=body).status_code, 200)
        self.assertEqual(c.post(base + '/outcome', json=body).json()['idempotentReplay'], True)
        export = c.get(base + '/export').json()
        self.assertFalse(export['sent'])
        self.assertEqual(export['clinicalEligibility'], 'not evaluated')

        t = c.get(base + '/timing').json()
        self.assertEqual(t['status'], 'confirmed-intermediate')
        self.assertEqual(t['counts']['confirmations'], 1, 'replay is not a second confirmation')
        self.assertGreater(t['pausedSeconds'], 0)
        self.assertLess(t['activeSeconds'], t['elapsedSeconds'])
        self.assertFalse(t['disposition']['complete'])

        # a correction after confirmation invalidates the old decision, draft and export
        self.assertEqual(edit('covid_result', value='positive', assessment='unresolved',
                              note='Therapy note says positive on page 2.', page=2).status_code, 200)
        self.assertEqual(c.get(base + '/export').status_code, 409)
        self.assertEqual(c.get(base + '/draft').status_code, 409)
        self.assertEqual(c.post(base + '/outcome', json=body).status_code, 409, 'stale confirmation request')
        t2 = c.get(base + '/timing').json()
        self.assertEqual(t2['status'], 'unfinished')
        self.assertEqual(t2['counts']['invalidatedConfirmations'], 1)
        self.assertIsNone(t2['activeSeconds'])

    def test_failed_analysis_still_allows_manual_review_and_is_counted(self):
        def boom(request):
            raise AnalysisError('Static failure.', code='model_error')
        c = self.start(FakeAdapter(boom))
        pid = self.upload(c)
        base = f'/api/referrals/{pid}'
        self.assertEqual(c.get(base).json()['analysis']['status'], 'failed')
        self.assertEqual(c.patch(base + '/review', json={'version': 1, 'page': 1, 'reviewer': 'QA',
                                                         'note': 'Manual check of page one.'}).status_code, 200)
        summary = c.get('/api/timing/summary').json()
        self.assertEqual((summary['packets'], summary['unfinished']), (1, 1))
        kinds = [e['kind'] for e in c.app.state.service.timelines[pid]]
        self.assertIn('analysis_terminal', kinds)

    def test_invalid_upload_creates_no_timing_record_and_restart_forgets_everything(self):
        c = self.start(FakeAdapter(rich_result))
        self.assertGreaterEqual(c.post('/api/referrals', files={'file': ('x.pdf', b'not a pdf', 'application/pdf')}).status_code, 400)
        self.assertEqual(c.get('/api/timing/summary').json()['packets'], 0)
        pid = self.upload(c)
        c.__exit__(None, None, None)
        fresh = self.start(FakeAdapter(rich_result))      # a restart: session data is not durable
        self.assertEqual(fresh.get(f'/api/referrals/{pid}/timing').status_code, 404)
        self.assertEqual(fresh.get('/api/timing/summary').json()['packets'], 0)

    def test_timing_events_reject_unknown_values_and_packets(self):
        c = self.start(FakeAdapter(rich_result))
        pid = self.upload(c)
        self.assertEqual(c.post(f'/api/referrals/{pid}/timing', json={'event': 'sleep'}).status_code, 422)
        self.assertEqual(c.post(f'/api/referrals/{pid}/timing', json={'event': 'resume'}).status_code, 409)
        self.assertEqual(c.post('/api/referrals/' + 'a' * 32 + '/timing', json={'event': 'pause'}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
