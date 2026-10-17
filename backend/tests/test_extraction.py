"""BE-03 tests: synthetic fixture, draft schema and the extraction adapter. No model is called."""
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator

from backend import analysis as an
from backend import extraction as ex

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / 'backend/fixtures/synthetic-analysis-result.json').read_text())
SCHEMA = json.loads((ROOT / 'docs/schemas/analysis-result.draft.schema.json').read_text())
CRIT = ROOT / 'challenges/1-referral-intake/criteria'


def request(model='synthetic-model'):
    pages = tuple(an.PageInput(p['page'], p['state'], p['text']) for p in FIXTURE['request']['pages'])
    return an.AnalysisRequest(FIXTURE['request']['referralId'], pages, model, 5.0, CRIT)


def settings(**kw):
    return an.AnalysisSettings(criteria_dir=CRIT, model='synthetic-model', max_attempts=2, **kw)


class FakeClient:
    def __init__(self, text=None, stop_reason='end_turn', error=None):
        self.text, self.stop_reason, self.error, self.calls = text, stop_reason, error, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return SimpleNamespace(content=[SimpleNamespace(text=self.text)], stop_reason=self.stop_reason)


def adapter(client, env=None):
    return ex.ClaudeExtractionAdapter(settings(), env={'ANTHROPIC_API_KEY': 'k'} if env is None else env,
                                      client_factory=lambda key, timeout: client)


class FixtureAndSchema(unittest.TestCase):
    def test_fixture_is_labelled_synthetic(self):
        self.assertTrue(FIXTURE['_meta']['synthetic'])
        self.assertEqual(FIXTURE['_meta']['contractStatus'], 'unagreed-draft')

    def test_fixture_passes_schema_and_the_real_validator(self):
        Draft202012Validator(SCHEMA).validate(FIXTURE['result'])
        out = an.validate_analysis_result(FIXTURE['result'], request(), an.load_rules(CRIT))
        self.assertFalse(out['criteriaCoverage']['complete'])
        self.assertTrue(all(not f['reviewed'] for f in out['findings']))

    def test_fixture_covers_every_uncertain_state(self):
        self.assertEqual({f['status'] for f in FIXTURE['result']['formFields']},
                         {'conflicting', 'redacted', 'missing', 'unreadable'})
        redacted = next(f for f in FIXTURE['result']['formFields'] if f['status'] == 'redacted')
        self.assertIsNone(redacted['value'])

    def test_schema_rejects_what_the_contract_forbids(self):
        v = Draft202012Validator(SCHEMA)
        for mutate in (lambda r: r.update(extra=1), lambda r: r['formFields'][0].update(status='guess'),
                       lambda r: r['findings'][0].update(status='fails'), lambda r: r['authorization'].update(status='maybe'),
                       lambda r: r['formFields'][0]['evidence'][0].update(page=0),
                       lambda r: r['formFields'][0]['evidence'][0].update(region=[0, 0, 2, 1])):
            bad = copy.deepcopy(FIXTURE['result'])
            mutate(bad)
            self.assertFalse(v.is_valid(bad))

    def test_validator_rejects_invented_rule_page_and_quote(self):
        rules = an.load_rules(CRIT)
        for mutate in (lambda r: r['findings'][0].update(ruleId='NOPE-9'),
                       lambda r: r['formFields'][0]['evidence'][0].update(page=9),
                       lambda r: r['formFields'][0]['evidence'][0].update(quote='a quote that is not on the page'),
                       lambda r: r['findings'][2].update(status='meets')):
            bad = copy.deepcopy(FIXTURE['result'])
            mutate(bad)
            with self.assertRaises(an.InvalidAnalysisResponse):
                an.validate_analysis_result(bad, request(), rules)


class AdapterTests(unittest.TestCase):
    def test_factory_builds_no_client(self):
        a = ex.create_adapter(settings())
        self.assertIsNone(a._client)
        self.assertFalse(a.synthetic)

    def test_good_output_flows_through_the_real_pipeline(self):
        client = FakeClient(json.dumps(FIXTURE['result']))
        result, attempts = an.execute_analysis(adapter(client), request(), settings())
        self.assertEqual(attempts, 1)
        self.assertEqual(len(result['findings']), 3)
        call = client.calls[0]
        self.assertEqual(call['model'], 'synthetic-model')

    def test_prompt_treats_pages_as_untrusted_and_carries_only_criteria(self):
        client = FakeClient(json.dumps(FIXTURE['result']))
        an.execute_analysis(adapter(client), request(), settings())
        system, user = client.calls[0]['system'], client.calls[0]['messages'][0]['content']
        self.assertIn('untrusted', system)
        self.assertIn('MOB-4', system)
        self.assertNotIn('decisions', system.lower())
        self.assertIn('=== PAGE 1 ===', user)
        self.assertIn('=== PAGE 3 ===\n[no readable text: failed]', user)
        self.assertIn('REFERRAL_ID: synthetic-demo-0001', user)

    def test_fenced_json_is_accepted_but_nothing_else_is_repaired(self):
        out = ex.parse_output('```json\n{"a": 1}\n```')
        self.assertEqual(out, {'a': 1})
        with self.assertRaises(an.InvalidAnalysisResponse):
            ex.parse_output('Here you go: {"a": 1}')

    def test_truncated_nonjson_and_invalid_output_never_become_results(self):
        cases = {'truncated': FakeClient(json.dumps(FIXTURE['result']), stop_reason='max_tokens'),
                 'not json': FakeClient('sorry, I cannot'),
                 'invented rule': FakeClient(json.dumps({**FIXTURE['result'], 'findings': [
                     {**FIXTURE['result']['findings'][0], 'ruleId': 'NOPE-9'}]}))}
        for name, client in cases.items():
            with self.subTest(name), self.assertRaises(an.AnalysisError) as ctx:
                an.execute_analysis(adapter(client), request(), settings(), sleep=lambda s: None)
            self.assertEqual(ctx.exception.attempts, 2, 'bounded retry')

    def test_api_errors_map_to_static_messages(self):
        class RateLimitError(Exception): pass
        class AuthenticationError(Exception): pass
        secret = 'PATIENT TEXT SHOULD NEVER APPEAR'
        with self.assertRaises(an.AnalysisRetryable) as r:
            adapter(FakeClient(error=RateLimitError(secret))).analyze(request())
        with self.assertRaises(an.AnalysisUnavailable) as u:
            adapter(FakeClient(error=AuthenticationError(secret))).analyze(request())
        self.assertNotIn(secret, str(r.exception) + str(u.exception))

    def test_missing_key_or_model_is_unavailable_and_never_calls_a_model(self):
        client = FakeClient('{}')
        with self.assertRaises(an.AnalysisUnavailable) as e:
            adapter(client, env={}).analyze(request())
        self.assertEqual(e.exception.code, 'credentials_missing')
        with self.assertRaises(an.AnalysisUnavailable) as e:
            adapter(client).analyze(request(model=None))
        self.assertEqual(e.exception.code, 'model_not_configured')
        self.assertEqual(client.calls, [])


if __name__ == '__main__':
    unittest.main()
