"""Boundary between the packet service and a clinical-analysis adapter (BE-01 integration slice).

This module never calls a model by itself. It defines:

* explicit server-side configuration (`AnalysisSettings`, environment variables only);
* the adapter interface (`AnalysisAdapter`) that Harjeev's BE-03 extraction module implements;
* bounded execution (timeout, limited retry) that always ends in a result or a visible error;
* `validate_analysis_result`, the single seam that rejects anything that is not traceable to the
  OCR text. It enforces the DRAFT field/finding shapes proposed in
  docs/frontend-research-and-handoff.md. The BE-03 contract is not agreed yet
  (`CONTRACT_STATUS`); when it is, replace this one function and its constants.

Nothing here runs at import time: no model client, no file reads, no network. A model client is
constructed only inside an adapter factory, which `load_adapter` calls on the inference path.
Document text is untrusted evidence. Error messages are static strings plus index paths; they never
contain document text, model output, exception text or credentials.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Protocol

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CRITERIA_DIR = ROOT / 'challenges' / '1-referral-intake' / 'criteria'
CRITERIA_FILE = 'admission-criteria.json'
API_KEY_ENV = 'ANTHROPIC_API_KEY'
CONTRACT_STATUS = 'unagreed-draft'

DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_ATTEMPTS = 2
MAX_ATTEMPTS_LIMIT = 3

log = logging.getLogger('ihh.analysis')


# --------------------------------------------------------------------------- errors

class AnalysisError(Exception):
    """Base class. `str(error)` is always safe to show to the person reviewing."""
    code = 'analysis_failed'
    retryable = False

    def __init__(self, message: str, code: str | None = None, retryable: bool | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.attempts = 0


class AnalysisUnavailable(AnalysisError):
    """Analysis cannot run (configuration, credentials, adapter). Never retried."""
    code = 'unavailable'


class AnalysisRetryable(AnalysisError):
    """Transient adapter problem (rate limit, 5xx, truncated output). Retried within the bound."""
    code = 'transient_error'
    retryable = True


class AnalysisTimeout(AnalysisError):
    code = 'model_timeout'


class InvalidAnalysisResponse(AnalysisError):
    code = 'invalid_response'
    retryable = True

    def __init__(self, reason: str, path: str):
        self.reason = reason
        self.path = path
        super().__init__(f'The analysis response was rejected ({reason}) at {path}. No analysis was produced.')


# --------------------------------------------------------------------------- configuration

@dataclass(frozen=True)
class AnalysisSettings:
    adapter: str | None = None            # 'backend.module:factory'; None = analysis not connected
    model: str | None = None              # no default: choose and verify an accessible model ID
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    criteria_dir: Path = DEFAULT_CRITERIA_DIR
    problems: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> 'AnalysisSettings':
        env = os.environ if env is None else env
        problems: list[str] = []

        def text(name):
            return (env.get(name) or '').strip() or None

        timeout = DEFAULT_TIMEOUT_SECONDS
        if text('IHH_ANALYSIS_TIMEOUT_SECONDS'):
            try:
                timeout = float(text('IHH_ANALYSIS_TIMEOUT_SECONDS'))
                if not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
                    raise ValueError
            except ValueError:
                timeout = DEFAULT_TIMEOUT_SECONDS
                problems.append(f'IHH_ANALYSIS_TIMEOUT_SECONDS must be a number from 1 to {int(MAX_TIMEOUT_SECONDS)}.')
        attempts = DEFAULT_MAX_ATTEMPTS
        if text('IHH_ANALYSIS_MAX_ATTEMPTS'):
            try:
                attempts = int(text('IHH_ANALYSIS_MAX_ATTEMPTS'))
                if not 1 <= attempts <= MAX_ATTEMPTS_LIMIT:
                    raise ValueError
            except ValueError:
                attempts = DEFAULT_MAX_ATTEMPTS
                problems.append(f'IHH_ANALYSIS_MAX_ATTEMPTS must be an integer from 1 to {MAX_ATTEMPTS_LIMIT}.')
        criteria = DEFAULT_CRITERIA_DIR
        if text('IHH_CRITERIA_DIR'):
            criteria = Path(text('IHH_CRITERIA_DIR'))
            criteria = criteria if criteria.is_absolute() else ROOT / criteria
        return cls(adapter=text('IHH_ANALYSIS_ADAPTER'), model=text('IHH_ANALYSIS_MODEL'),
                   timeout_seconds=timeout, max_attempts=attempts, criteria_dir=criteria,
                   problems=tuple(problems))


@dataclass(frozen=True)
class Readiness:
    status: str          # not_connected | unavailable | ready
    code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class PageInput:
    page: int            # 1-based original PDF page number
    state: str           # 'ready' | 'failed' | 'no_text_detected' | 'pending'
    text: str            # UNTRUSTED, UNVERIFIED OCR/native text. Evidence, never instructions.


@dataclass(frozen=True)
class AnalysisRequest:
    referral_id: str
    pages: tuple[PageInput, ...]
    model: str | None
    timeout_seconds: float
    criteria_dir: Path


class AnalysisAdapter(Protocol):
    """What BE-03's extraction module provides.

    `name` and `synthetic` are required. A fake/fixture adapter MUST set synthetic = True so its
    output is never mistaken for real extraction. Pass `request.timeout_seconds` to the model client.
    Raise AnalysisRetryable / AnalysisUnavailable / AnalysisError with static messages only.
    Return a dict in the draft contract shape (see validate_analysis_result).
    """
    name: str
    synthetic: bool

    def analyze(self, request: AnalysisRequest) -> dict: ...


class AnalysisRuntime:
    """Configuration plus lazy adapter construction. Constructing this object is cheap and offline."""

    def __init__(self, settings: AnalysisSettings | None = None, adapter: AnalysisAdapter | None = None,
                 env: Mapping[str, str] | None = None, sleep=time.sleep):
        self.env = os.environ if env is None else env
        self.settings = settings or AnalysisSettings.from_env(self.env)
        self.injected = adapter      # tests/fixtures only; env configuration cannot select a fake
        self.sleep = sleep

    def readiness(self) -> Readiness:
        s = self.settings
        if self.injected is None and not s.adapter:
            return Readiness('not_connected', 'adapter_not_configured',
                             'No analysis adapter is configured. OCR text is unverified and no findings were produced.')
        if s.problems:
            return Readiness('unavailable', 'invalid_configuration', ' '.join(s.problems))
        if not (s.criteria_dir / CRITERIA_FILE).is_file():
            return Readiness('unavailable', 'criteria_unavailable',
                             f'Criteria file {CRITERIA_FILE} was not found in the configured criteria directory.')
        if self.injected is not None:
            return Readiness('ready')
        parsed = parse_adapter_spec(s.adapter)
        if parsed is None:
            return Readiness('unavailable', 'invalid_configuration',
                             "IHH_ANALYSIS_ADAPTER must look like 'backend.module:factory'.")
        if not _module_exists(parsed[0]):
            return Readiness('unavailable', 'adapter_unavailable',
                             'The configured analysis module was not found. The BE-03 extraction module may not be merged yet.')
        if not s.model:
            return Readiness('unavailable', 'model_not_configured',
                             'IHH_ANALYSIS_MODEL is not set. Choose a model ID and verify it with: python3 -m backend.analysis check-model')
        if not (self.env.get(API_KEY_ENV) or '').strip():
            return Readiness('unavailable', 'credentials_missing',
                             f'{API_KEY_ENV} is not set on the server. Analysis was not attempted.')
        return Readiness('ready')

    def adapter(self) -> AnalysisAdapter:
        """Inference path only. May construct a model client inside the adapter factory."""
        return self.injected if self.injected is not None else load_adapter(self.settings)


def _import_module(name: str):
    return importlib.import_module(name)


def _module_exists(name: str) -> bool:
    """Locate a module without executing it (no adapter code, no client, no network)."""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def parse_adapter_spec(spec: str | None) -> tuple[str, str] | None:
    """'backend.module:factory' -> (module, factory); anything else is rejected. Operator config only."""
    module_name, _, factory_name = (spec or '').partition(':')
    if re.fullmatch(r'backend(\.[A-Za-z_]\w*)+', module_name) and re.fullmatch(r'[A-Za-z_]\w*', factory_name):
        return module_name, factory_name
    return None


def load_adapter(settings: AnalysisSettings) -> AnalysisAdapter:
    parsed = parse_adapter_spec(settings.adapter)
    if parsed is None:
        raise AnalysisUnavailable("IHH_ANALYSIS_ADAPTER must look like 'backend.module:factory'.",
                                  code='invalid_configuration')
    module_name, factory_name = parsed
    try:
        factory = getattr(_import_module(module_name), factory_name, None)
    except Exception:
        raise AnalysisUnavailable('The configured analysis module could not be imported.',
                                  code='adapter_unavailable') from None
    if not callable(factory):
        raise AnalysisUnavailable('The configured analysis factory was not found.', code='adapter_unavailable')
    try:
        adapter = factory(settings)
    except AnalysisError:
        raise
    except Exception:
        raise AnalysisUnavailable('The analysis adapter could not be created.', code='adapter_unavailable') from None
    if not callable(getattr(adapter, 'analyze', None)) or not isinstance(getattr(adapter, 'name', None), str) \
            or not isinstance(getattr(adapter, 'synthetic', None), bool):
        raise AnalysisUnavailable("The analysis adapter must provide analyze(), a string 'name' and a boolean 'synthetic'.",
                                  code='adapter_unavailable')
    return adapter


# --------------------------------------------------------------------------- bounded execution

def _call_with_timeout(adapter, request: AnalysisRequest, timeout: float):
    box: dict[str, Any] = {}

    def target():
        try:
            box['result'] = adapter.analyze(request)
        except Exception as exc:  # re-raised in the caller; never logged with content
            box['error'] = exc

    worker = threading.Thread(target=target, name='analysis-call', daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        # The call cannot be cancelled from here; its late answer is discarded.
        raise AnalysisTimeout(f'The model did not answer within {timeout:g} seconds. No analysis was produced.')
    if 'error' in box:
        raise box['error']
    return box['result']


def execute_analysis(adapter, request: AnalysisRequest, settings: AnalysisSettings, sleep=time.sleep):
    """Returns (normalized_result, attempts) or raises AnalysisError with `.attempts` set.

    Only transient errors and rejected responses are retried, at most `max_attempts` calls in total.
    Timeouts are not retried: the abandoned call may still be running.
    """
    rules = load_rules(settings.criteria_dir)    # before any model call
    attempts = 0
    while True:
        attempts += 1
        try:
            return validate_analysis_result(_call_with_timeout(adapter, request, settings.timeout_seconds),
                                            request, rules), attempts
        except AnalysisError as exc:
            error = exc
        except Exception as exc:
            log.warning('analysis adapter raised %s', type(exc).__name__)
            error = AnalysisError('The analysis adapter failed unexpectedly. No analysis was produced.',
                                  code='adapter_error')
        error.attempts = attempts
        if not error.retryable or attempts >= settings.max_attempts:
            raise error
        sleep(min(0.5 * attempts, 2.0))


# --------------------------------------------------------------------------- criteria

@lru_cache(maxsize=4)
def _rules_cached(path: str) -> tuple[tuple[str, str], ...]:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return tuple((rule['id'], rule['kind']) for rule in data['rules'])


def load_rules(criteria_dir: Path) -> dict[str, str]:
    """Rule ID -> kind from the explicit criteria directory. Read on the inference path only."""
    try:
        return dict(_rules_cached(str((Path(criteria_dir) / CRITERIA_FILE).resolve())))
    except Exception:
        raise AnalysisUnavailable('The criteria file could not be read.', code='criteria_unavailable') from None


# --------------------------------------------------------------------------- validation (DRAFT contract)

FIELD_STATUSES = {'extracted', 'missing', 'redacted', 'conflicting', 'unreadable'}
FINDING_STATUSES = {'meets', 'unmet', 'unknown', 'conflict', 'not_applicable', 'clinical_review'}
SOURCE_QUALITY = {'readable', 'uncertain', 'unreadable'}
AUTH_STATUSES = {'unknown', 'requested', 'approved', 'denied'}
FORBIDDEN_KEYS = {'decision', 'suggestion', 'recommendation', 'disposition', 'approve', 'deny'}
NON_PASS_FAIL_KINDS = {'ask', 'note'}   # questions and context are not pass/fail rules
MAX_ITEMS, MAX_EVIDENCE, MAX_TEXT = 200, 10, 2000
ID_RE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
VERSION_RE = re.compile(r'^\d+\.\d+(\.\d+)?(-[a-z0-9.]+)?$')


def _reject(reason: str, path: str):
    raise InvalidAnalysisResponse(reason, path)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value, path, *, allow_none=False, limit=MAX_TEXT):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        _reject('invalid_text', path)
    return value


def _object(value, allowed: set[str], path: str, required: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        _reject('not_an_object', path)
    if FORBIDDEN_KEYS & {str(k).lower() for k in value}:
        _reject('decision_not_permitted', path)
    if set(value) - allowed:
        _reject('unsupported_key', path)
    if (required or allowed) - set(value):
        _reject('missing_key', path)
    return value


def _norm(text: str) -> str:
    return ' '.join(text.split()).casefold()


def _evidence(items, request: AnalysisRequest, pages: dict[int, PageInput], path: str) -> list[dict]:
    if not isinstance(items, list) or len(items) > MAX_EVIDENCE:
        _reject('invalid_evidence_list', path)
    out = []
    for i, raw in enumerate(items):
        here = f'{path}[{i}]'
        ev = _object(raw, {'documentId', 'page', 'quote', 'region', 'sourceQuality'}, here)
        if ev['documentId'] != request.referral_id:
            _reject('unknown_document', f'{here}.documentId')
        if not _is_int(ev['page']) or ev['page'] not in pages:
            _reject('page_out_of_bounds', f'{here}.page')
        quote = _text(ev['quote'], f'{here}.quote', allow_none=True)
        region = ev['region']
        if region is not None and not (isinstance(region, list) and len(region) == 4 and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in region)):
            _reject('invalid_region', f'{here}.region')
        if region is not None and (region[2] <= 0 or region[3] <= 0 or
                                   region[0] + region[2] > 1 or region[1] + region[3] > 1):
            _reject('invalid_region', f'{here}.region')
        if ev['sourceQuality'] not in SOURCE_QUALITY:
            _reject('invalid_source_quality', f'{here}.sourceQuality')
        page = pages[ev['page']]
        if page.state != 'ready':
            # A failed/empty page can only be cited as unreadable; there is no text to quote.
            if quote is not None or ev['sourceQuality'] != 'unreadable':
                _reject('evidence_on_unreadable_page', here)
        elif quote is not None and _norm(quote) not in _norm(page.text):
            _reject('quote_not_in_source', f'{here}.quote')
        out.append({**ev, 'quoteVerified': True if quote is not None else None})
    return out


def _require_support(evidence: list[dict], path: str):
    """A factual assertion needs at least one readable, locatable source span.

    This checks traceability, not whether the source semantically proves the assertion.
    Unreadable references remain valid for uncertainty records only.
    """
    if not any(e['sourceQuality'] == 'readable' and
               (e['quoteVerified'] is True or e['region'] is not None)
               for e in evidence):
        _reject('assertion_without_readable_source', path)


def validate_analysis_result(result: Any, request: AnalysisRequest, rules: dict[str, str]) -> dict:
    """Return a normalized copy or raise InvalidAnalysisResponse. Never repairs or invents content.

    Server-controlled: every `reviewed` flag is set to False here; a model cannot mark anything reviewed.
    """
    top = _object(result, {'schemaVersion', 'formFields', 'findings', 'criteriaCoverage', 'authorization'}, 'result')
    if not isinstance(top['schemaVersion'], str) or not VERSION_RE.match(top['schemaVersion']) \
            or len(top['schemaVersion']) > 32:
        _reject('invalid_schema_version', 'result.schemaVersion')
    pages = {p.page: p for p in request.pages}

    raw_fields = top['formFields']
    if not isinstance(raw_fields, list) or len(raw_fields) > MAX_ITEMS:
        _reject('invalid_list', 'result.formFields')
    fields, field_ids = [], set()
    for i, raw in enumerate(raw_fields):
        here = f'result.formFields[{i}]'
        f = _object(raw, {'id', 'value', 'status', 'evidence', 'alternatives', 'review'}, here,
                    {'id', 'value', 'status', 'evidence'})
        if not isinstance(f['id'], str) or not ID_RE.match(f['id']) or f['id'] in field_ids:
            _reject('invalid_or_duplicate_id', f'{here}.id')
        field_ids.add(f['id'])
        if f['status'] not in FIELD_STATUSES:
            _reject('invalid_status', f'{here}.status')
        value = f['value']
        if value is not None and (isinstance(value, str) and len(value) > MAX_TEXT
                                  or not isinstance(value, (str, bool, int, float))):
            _reject('invalid_value', f'{here}.value')
        evidence = _evidence(f['evidence'], request, pages, f'{here}.evidence')
        alternatives = []
        raw_alts = f.get('alternatives', [])
        if not isinstance(raw_alts, list) or len(raw_alts) > MAX_EVIDENCE:
            _reject('invalid_list', f'{here}.alternatives')
        for j, alt in enumerate(raw_alts):
            a = _object(alt, {'value', 'evidence'}, f'{here}.alternatives[{j}]')
            alternatives.append({'value': _text(a['value'], f'{here}.alternatives[{j}].value'),
                                 'evidence': _evidence(a['evidence'], request, pages, f'{here}.alternatives[{j}].evidence')})
        if f['status'] == 'extracted' and (value is None or not evidence):
            _reject('extracted_without_value_or_evidence', here)
        if f['status'] == 'extracted':
            _require_support(evidence, f'{here}.evidence')
        if f['status'] in ('missing', 'redacted', 'unreadable') and value is not None:
            _reject('value_on_non_extracted_field', f'{here}.value')   # redacted dates stay null
        if f['status'] == 'conflicting' and not alternatives:
            _reject('conflict_without_alternatives', f'{here}.alternatives')
        fields.append({'id': f['id'], 'value': value, 'status': f['status'], 'evidence': evidence,
                       'alternatives': alternatives, 'review': {'reviewed': False, 'reviewerId': None, 'note': None}})

    raw_findings = top['findings']
    if not isinstance(raw_findings, list) or len(raw_findings) > MAX_ITEMS:
        _reject('invalid_list', 'result.findings')
    findings, finding_ids = [], set()
    for i, raw in enumerate(raw_findings):
        here = f'result.findings[{i}]'
        f = _object(raw, {'id', 'ruleId', 'criteriaVersion', 'status', 'fieldIds', 'evidence', 'rationale', 'reviewed'},
                    here, {'id', 'ruleId', 'criteriaVersion', 'status', 'fieldIds', 'evidence', 'rationale'})
        if not isinstance(f['id'], str) or not ID_RE.match(f['id']) or f['id'] in finding_ids:
            _reject('invalid_or_duplicate_id', f'{here}.id')
        finding_ids.add(f['id'])
        if f['ruleId'] not in rules:
            _reject('unknown_rule_id', f'{here}.ruleId')
        _text(f['criteriaVersion'], f'{here}.criteriaVersion', limit=64)
        if f['status'] not in FINDING_STATUSES:
            _reject('invalid_status', f'{here}.status')
        if not isinstance(f['fieldIds'], list) or any(x not in field_ids for x in f['fieldIds']):
            _reject('unknown_field_id', f'{here}.fieldIds')
        evidence = _evidence(f['evidence'], request, pages, f'{here}.evidence')
        _text(f['rationale'], f'{here}.rationale')
        if f['status'] in ('meets', 'unmet') and not evidence:
            _reject('conclusion_without_evidence', here)       # missing is unknown, never "meets"
        if f['status'] in ('meets', 'unmet'):
            _require_support(evidence, f'{here}.evidence')
        if f['status'] == 'conflict' and len(evidence) < 2:
            _reject('conflict_without_two_sources', here)
        if f['status'] in ('meets', 'unmet') and rules[f['ruleId']] in NON_PASS_FAIL_KINDS:
            _reject('question_or_note_treated_as_rule', here)
        findings.append({'id': f['id'], 'ruleId': f['ruleId'], 'criteriaVersion': f['criteriaVersion'],
                         'status': f['status'], 'fieldIds': list(f['fieldIds']), 'evidence': evidence,
                         'rationale': f['rationale'], 'reviewed': False})

    cov = _object(top['criteriaCoverage'], {'applicable', 'evaluated', 'unresolved'}, 'result.criteriaCoverage')
    if not (_is_int(cov['applicable']) and _is_int(cov['evaluated'])
            and 0 <= cov['evaluated'] <= cov['applicable'] <= len(rules)):
        _reject('invalid_coverage_counts', 'result.criteriaCoverage')
    if not isinstance(cov['unresolved'], list) or any(r not in rules for r in cov['unresolved']) \
            or len(set(cov['unresolved'])) != len(cov['unresolved']):
        _reject('unknown_rule_id', 'result.criteriaCoverage.unresolved')
    if cov['evaluated'] > len({f['ruleId'] for f in findings}):
        _reject('coverage_without_findings', 'result.criteriaCoverage.evaluated')
    coverage = {'applicable': cov['applicable'], 'evaluated': cov['evaluated'], 'unresolved': list(cov['unresolved']),
                'complete': cov['applicable'] > 0 and cov['evaluated'] == cov['applicable'] and not cov['unresolved']}

    auth = _object(top['authorization'], {'status', 'evidence'}, 'result.authorization', {'status'})
    if auth['status'] not in AUTH_STATUSES:
        _reject('invalid_status', 'result.authorization.status')
    authorization = {'status': auth['status'],
                     'evidence': _evidence(auth.get('evidence', []), request, pages, 'result.authorization.evidence')}
    if auth['status'] != 'unknown' and not authorization['evidence']:
        _reject('authorization_without_evidence', 'result.authorization')

    if auth['status'] != 'unknown':
        _require_support(authorization['evidence'], 'result.authorization.evidence')

    return {'schemaVersion': top['schemaVersion'], 'formFields': fields, 'findings': findings,
            'criteriaCoverage': coverage, 'authorization': authorization}


# --------------------------------------------------------------------------- model access check (opt-in, never at startup)

def _anthropic_client(api_key: str, timeout: float):
    try:
        import anthropic
    except ImportError:
        raise AnalysisUnavailable('The anthropic package is not installed. Run: python3 -m pip install -r backend/requirements-analysis.txt',
                                  code='sdk_missing') from None
    return anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)


def verify_model_access(settings: AnalysisSettings, env: Mapping[str, str] | None = None, client_factory=None) -> dict:
    """Confirm the configured model ID is visible to the configured key (metadata lookup, no document data).

    Run it deliberately before a first analysis: `python3 -m backend.analysis check-model`.
    """
    env = os.environ if env is None else env
    if not settings.model:
        raise AnalysisUnavailable('IHH_ANALYSIS_MODEL is not set.', code='model_not_configured')
    key = (env.get(API_KEY_ENV) or '').strip()
    if not key:
        raise AnalysisUnavailable(f'{API_KEY_ENV} is not set.', code='credentials_missing')
    client = (client_factory or _anthropic_client)(key, min(settings.timeout_seconds, 30.0))
    try:
        info = client.models.retrieve(settings.model)
    except Exception as exc:
        kind = type(exc).__name__
        if kind == 'NotFoundError':
            raise AnalysisUnavailable('The model ID was not found or is not available to this key.', code='model_not_found') from None
        if kind in ('AuthenticationError', 'PermissionDeniedError'):
            raise AnalysisUnavailable('The API key was rejected for this model.', code='credentials_rejected') from None
        raise AnalysisUnavailable(f'The model lookup failed ({kind}).', code='model_check_failed') from None
    return {'model': getattr(info, 'id', settings.model), 'accessible': True}


def main(argv: list[str]) -> int:
    if argv[1:] != ['check-model']:
        print('usage: python3 -m backend.analysis check-model', file=sys.stderr)
        return 2
    try:
        print(json.dumps(verify_model_access(AnalysisSettings.from_env())))
        return 0
    except AnalysisError as exc:
        print(json.dumps({'accessible': False, 'errorCode': exc.code, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
