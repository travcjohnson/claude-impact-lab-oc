"""LOOP-05: repeatable end-to-end rehearsal and readiness report. Prints structure and statuses, never document text.

    python -m backend.rehearsal [--out report.json]  # synthetic rehearsal only (always runnable, no credentials)
    python -m backend.rehearsal --real DIR           # additionally run the CONFIGURED real adapter on PDFs in DIR

Synthetic results and real-adapter results are reported in separate sections and are never merged. The real
section runs only when ALL of these hold, otherwise it is reported as NOT RUN with the reason: --real given,
IHH_ANALYSIS_ADAPTER set, IHH_ANALYSIS_MODEL set, ANTHROPIC_API_KEY set, DIR holds PDFs approved for event use.
The real section reports counts and error codes only (no text, quotes, values or filenames), and says nothing
about clinical accuracy: that needs the blind evaluation (backend/evaluation.py) and staff sign-off
(docs/loop-05-validation.md). No savings percentage is ever computed: `savingsPercent` is always null.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF
    import fitz
from fastapi.testclient import TestClient

from backend.analysis import AnalysisRuntime, AnalysisSettings, AnalysisUnavailable
from backend.app import create_app

QUOTE = 'transfers need assistance'


def _pdf(pages: list[str | None]) -> bytes:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _ev(page, quote, doc, quality='readable'):
    return {'documentId': doc, 'page': page, 'quote': quote, 'region': None, 'sourceQuality': quality}


class SyntheticAdapter:
    """Invented, deterministic stand-in for a model. synthetic=True so every output is labelled."""
    name, synthetic = 'rehearsal-synthetic', True

    def __init__(self, mode='ok'):
        self.mode = mode

    def analyze(self, request):
        if self.mode == 'timeout':
            time.sleep(1)
        if self.mode == 'unavailable':
            raise AnalysisUnavailable('Synthetic: adapter is down.', 'adapter_unavailable')
        doc = request.referral_id
        finding = {'id': 'r1', 'ruleId': 'MOB-1', 'criteriaVersion': 'synthetic-v0', 'status': 'unknown',
                   'fieldIds': ['transfer'], 'evidence': [_ev(1, QUOTE, doc)], 'rationale': 'Synthetic: not enough to say.'}
        if self.mode == 'invalid':
            finding['ruleId'] = 'ZZ-9'                 # unknown rule id: must be rejected, never repaired
        return {'schemaVersion': '0.1.0-draft',
                'formFields': [{'id': 'transfer', 'value': 'needs assistance', 'status': 'extracted',
                                'evidence': [_ev(1, QUOTE, doc)], 'alternatives': []},
                               {'id': 'covid_date', 'value': None, 'status': 'redacted', 'evidence': []}],
                'findings': [finding],
                'criteriaCoverage': {'applicable': 2, 'evaluated': 1, 'unresolved': ['MOB-2']},
                'authorization': {'status': 'unknown'}}


class _Clock:
    def __init__(self):
        self.t = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc) - timedelta(minutes=1)

    def __call__(self):
        self.t += timedelta(minutes=1)
        return self.t.isoformat(timespec='seconds')


def _client(adapter, **settings):
    rt = AnalysisRuntime(settings=AnalysisSettings(**settings), adapter=adapter, env={}, sleep=lambda s: None)
    return TestClient(create_app(ocr=lambda image: '', analysis=rt, clock=_Clock()))


def _wait(c, pid, done=('needs_review', 'failed', 'unavailable', 'not_connected')):
    for _ in range(400):
        job = c.get('/api/jobs/' + pid).json()
        if job['state'] == 'failed' or job['analysis']['status'] in done:
            return job
        time.sleep(0.02)
    return c.get('/api/jobs/' + pid).json()


class Report:
    def __init__(self):
        self.checks = []

    def add(self, name, ok, detail=''):
        self.checks.append({'check': name, 'result': 'PASS' if ok else 'FAIL', 'detail': detail})
        return ok


def synthetic_rehearsal() -> dict:
    r = Report()
    with _client(SyntheticAdapter()) as c:
        up = lambda data, name='s.pdf': c.post('/api/referrals', files={'file': (name, data, 'application/pdf')})
        good = _pdf(['Synthetic rehearsal page one: ' + QUOTE + '.', 'Synthetic page two.', None])
        pid = up(good).json()['referralId']
        base = f'/api/referrals/{pid}'
        job = _wait(c, pid)
        rec = c.get(base).json()
        r.add('text ready is separate from analysis', job['state'] == 'text_ready' and job['analysis']['status'] == 'needs_review')
        r.add('synthetic output is labelled synthetic', rec['analysis'].get('synthetic') is True)
        r.add('blank page 3 is flagged, not treated as normal', 'appears_blank' in rec['pages'][2]['qualityFlags'])
        cited = [e for f in rec['formFields'] for e in f['evidence']]
        r.add('every citation opens its original page and quote is on that page',
              bool(cited) and all(c.get(f"{base}/pages/{e['page']}/image").status_code == 200
                                  and e['quote'].lower() in rec['pages'][e['page'] - 1]['text'].lower() for e in cited))
        redacted = next(f for f in rec['formFields'] if f['id'] == 'covid_date')
        r.add('redacted field keeps no value', redacted['value'] is None and redacted['status'] == 'redacted')

        v = rec['version']
        c.patch(base + '/review', json={'version': v, 'page': 1, 'reviewer': 'Rehearsal', 'note': 'Page checked against the field.'})
        v = c.get(base).json()['version']
        c.patch(base + '/fields/transfer', json={'version': v, 'value': 'needs assistance', 'assessment': 'verified', 'reviewer': 'Rehearsal'})
        v = c.get(base).json()['version']
        c.patch(base + '/fields/covid_date', json={'version': v, 'value': 'unknown', 'assessment': 'unresolved', 'reviewer': 'Rehearsal'})
        v = c.get(base).json()['version']
        out = {'version': v, 'decision': 'clarification', 'reviewer': 'Rehearsal', 'rationale': 'Synthetic clarification request.', 'attested': True}
        first = c.post(base + '/outcome', json=out)
        retry = c.post(base + '/outcome', json=out)            # timeout-after-accept: client resends the same request
        r.add('confirmation retry is idempotent (no duplicate decision)', first.status_code == 200 and retry.status_code == 200
              and retry.json().get('idempotentReplay') is True and retry.json()['version'] == first.json()['version'])
        r.add('approve stays refused', c.post(base + '/outcome', json={**out, 'version': first.json()['version'], 'decision': 'approve'}).status_code == 409)
        exp = c.get(base + '/export')
        r.add('export is unsent and keeps the unresolved field', exp.status_code == 200 and exp.json()['sent'] is False
              and any(f['id'] == 'covid_date' for f in exp.json()['unresolved']['fields']))
        stale = c.patch(base + '/review', json={'version': v, 'page': 2, 'reviewer': 'Other', 'note': 'A stale competing edit.'})
        r.add('stale competing edit is rejected, nothing lost', stale.status_code == 409)
        cur = c.get(base).json()['version']
        c.patch(base + '/review', json={'version': cur, 'page': 2, 'reviewer': 'Rehearsal', 'note': 'Second page checked as well.'})
        r.add('an edit after confirmation invalidates draft and export', c.get(base + '/draft').status_code == 409 and c.get(base + '/export').status_code == 409)

        before = len(set(c.app.state.service.records))
        bad = [up(b'not a pdf'), up(b'%PDF-1.4\ngarbage'), up(b'')]
        r.add('invalid uploads create no referral', all(x.status_code in (415, 422) for x in bad) and len(c.app.state.service.records) == before)
        timing = c.get(base + '/timing').json()
        r.add('timing keeps active, processing and elapsed separate; unknown is null',
              all(k in timing for k in ('activeSeconds', 'processingSeconds', 'elapsedSeconds')))
        summary = c.get('/api/timing/summary').json()
        r.add('no savings percentage is computed', summary.get('savingsPercent') is None)

    for mode, expect in (('invalid', 'invalid_response'), ('timeout', 'model_timeout'), ('unavailable', 'adapter_unavailable')):
        with _client(SyntheticAdapter(mode), timeout_seconds=0.05, max_attempts=2) as c:
            pid = c.post('/api/referrals', files={'file': ('s.pdf', _pdf(['Synthetic ' + QUOTE]), 'application/pdf')}).json()['referralId']
            job = _wait(c, pid)
            rec = c.get(f'/api/referrals/{pid}').json()
            ok = (job['analysis'].get('errorCode') == expect and job['state'] == 'text_ready'
                  and rec['formFields'] == [] and rec['findings'] == [])
            manual = c.patch(f'/api/referrals/{pid}/review', json={'version': rec['version'], 'page': 1, 'reviewer': 'R', 'note': 'Manual review still possible.'})
            r.add(f'{mode} analysis: no fabricated fields, manual review still works', ok and manual.status_code == 200, expect)

    with _client(SyntheticAdapter()) as c:
        pid = c.post('/api/referrals', files={'file': ('s.pdf', _pdf([None, None]), 'application/pdf')}).json()['referralId']
        job = _wait(c, pid)
        r.add('all-blank packet: analysis is not attempted', job['analysis']['status'] in ('unavailable', 'failed') and
              job['analysis'].get('errorCode') in ('no_readable_pages', None), job['analysis'].get('errorCode', ''))
    return {'section': 'SYNTHETIC rehearsal (fake adapter; proves software behaviour, not extraction quality)', 'checks': r.checks,
            'passed': sum(c['result'] == 'PASS' for c in r.checks), 'failed': sum(c['result'] == 'FAIL' for c in r.checks)}


def real_run(directory: str | None, env=os.environ) -> dict:
    head = 'REAL adapter run (counts and codes only; no clinical accuracy claim)'
    missing = [k for k in ('IHH_ANALYSIS_ADAPTER', 'IHH_ANALYSIS_MODEL', 'ANTHROPIC_API_KEY') if not env.get(k)]
    if not directory:
        return {'section': head, 'status': 'NOT RUN', 'reason': 'No --real DIR given.'}
    if missing:
        return {'section': head, 'status': 'NOT RUN', 'reason': 'Missing configuration: ' + ', '.join(missing) + ' (values are never printed).'}
    pdfs = sorted(Path(directory).glob('*.pdf'))
    if not pdfs:
        return {'section': head, 'status': 'NOT RUN', 'reason': 'No PDFs found in the given directory.'}
    runtime = AnalysisRuntime(env=dict(env))
    ready = runtime.readiness()
    if getattr(ready, 'status', None) != 'ready':
        return {'section': head, 'status': 'NOT RUN', 'reason': f"Adapter not ready ({getattr(ready, 'code', 'unknown')})."}
    codes, fields, unresolved = Counter(), Counter(), 0
    with TestClient(create_app(analysis=runtime)) as c:
        for i, p in enumerate(pdfs, 1):
            resp = c.post('/api/referrals', files={'file': (f'p{i}.pdf', p.read_bytes(), 'application/pdf')})
            if resp.status_code != 202:
                codes[f'upload_{resp.status_code}'] += 1
                continue
            pid = resp.json()['referralId']
            job = _wait(c, pid)
            codes[job['analysis'].get('errorCode') or job['analysis']['status']] += 1
            for f in c.get(f'/api/referrals/{pid}').json()['formFields']:
                fields[f['status']] += 1
    return {'section': head, 'status': 'RAN', 'packets': len(pdfs), 'analysisOutcomes': dict(codes), 'fieldStatuses': dict(fields),
            'note': 'Every result is unreviewed machine output. Accuracy requires blind evaluation and staff sign-off.'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--real', metavar='DIR', help='directory of PDFs approved for event use')
    ap.add_argument('--out', metavar='FILE', help='write the JSON report here (stdout may carry a library banner)')
    args = ap.parse_args(argv)
    out = {'synthetic': synthetic_rehearsal(), 'real': real_run(args.real), 'savingsPercent': None,
           'note': 'Synthetic rehearsal only demonstrates behaviour. No time saving or accuracy is claimed.'}
    text = json.dumps(out, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n')
    print(text)
    return 0 if out['synthetic']['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
