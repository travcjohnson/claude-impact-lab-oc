"""BE-05 tests. Invented packet text and invented labels only; no model is called."""
import builtins
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import evaluation as ev

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT / 'challenges' / '1-referral-intake' / 'criteria'


def good(suggestion='hold', page=1, status='unknown'):
    return json.dumps({'suggestion': suggestion, 'reason': 'Synthetic reason.',
                       'rules': [{'rule': 'Synthetic rule', 'status': status, 'evidence': 'invented line', 'page': page}],
                       'contradictions': [], 'ask_hospital': []})


class Recorder:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, system, user):
        self.calls.append((system, user))
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.packets, self.out, self.crit = self.tmp / 'packets', self.tmp / 'out', self.tmp / 'criteria'
        self.packets.mkdir()
        shutil.copytree(CRITERIA, self.crit, ignore=shutil.ignore_patterns('source'))
        (self.packets / 'X01_p-01.txt').write_text('PAGE ONE invented text', encoding='utf-8')
        (self.packets / 'X01_p-03.txt').write_text('PAGE THREE invented text', encoding='utf-8')

    def run_suggest(self, rec, **kw):
        kw.setdefault('model', 'synthetic-model')
        return ev.suggest(self.packets, self.crit, self.out, rec, **kw)


class SuggestTests(Base):
    def test_never_opens_the_labels_file(self):
        labels = self.tmp / 'labels.json'
        labels.write_text(json.dumps({'packets': [{'packet_id': 'X01', 'decision': 'approve'}]}))
        opened = []
        real_open, real_io_open = builtins.open, io.open

        def spy(file, *a, **k):
            opened.append(str(file))
            return real_open(file, *a, **k)

        def spy_io(file, *a, **k):
            opened.append(str(file))
            return real_io_open(file, *a, **k)
        with mock.patch('builtins.open', spy), mock.patch('io.open', spy_io):
            self.run_suggest(Recorder(good()))
        self.assertTrue(opened, 'spy should have seen file access')
        self.assertFalse([p for p in opened if p.endswith('labels.json')])

    def test_model_input_has_criteria_and_packet_only(self):
        rec = Recorder(good())
        self.run_suggest(rec)
        system, user = rec.calls[0]
        self.assertIn('untrusted evidence', system)
        self.assertNotIn('decision', user.lower().replace('decisions', ''))
        self.assertIn('=== PAGE 1 ===', user)

    def test_original_page_numbers_survive_a_missing_page(self):
        rec = Recorder(good())
        self.run_suggest(rec)
        user = rec.calls[0][1]
        self.assertIn('=== PAGE 1 ===', user)
        self.assertIn('=== PAGE 3 ===', user)
        self.assertNotIn('=== PAGE 2 ===', user)

    def test_citing_the_missing_page_is_rejected(self):
        run = self.run_suggest(Recorder(good(page=2)))
        self.assertEqual(run['packets'][0]['status'], 'failed')
        self.assertEqual(run['packets'][0]['errorCode'], 'invalid_output')

    def test_same_inputs_reuse_cache_and_say_so(self):
        rec = Recorder(good())
        self.run_suggest(rec)
        second = self.run_suggest(rec)
        self.assertEqual(len(rec.calls), 1)
        self.assertTrue(second['packets'][0]['reusedFromCache'])
        self.run_suggest(rec, refresh=True)
        self.assertEqual(len(rec.calls), 2)

    def test_changed_inputs_never_reuse_old_output(self):
        rec = Recorder(good())
        self.run_suggest(rec)
        (self.packets / 'X01_p-01.txt').write_text('PAGE ONE edited text', encoding='utf-8')
        self.run_suggest(rec)
        self.assertEqual(len(rec.calls), 2, 'edited packet text')
        (self.crit / 'admission-criteria.md').write_text('# changed criteria\n', encoding='utf-8')
        self.run_suggest(rec)
        self.assertEqual(len(rec.calls), 3, 'edited criteria')
        self.run_suggest(rec, model='other-model')
        self.assertEqual(len(rec.calls), 4, 'different model')
        with mock.patch.object(ev, 'PROMPT_VERSION', 'blind-next'):
            self.run_suggest(rec)
        self.assertEqual(len(rec.calls), 5, 'different prompt version')

    def test_metadata_is_recorded(self):
        run = self.run_suggest(Recorder(good()), now=lambda: '2026-01-01T00:00:00+00:00')
        e = run['packets'][0]
        for key in ('packetHash', 'criteriaHash', 'promptVersion', 'model', 'schemaVersion', 'generatedAt', 'status'):
            self.assertTrue(e.get(key), key)
        self.assertTrue((self.out / 'runs' / f"{run['runId']}.json").is_file())

    def test_bad_outputs_are_failures_not_results_and_are_not_cached(self):
        bad = ['not json', good()[:40], json.dumps({'suggestion': 'maybe'}), good(status='fails'),
               good(suggestion='approve', status='unknown'), good(status='meets', page=None),
               TimeoutError('slow')]
        for reply in bad:
            with self.subTest(reply=str(reply)[:30]):
                run = self.run_suggest(Recorder(reply))
                self.assertEqual(run['packets'][0]['status'], 'failed')
                self.assertNotIn('suggestion', run['packets'][0])
                self.assertEqual(list((self.out / 'cache').glob('*.json')), [])
        ok = self.run_suggest(Recorder(good()))
        self.assertEqual(ok['packets'][0]['status'], 'completed')

    def test_model_id_is_required(self):
        with self.assertRaises(ValueError):
            self.run_suggest(Recorder(good()), model=' ')


def run_of(*entries, **kw):
    return {'runId': 'r1', 'model': 'm', 'promptVersion': 'p', 'criteriaHash': 'c', 'schemaVersion': 's',
            'packets': list(entries), **kw}


def done(pid, suggestion):
    return {'packetId': pid, 'status': 'completed', 'criteriaHash': 'c', 'suggestion': {'suggestion': suggestion}}


class ScoreTests(unittest.TestCase):
    def test_zero_completed_is_not_a_success_claim(self):
        s = ev.score(run_of({'packetId': 'A', 'status': 'failed'}), {'A': 'approve', 'B': 'deny'})
        self.assertEqual(s['verdict'], 'No evaluated results.')
        self.assertNotIn('agreement', s)
        self.assertEqual(s['accounting']['expected'], 2)
        self.assertEqual((s['failedIds'], s['missingIds']), (['A'], ['B']))

    def test_accounting_keeps_every_case_visible(self):
        labels = {'A': 'approve', 'B': 'deny', 'C': 'approve', 'D': 'deny', 'E': 'approve'}
        run = run_of(done('A', 'approve'), done('B', 'approve'), done('C', 'hold'),
                     {'packetId': 'D', 'status': 'failed'}, done('Z', 'deny'))
        s = ev.score(run, labels)
        self.assertEqual(s['accounting'], {'expected': 5, 'attempted': 4, 'completed': 3, 'failed': 1,
                                           'missing': 1, 'unmatched': 1, 'holds': 1})
        self.assertEqual(s['agreement'], {'matched': 1, 'decisive': 2, 'expected': 5})
        self.assertEqual(s['holdIds'], ['C'])
        queue = {r['packetId']: r for r in s['reviewQueue']}
        self.assertEqual(set(queue), {'B', 'C'})
        self.assertIn('unknown', queue['B']['why'])
        self.assertIn('not accuracy', s['verdict'])
        self.assertEqual(s['reviewerCheck']['done'], [])
        self.assertIn('NOT DONE', ev.format_summary(s))

    def test_reviewer_check_is_recorded_only_when_supplied(self):
        s = ev.score(run_of(done('A', 'approve')), {'A': 'approve'}, reviews={'A': {'claimsChecked': 3}})
        self.assertEqual(s['reviewerCheck']['done'], ['A'])

    def test_stale_criteria_is_flagged(self):
        s = ev.score(run_of(done('A', 'approve')), {'A': 'approve'}, criteria_dir=CRITERIA)
        self.assertEqual(s['staleCriteriaIds'], ['A'])

    def test_scoring_needs_no_sdk_or_network_or_key(self):
        code = ('import sys,json;from backend import evaluation as e;'
                's=e.score({"runId":"r","model":"m","promptVersion":"p","criteriaHash":"c","schemaVersion":"s","packets":[]},{"A":"approve"});'
                'assert "anthropic" not in sys.modules;print(s["verdict"])')
        env = {'PATH': '', 'PYTHONPATH': str(ROOT)}
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=ROOT, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('No evaluated results.', out.stdout)

    def test_cli_requires_a_model_for_suggest(self):
        self.assertEqual(ev.main(['suggest', '--packets', '.', '--out', '.', '--model', '']), 2)


if __name__ == '__main__':
    unittest.main()

class EvidenceTypeTests(unittest.TestCase):
    def test_conclusions_reject_null_and_non_text_evidence(self):
        for status in ('meets', 'unmet', 'conflict'):
            for evidence in (None, False, 1, [], {}, '', '   '):
                with self.subTest(status=status, evidence=evidence):
                    obj = json.loads(good(status=status))
                    obj['rules'][0]['evidence'] = evidence
                    with self.assertRaises(ValueError):
                        ev.validate_suggestion(obj, {1})
