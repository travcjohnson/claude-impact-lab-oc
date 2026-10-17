"""LOOP-05: the rehearsal must pass on synthetic data, never read secrets, and report the real section honestly."""
import json
import tempfile
import unittest
from pathlib import Path

from backend import rehearsal


class RehearsalTests(unittest.TestCase):
    def test_synthetic_rehearsal_passes_every_check(self):
        s = rehearsal.synthetic_rehearsal()
        failed = [c for c in s['checks'] if c['result'] != 'PASS']
        self.assertEqual(failed, [])
        self.assertGreaterEqual(len(s['checks']), 15)
        self.assertIn('SYNTHETIC', s['section'])

    def test_real_section_is_not_run_without_input_or_configuration(self):
        self.assertEqual(rehearsal.real_run(None, env={})['status'], 'NOT RUN')
        with tempfile.TemporaryDirectory() as d:
            r = rehearsal.real_run(d, env={})
            self.assertEqual(r['status'], 'NOT RUN')
            for name in ('IHH_ANALYSIS_ADAPTER', 'IHH_ANALYSIS_MODEL', 'ANTHROPIC_API_KEY'):
                self.assertIn(name, r['reason'])

    def test_real_section_never_echoes_configuration_values(self):
        env = {'IHH_ANALYSIS_ADAPTER': 'backend.nope:build', 'IHH_ANALYSIS_MODEL': 'secret-model-id', 'ANTHROPIC_API_KEY': 'sk-test-SECRET'}
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'a.pdf').write_bytes(rehearsal._pdf(['Synthetic page']))
            text = json.dumps(rehearsal.real_run(d, env=env))
        self.assertNotIn('SECRET', text)
        self.assertNotIn('secret-model-id', text)

    def test_real_section_with_no_pdfs_is_not_run(self):
        env = {'IHH_ANALYSIS_ADAPTER': 'x', 'IHH_ANALYSIS_MODEL': 'y', 'ANTHROPIC_API_KEY': 'z'}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rehearsal.real_run(d, env=env)['status'], 'NOT RUN')

    def test_cli_report_has_no_savings_claim_and_exits_zero(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rehearsal.main([])
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertIsNone(out['savingsPercent'])
        self.assertEqual(out['real']['status'], 'NOT RUN')
        self.assertNotIn('saved', buf.getvalue().lower().replace('no time saving', ''))


if __name__ == '__main__':
    unittest.main()
