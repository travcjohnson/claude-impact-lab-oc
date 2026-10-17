import io
import time
import unittest

import fitz
from fastapi.testclient import TestClient
from backend.analysis import AnalysisRuntime
from backend.app import create_app


def pdf_bytes(pages=1, scanned=False, encrypted=False):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        if not scanned:
            page.insert_text((72, 72), f'Synthetic training document original page {i+1}. No patient information.')
    kwargs = {'encryption': fitz.PDF_ENCRYPT_AES_256, 'user_pw': 'test-only', 'owner_pw': 'owner'} if encrypted else {}
    data = doc.tobytes(**kwargs)
    doc.close()
    return data


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(ocr=lambda image: f'Synthetic OCR for {image.name}', analysis=AnalysisRuntime(env={})))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def upload(self, data=None, name='test.pdf'):
        return self.client.post('/api/referrals', files={'file': (name, data or pdf_bytes(), 'application/pdf')})

    def ready(self, packet_id):
        for _ in range(100):
            r = self.client.get('/api/referrals/' + packet_id)
            if r.json()['job']['state'] in ('text_ready', 'failed'):
                return r.json()
            time.sleep(.02)
        self.fail('Job did not finish')

    def test_health_and_static_asset_boundary(self):
        health = self.client.get('/health').json()
        self.assertEqual(health['service'], 'ihh-local-intake')
        self.assertFalse(health['capabilities']['clinicalAnalysis'])
        for path in ['/', '/app.js', '/backend-client.js']:
            self.assertEqual(self.client.get(path).status_code, 200)
        for path in ['/backend/app.py', '/.env', '/referral-review-repo.zip', '/api/referrals/not-found', '/api/referrals/..%2Fsecret']:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_pdf_validation(self):
        for name, content, status in [('bad.txt', b'hello', 415), ('bad.pdf', b'%PDF-broken', 422), ('empty.pdf', b'', 422)]:
            response = self.client.post('/api/referrals', files={'file': (name, content, 'application/pdf')})
            self.assertEqual(response.status_code, status)
        self.assertEqual(self.upload(pdf_bytes(encrypted=True)).status_code, 422)
        self.assertEqual(self.upload(pdf_bytes(pages=61)).status_code, 422)
        self.assertEqual(self.client.post('/api/referrals', content=b'x', headers={'content-length':str(28*1024*1024)}).status_code, 413)

    def test_true_job_and_page_provenance_without_fake_analysis(self):
        response = self.upload(pdf_bytes(pages=3))
        self.assertEqual(response.status_code, 202)
        packet = self.ready(response.json()['referralId'])
        self.assertEqual(packet['job']['state'], 'text_ready')
        self.assertEqual([p['page'] for p in packet['pages']], [1, 2, 3])
        self.assertIn('original page 3', packet['pages'][2]['text'])
        self.assertEqual(packet['findings'], [])
        self.assertFalse(packet['criteriaCoverage']['complete'])
        self.assertEqual(self.client.get(packet['pages'][2]['imageUrl']).headers['content-type'], 'image/png')
        self.assertEqual(self.client.get(f"/api/referrals/{packet['referralId']}/pages/4/image").status_code, 404)

    def test_search_returns_original_page_and_literal_matches(self):
        packet_id = self.upload(pdf_bytes(3)).json()['referralId']
        self.ready(packet_id)
        result = self.client.get('/api/referrals/'+packet_id+'/search',params={'q':'original page 3'}).json()
        self.assertEqual([m['page'] for m in result['matches']],[3])
        self.assertFalse(result['verified'])
        result = self.client.get('/api/referrals/'+packet_id+'/search',params={'q':'.*'}).json()
        self.assertEqual(result['matches'],[])

    def test_failed_ocr_page_does_not_renumber_later_page(self):
        def ocr(path):
            if path.name == 'page-2.png':
                raise RuntimeError('Synthetic processing failure')
            return 'Synthetic extracted text'
        with TestClient(create_app(ocr=ocr, analysis=AnalysisRuntime(env={}))) as c:
            response = c.post('/api/referrals', files={'file': ('scan.pdf', pdf_bytes(3, scanned=True), 'application/pdf')})
            packet_id = response.json()['referralId']
            for _ in range(100):
                packet = c.get('/api/referrals/' + packet_id).json()
                if packet['job']['state'] == 'text_ready':break
                time.sleep(.02)
            self.assertEqual([p['page'] for p in packet['pages']], [1, 2, 3])
            self.assertEqual(packet['pages'][1]['state'], 'failed')
            self.assertEqual(packet['pages'][2]['state'], 'ready')
            self.assertTrue(packet['job']['partial'])

    def test_outcomes_reject_decisions_and_invalidate_stale_drafts(self):
        packet_id = self.upload().json()['referralId']
        self.ready(packet_id)
        base = '/api/referrals/' + packet_id
        outcome = {'version':1,'decision':'approve','reviewer':'QA','rationale':'Synthetic request for clarification.','attested':True}
        self.assertEqual(self.client.post(base+'/outcome',json=outcome).status_code,409)
        outcome['decision']='deny'
        self.assertEqual(self.client.post(base+'/outcome',json=outcome).status_code,409)
        outcome['decision']='clarification'
        self.assertEqual(self.client.post(base+'/outcome',json=outcome).status_code,409)
        review={'version':1,'page':1,'reviewer':'QA','note':'Source page verified for this synthetic test.'}
        self.assertEqual(self.client.patch(base+'/review',json=review).status_code,200)
        self.assertEqual(self.client.patch(base+'/review',json=review).status_code,409)
        outcome['version']=2
        outcome['attested']=False
        self.assertEqual(self.client.post(base+'/outcome',json=outcome).status_code,409)
        outcome['attested']=True
        result=self.client.post(base+'/outcome',json=outcome)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['version'],3)
        self.assertFalse(self.client.get(base+'/draft').json()['sent'])
        review['version']=3
        self.assertEqual(self.client.patch(base+'/review',json=review).status_code,200)
        self.assertEqual(self.client.get(base+'/draft').status_code,409)

    def test_cross_origin_writes_and_untrusted_hosts_rejected(self):
        self.assertEqual(self.client.post('/api/referrals',headers={'origin':'https://example.com'}).status_code,403)
        self.assertEqual(self.client.get('/health',headers={'host':'evil.example'}).status_code,403)

    def test_session_data_removed_at_shutdown(self):
        with TestClient(create_app(ocr=lambda _: 'Synthetic OCR', analysis=AnalysisRuntime(env={}))) as c:
            root=c.app.state.service.root
            self.assertTrue(root.exists())
        self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
