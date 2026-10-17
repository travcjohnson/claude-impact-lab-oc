"""BE-02: stable original page numbers, rotation and per-page quality flags (invented PDFs only)."""
import time
import unittest

import fitz
from fastapi.testclient import TestClient

from backend.analysis import AnalysisRuntime
from backend.app import create_app


def pdf(spec):
    """spec: list of (text or None, rotation)."""
    doc = fitz.open()
    for text, rotation in spec:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
        if rotation:
            page.set_rotation(rotation)
    data = doc.tobytes()
    doc.close()
    return data


class PageTests(unittest.TestCase):
    def open(self, ocr=lambda image: ''):
        client = TestClient(create_app(ocr=ocr, analysis=AnalysisRuntime(env={})))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def process(self, client, data):
        pid = client.post('/api/referrals', files={'file': ('t.pdf', data, 'application/pdf')}).json()['referralId']
        for _ in range(200):
            record = client.get('/api/referrals/' + pid).json()
            if record['job']['state'] in ('text_ready', 'failed'):
                return pid, record
            time.sleep(.02)
        self.fail('job did not finish')

    def test_short_native_text_survives_empty_or_failed_ocr(self):
        def fail(image):
            raise RuntimeError('Synthetic OCR failure')
        for ocr, flag in ((lambda image: '', 'ocr_no_text'), (fail, 'ocr_failed')):
            with self.subTest(flag=flag):
                c = self.open(ocr)
                pid, rec = self.process(c, pdf([('Synthetic short note', 0)]))
                page = rec['pages'][0]
                self.assertEqual(page['text'], 'Synthetic short note')
                self.assertEqual(page['state'], 'ready')
                self.assertEqual(page['extractionMethod'], 'pdf-text')
                self.assertIn(flag, page['qualityFlags'])
                self.assertIn('native_text_fallback', page['qualityFlags'])
                self.assertEqual(page['quality'], 'unverified')
                self.assertEqual(c.get(f'/api/referrals/{pid}/search', params={'q': 'short note'}).json()['matches'][0]['page'], 1)

    def test_pages_one_and_three_keep_their_markers_and_page_two_is_flagged(self):
        c = self.open()
        long = ' synthetic filler text to exceed the native text threshold'
        pid, rec = self.process(c, pdf([('PAGE 1' + long, 0), (None, 0), ('PAGE 3' + long, 0)]))
        self.assertEqual([p['page'] for p in rec['pages']], [1, 2, 3])
        self.assertIn('PAGE 1', rec['pages'][0]['text'])
        self.assertIn('PAGE 3', rec['pages'][2]['text'])
        self.assertNotIn('PAGE 2', ''.join(p['text'] for p in rec['pages']))
        self.assertEqual(rec['pages'][1]['state'], 'no_text_detected')
        self.assertTrue(rec['pages'][1]['appearsBlank'])
        self.assertIn('appears_blank', rec['pages'][1]['qualityFlags'])
        self.assertIn('no_text_detected', rec['pages'][1]['qualityFlags'])
        hits = c.get(f'/api/referrals/{pid}/search', params={'q': 'PAGE 3'}).json()['matches']
        self.assertEqual([h['page'] for h in hits], [3])
        self.assertEqual(c.get(f'/api/referrals/{pid}/search', params={'q': 'PAGE 2'}).json()['matches'], [])

    def test_text_page_is_not_flagged_blank_and_text_stays_unverified(self):
        c = self.open()
        _, rec = self.process(c, pdf([('A page with enough synthetic words to count as native text.', 0)]))
        page = rec['pages'][0]
        self.assertFalse(page['appearsBlank'])
        self.assertEqual(page['qualityFlags'], ['native_text'])
        self.assertEqual(page['quality'], 'unverified')

    def test_ocr_short_and_failed_pages_are_flagged(self):
        def ocr(image):
            if image.name == 'page-2.png':
                raise RuntimeError('boom with private text')
            return 'ab'
        c = self.open(ocr)
        _, rec = self.process(c, pdf([(None, 0), (None, 0)]))
        self.assertEqual(rec['pages'][0]['qualityFlags'], ['ocr_used', 'short_text', 'appears_blank'])
        self.assertEqual(rec['pages'][1]['state'], 'failed')
        self.assertEqual(rec['pages'][1]['qualityFlags'], ['extraction_failed'])
        self.assertNotIn('private text', str(rec['pages'][1]))

    def test_original_and_upright_orientation_are_distinguishable(self):
        c = self.open()
        pid, rec = self.process(c, pdf([('Portrait source page rotated by metadata, enough words here.', 90),
                                        ('Upright page with enough synthetic words to count.', 0)]))
        self.assertEqual([p['rotation'] for p in rec['pages']], [90, 0])
        sizes = []
        for n in (1, 2):
            image = fitz.Pixmap(c.get(f'/api/referrals/{pid}/pages/{n}/image').content)
            sizes.append((image.width, image.height))
        self.assertGreater(sizes[0][0], sizes[0][1], 'rotated page is rendered upright (landscape)')
        self.assertGreater(sizes[1][1], sizes[1][0])


if __name__ == '__main__':
    unittest.main()
