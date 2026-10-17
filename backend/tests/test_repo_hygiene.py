"""BE-07 guards. These read tracked file names and source text only; no packet content, no model."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = 'challenges/1-referral-intake/eval/decisions.json'
ALLOWED_PDF_PREFIX = 'challenges/1-referral-intake/criteria/source/'


def tracked():
    try:
        out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        raise unittest.SkipTest('not a git checkout')
    return [p for p in out.splitlines() if (ROOT / p).exists()]


class RepoHygiene(unittest.TestCase):
    def test_no_archives_or_packet_files_tracked(self):
        bad = [p for p in tracked() if p.lower().endswith(('.zip', '.tar', '.tgz', '.gz', '.png', '.jpg', '.jpeg', '.tif', '.tiff'))
               or re.search(r'(^|/)R\d\d(\.pdf|_p-\d+\.txt)$', p)
               or (p.lower().endswith('.pdf') and not p.startswith(ALLOWED_PDF_PREFIX))]
        self.assertEqual(bad, [], 'Packets, scans, OCR and archives must not be tracked.')

    def test_live_code_never_references_evaluation_labels(self):
        code = [p for p in tracked() if p.startswith(('backend/', 'frontend/')) and p.endswith(('.py', '.js', '.mjs', '.cjs', '.html', '.json'))
                and p != 'backend/tests/test_repo_hygiene.py']
        hits = [p for p in code if re.search(r'decisions\.json|eval/decisions', (ROOT / p).read_text(encoding='utf-8', errors='ignore'))]
        self.assertEqual(hits, [], 'Only the offline evaluation module may name the labels file.')

    def test_ignore_rules_cover_derived_clinical_content(self):
        probes = ['runtime/x.json', 'results/R01.json', 'suggestions/R01.json', 'packets_text/R01_p-01.txt',
                  'ocr/p1.txt', 'renders/p1.png', 'server.log', '.env', 'challenges/1-referral-intake/packets/R01.pdf']
        for probe in probes:
            r = subprocess.run(['git', 'check-ignore', '-q', probe], cwd=ROOT)
            self.assertEqual(r.returncode, 0, f'{probe} must be git-ignored')

    def test_labels_file_is_not_served_or_bundled(self):
        build = (ROOT / 'frontend/scripts/build.mjs').read_text()
        self.assertNotIn('eval', build)
        self.assertNotIn('challenges/1-referral-intake/eval', (ROOT / 'backend/app.py').read_text())


if __name__ == '__main__':
    unittest.main()
