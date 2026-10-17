"""Local PDF-to-text service with an optional, explicitly configured analysis adapter.

No eligibility decisions or messaging. OCR needs no model or key; analysis runs only when
IHH_ANALYSIS_ADAPTER is configured (see backend/analysis.py and backend/README.md).

Run: python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
All document data is ephemeral, outside the checkout, and removed at shutdown.
"""
from __future__ import annotations

import copy
import hashlib
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import fitz
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.timing import TimingInput, compute as compute_timing, open_intervals, summarize
from backend.review import (
    FieldReviewInput, apply_field_review, build_export, draft_sections, now_iso, with_actions,
)
from backend.analysis import (
    CONTRACT_STATUS, AnalysisError, AnalysisRequest, AnalysisRuntime, AnalysisUnavailable, PageInput,
    execute_analysis,
)

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 60
MAX_ACTIVE_JOBS = 4
MAX_SESSION_PACKETS = 12


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    page: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(min_length=8, max_length=4000)
    @field_validator('reviewer', 'note', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class OutcomeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    decision: Literal['clarification', 'clinical-review', 'approve', 'deny']
    reviewer: str = Field(min_length=1, max_length=80)
    rationale: str = Field(min_length=12, max_length=4000)
    attested: bool
    @field_validator('reviewer', 'rationale', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


def default_ocr(image: Path) -> str:
    """No shell and no content logging. Each OCR invocation is time-bounded."""
    result = subprocess.run(
        ['tesseract', str(image), 'stdout', '--psm', '3'],
        capture_output=True, text=True, timeout=40, check=True,
    )
    return result.stdout.strip()


def appears_blank(pix) -> bool:
    """Heuristic only: almost every sampled pixel is near-white. A faint scan or light handwriting can
    still look blank, so this is a flag for a human, never proof that a page has no content."""
    samples = pix.samples[::97]
    if not samples:
        return False
    dark = sum(1 for b in samples if b < 200)
    return dark / len(samples) < 0.0005


def quality_flags(method: str, text: str, blank: bool) -> list[str]:
    """Per-page extraction flags. None of them says the text is correct; all text stays unverified."""
    flags = ['native_text' if method == 'pdf-text' else 'ocr_used']
    if not text:
        flags.append('no_text_detected')
    elif len(text) < 30:
        flags.append('short_text')
    if blank:
        flags.append('appears_blank')
    return flags


def record_field_corrected(record, field_id):
    field = next((f for f in record['formFields'] if f['id'] == field_id), None)
    return bool(field and field['review'].get('correctedValue') is not None)


class PacketService:
    def __init__(self, data_dir: Path, ocr=default_ocr, analysis: AnalysisRuntime | None = None, clock=None):
        self.root = data_dir
        self.clock = clock or now_iso
        self.timelines: dict[str, list[dict]] = {}   # BE-06: event log, no clinical content
        self.ocr = ocr
        self.analysis = analysis or AnalysisRuntime()
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.records = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='packet')
        # Model latency must not hold the OCR queue; a separate single worker runs analysis.
        self.analysis_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='analysis')
        self.active_slots = threading.BoundedSemaphore(MAX_ACTIVE_JOBS)

    def mark(self, packet_id, kind, **extra):
        """Append a timing event. Extras are labels/booleans only, never document or reviewer text."""
        with self.lock:
            version = self.records[packet_id]['version'] if packet_id in self.records else None
            self.timelines.setdefault(packet_id, []).append({'at': self.clock(), 'kind': kind, 'version': version, **extra})

    def close(self):
        self.stopping.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
        # An in-flight model call cannot be cancelled; it is a daemon thread and its answer is discarded.
        self.analysis_pool.shutdown(wait=False, cancel_futures=True)

    def skip_analysis(self, record, code, message):
        """Caller holds the lock. Analysis never ran; say so instead of leaving it 'waiting'."""
        if record['analysis']['status'] == 'waiting_for_text':
            record['analysis'] = {'status': 'unavailable', 'errorCode': code, 'error': message}

    def run_analysis(self, packet_id):
        try:
            self._run_analysis(packet_id)
            with self.lock:
                record = self.records.get(packet_id)
                if record and not self.stopping.is_set() and record['analysis']['status'] in ('needs_review', 'failed', 'unavailable'):
                    self.mark(packet_id, 'analysis_terminal', status=record['analysis']['status'])
        except Exception:
            # Never leave 'queued'/'checking' behind: it would block confirming the next step forever.
            with self.lock:
                record = self.records.get(packet_id)
                if record and record['analysis']['status'] in ('queued', 'checking'):
                    record['analysis'] = {'status': 'failed', 'errorCode': 'internal_error',
                                          'error': 'Analysis stopped unexpectedly. No analysis was produced.'}

    def _run_analysis(self, packet_id):
        runtime = self.analysis
        with self.lock:
            if self.stopping.is_set():
                return
            record = self.records[packet_id]
            record['analysis'] = {'status': 'checking'}
            request = AnalysisRequest(
                referral_id=packet_id, model=runtime.settings.model,
                timeout_seconds=runtime.settings.timeout_seconds, criteria_dir=runtime.settings.criteria_dir,
                pages=tuple(PageInput(p['page'], p['state'], p['text']) for p in record['pages']))
        try:
            adapter = runtime.adapter()   # a model client, if any, is constructed here and nowhere earlier
            result, attempts = execute_analysis(adapter, request, runtime.settings, runtime.sleep)
        except AnalysisError as exc:
            status = 'unavailable' if isinstance(exc, AnalysisUnavailable) else 'failed'
            state = {'status': status, 'errorCode': exc.code, 'error': str(exc)}
            if exc.attempts:
                state['attempts'] = exc.attempts
        except Exception:
            state = {'status': 'failed', 'errorCode': 'adapter_error',
                     'error': 'The analysis adapter failed unexpectedly. No analysis was produced.'}
        else:
            state = None
        with self.lock:
            if self.stopping.is_set():
                return
            record = self.records[packet_id]
            if state is not None:
                # Failed analysis leaves formFields/findings empty and manual review fully available.
                record['analysis'] = state
                return
            # New analysis changes the snapshot a reviewer must attest to. In-flight-state
            # guards alone cannot reject a request prepared before analysis completed.
            meta = {  # built before any mutation so a failure here cannot leave half-applied results
                'status': 'needs_review', 'contractVersion': result['schemaVersion'],
                'contractStatus': CONTRACT_STATUS, 'adapter': adapter.name, 'synthetic': adapter.synthetic,
                'model': runtime.settings.model, 'attempts': attempts,
                'note': 'Machine-generated and unreviewed. Not a verified fact, eligibility finding or decision.'}
            record.update(formFields=result['formFields'], findings=result['findings'],
                          criteriaCoverage=result['criteriaCoverage'], authorization=result['authorization'],
                          analysis=meta)
            record['version'] += 1
            record['outcome'] = None

    def get(self, packet_id):
        # User input never becomes a filesystem path.
        with self.lock:
            if packet_id not in self.records:
                raise HTTPException(404, 'Unknown referral in this server session.')
            return copy.deepcopy(self.records[packet_id])

    def process(self, packet_id):
        folder = self.root / packet_id
        try:
            with fitz.open(folder / 'packet.pdf') as pdf:
                for index in range(len(pdf)):
                    if self.stopping.is_set():
                        with self.lock:
                            self.records[packet_id]['job']['state'] = 'failed'
                            self.mark(packet_id, 'text_failed')
                            self.skip_analysis(self.records[packet_id], 'text_not_ready',
                                               'Analysis did not run because text processing stopped.')
                        return
                    with self.lock:
                        record = self.records[packet_id]
                        record['job']['state'] = 'rendering'
                        record['job']['currentPage'] = index + 1
                    image_path = folder / f'page-{index+1}.png'
                    try:
                        page = pdf[index]
                        # Bound image dimensions; never renumber missing/failed pages.
                        scale = min(2000 / max(page.rect.width, page.rect.height), 3)
                        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                        pix.save(image_path)
                        blank = appears_blank(pix)
                        with self.lock:
                            record['pages'][index]['imageUrl'] = f'/api/referrals/{packet_id}/pages/{index+1}/image'
                            record['pages'][index]['rotation'] = page.rotation
                            record['pages'][index]['appearsBlank'] = blank
                        text = page.get_text('text').strip()
                        method = 'pdf-text'
                        fallback_flags = []
                        if len(text) < 30:
                            with self.lock:
                                record['job']['state'] = 'extracting'
                            native_text = text
                            try:
                                ocr_text = self.ocr(image_path)
                            except Exception:
                                if not native_text:
                                    raise
                                # Preserve readable PDF text when optional OCR fails; never log OCR errors.
                                fallback_flags = ['ocr_failed', 'native_text_fallback']
                            else:
                                if ocr_text:
                                    text, method = ocr_text, 'ocr'
                                elif native_text:
                                    fallback_flags = ['ocr_no_text', 'native_text_fallback']
                                else:
                                    text, method = '', 'ocr'
                        with self.lock:
                            record['pages'][index].update(
                                state='ready' if text else 'no_text_detected',
                                text=text[:100000], truncated=len(text)>100000, extractionMethod=method,
                                quality='unverified' if text else 'no_text_detected',
                                qualityFlags=quality_flags(method, text, blank) + fallback_flags,
                            )
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        with self.lock:
                            record['pages'][index].update(state='failed', qualityFlags=['extraction_failed'],
                                                          error='OCR unavailable or timed out. Review the source image.')
                    except Exception:
                        # Never expose subprocess stderr or patient text in errors/logs.
                        with self.lock:
                            record['pages'][index].update(state='failed', qualityFlags=['extraction_failed'],
                                                          error='This page could not be extracted. Review the original PDF.')
                    with self.lock:
                        record['job']['completedPages'] = index + 1
                queue_analysis = False
                with self.lock:
                    record['job']['state'] = 'text_ready'
                    self.mark(packet_id, 'text_ready')
                    record['job']['partial'] = any(p['state'] != 'ready' for p in record['pages'])
                    # text_ready is OCR completion only. Analysis is queued atomically with it so a
                    # reader never sees text_ready next to a stale "waiting" analysis state.
                    if record['analysis']['status'] == 'waiting_for_text':
                        if any(p['state'] == 'ready' for p in record['pages']):
                            record['analysis'] = {'status': 'queued'}
                            queue_analysis = True
                        else:
                            self.skip_analysis(record, 'no_readable_pages',
                                               'No page produced readable text, so analysis was not attempted. Review the original pages.')
                if queue_analysis:
                    self.analysis_pool.submit(self.run_analysis, packet_id)
        except Exception:
            with self.lock:
                self.records[packet_id]['job'].update(state='failed', error='PDF processing failed. No analysis or decision was generated.')
                self.mark(packet_id, 'text_failed')
                self.skip_analysis(self.records[packet_id], 'text_not_ready',
                                   'Analysis did not run because text processing failed.')
        finally:
            self.active_slots.release()

    def initial_analysis(self):
        ready = self.analysis.readiness()
        if ready.status == 'ready':
            return {'status': 'waiting_for_text'}
        if ready.status == 'not_connected':
            return {'status': 'not_connected', 'reason': ready.message}
        return {'status': 'unavailable', 'errorCode': ready.code, 'error': ready.message}

    def register(self, path: Path, packet_id, page_count, digest):
        record = {
            'schemaVersion': '0.1', 'referralId': packet_id, 'version': 1,
            'document': {'documentId': packet_id, 'pageCount': page_count, 'sha256': digest},
            'job': {'jobId': packet_id, 'state': 'queued', 'currentPage': None,
                    'completedPages': 0, 'totalPages': page_count, 'partial': False},
            'pages': [{'page': n, 'state': 'pending', 'text': '', 'imageUrl': None,
                       'quality': 'unverified', 'extractionMethod': None, 'rotation': None, 'appearsBlank': None,
                       'qualityFlags': []} for n in range(1, page_count + 1)],
            'analysis': self.initial_analysis(),
            'formFields': [], 'findings': [],
            'criteriaCoverage': {'evaluated': 0, 'complete': False},
            'authorization': {'status': 'unknown'}, 'reviews': {}, 'outcome': None,
        }
        with self.lock:
            self.records[packet_id] = record
            self.mark(packet_id, 'received')
        self.pool.submit(self.process, packet_id)
        return record


def create_app(ocr=default_ocr, analysis: AnalysisRuntime | None = None, clock=None):
    runtime = analysis or AnalysisRuntime()   # reads configuration only; builds no client, reads no files

    @asynccontextmanager
    async def lifespan(app):
        folder = Path(tempfile.mkdtemp(prefix='ihh-local-packets-'))
        folder.chmod(0o700)
        app.state.service = PacketService(folder, ocr, runtime, clock)
        try:
            yield
        finally:
            app.state.service.close()
            shutil.rmtree(folder, ignore_errors=True)

    app = FastAPI(title='IHH local text-review prototype', lifespan=lifespan)

    @app.middleware('http')
    async def local_guards(request: Request, call_next):
        # No CORS grants, cross-site browser writes, or untrusted Host/DNS rebinding.
        if request.url.hostname not in ('127.0.0.1', 'localhost', '::1', 'testserver'):
            return JSONResponse({'detail': 'This prototype is localhost-only.'}, status_code=403)
        if request.method in ('POST', 'PATCH', 'DELETE'):
            origin = request.headers.get('origin')
            expected = f'{request.url.scheme}://{request.url.netloc}'
            if (origin and origin != expected) or request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': 'Cross-site upload/review is not permitted.'}, status_code=403)
            length = request.headers.get('content-length')
            if length and length.isdigit() and int(length) > MAX_BYTES + 1024 * 1024:
                return JSONResponse({'detail': 'Upload exceeds 25 MB.'}, status_code=413)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/health')
    def health():
        # Static configuration report only: never imports the adapter, builds a client or calls a model.
        ready = runtime.readiness()
        s = runtime.settings
        analysis_info = {'status': ready.status, 'adapterConfigured': runtime.injected is not None or bool(s.adapter),
                         'model': s.model, 'modelConfigured': bool(s.model),
                         'credentialPresent': bool((runtime.env.get('ANTHROPIC_API_KEY') or '').strip()),
                         'timeoutSeconds': s.timeout_seconds, 'maxAttempts': s.max_attempts,
                         'contractStatus': CONTRACT_STATUS, 'validated': False}
        if ready.status != 'ready':
            analysis_info.update(errorCode=ready.code, reason=ready.message)
        return {'status': 'ok', 'service': 'ihh-local-intake',
                'capabilities': {'pdfText': True, 'ocr': shutil.which('tesseract') is not None,
                                 'clinicalAnalysis': ready.status == 'ready', 'sending': False},
                'analysis': analysis_info,
                'limits': {'maxBytes': MAX_BYTES, 'maxPages': MAX_PAGES},
                'storage': 'ephemeral-local-session'}

    @app.post('/api/referrals', status_code=202)
    async def upload(request: Request, file: UploadFile = File(...)):
        service = request.app.state.service
        with service.lock:
            if len(service.records) >= MAX_SESSION_PACKETS:
                raise HTTPException(429, 'Session packet limit reached. Restart the local server to clear stored packets.')
        if not service.active_slots.acquire(blocking=False):
            raise HTTPException(429, 'Processing queue is full. Wait for a packet to finish.')
        packet_id = uuid.uuid4().hex
        folder = service.root / packet_id
        folder.mkdir(mode=0o700)
        path = folder / 'packet.pdf'
        accepted = False
        try:
            if not file.filename or not file.filename.lower().endswith('.pdf'):
                raise HTTPException(415, 'Choose a PDF file.')
            size = 0
            digest = hashlib.sha256()
            with path.open('wb') as target:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, 'Upload exceeds 25 MB.')
                    target.write(chunk)
                    digest.update(chunk)
            with path.open('rb') as header:
                signature = header.read(5)
            if not size or signature != b'%PDF-':
                raise HTTPException(422, 'The file is empty or is not a PDF.')
            try:
                with fitz.open(path) as pdf:
                    if pdf.needs_pass:
                        raise HTTPException(422, 'Encrypted PDFs are not supported.')
                    pages = len(pdf)
                    if not 1 <= pages <= MAX_PAGES:
                        raise HTTPException(422, f'Choose a PDF with 1–{MAX_PAGES} pages.')
                    if any(not p.rect.width or not p.rect.height for p in pdf):
                        raise HTTPException(422, 'The PDF contains an invalid page.')
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(422, 'The PDF is corrupt or cannot be parsed.') from None
            with service.lock:
                if len(service.records) >= MAX_SESSION_PACKETS:
                    raise HTTPException(429, 'Session packet limit reached. Restart the local server to clear stored packets.')
                service.register(path, packet_id, pages, digest.hexdigest())
            accepted = True
            return {'referralId': packet_id, 'jobId': packet_id, 'version': 1}
        finally:
            await file.close()
            if not accepted:
                shutil.rmtree(folder, ignore_errors=True)
                service.active_slots.release()

    @app.get('/api/jobs/{job_id}')
    def job(job_id: str, request: Request):
        # `state` is text processing only (text_ready != analysis complete); `analysis` is separate.
        record = request.app.state.service.get(job_id)
        return {**record['job'], 'analysis': record['analysis']}

    @app.get('/api/referrals/{packet_id}')
    def referral(packet_id: str, request: Request):
        return with_actions(request.app.state.service.get(packet_id))

    @app.get('/api/referrals/{packet_id}/search')
    def search(packet_id: str, request: Request, q: str = Query(min_length=2, max_length=120)):
        record = request.app.state.service.get(packet_id)
        matches = []
        for page in record['pages']:
            for hit in re.finditer(re.escape(q), page['text'], re.IGNORECASE):
                if len(matches) == 20:
                    return {'matches': matches, 'truncated': True, 'verified': False}
                matches.append({'page': page['page'], 'snippet': page['text'][max(0, hit.start()-70):hit.end()+100]})
        return {'matches': matches, 'truncated': False, 'verified': False}

    @app.get('/api/referrals/{packet_id}/pages/{page}/image')
    def image(packet_id: str, page: int, request: Request):
        service = request.app.state.service
        record = service.get(packet_id)
        if not 1 <= page <= len(record['pages']) or not record['pages'][page-1]['imageUrl']:
            raise HTTPException(404, 'Page image is not available.')
        return FileResponse(service.root / packet_id / f'page-{page}.png', media_type='image/png')

    @app.patch('/api/referrals/{packet_id}/review')
    def review(packet_id: str, body: ReviewInput, request: Request):
        service = request.app.state.service
        with service.lock:
            record = service.get(packet_id)
            if body.version != record['version']:
                raise HTTPException(409, 'Review changed. Reload the latest version.')
            if record['job']['state'] != 'text_ready':
                raise HTTPException(409, 'Wait for document processing to finish.')
            if not 1 <= body.page <= len(record['pages']):
                raise HTTPException(422, 'Page does not exist in this document.')
            had_outcome = record['outcome'] is not None
            record['reviews'][str(body.page)] = body.model_dump(exclude={'version'})
            record['version'] += 1
            record['outcome'] = None
            service.records[packet_id] = record
            service.mark(packet_id, 'page_note', invalidatedConfirmation=had_outcome)
            return with_actions(record)

    @app.post('/api/referrals/{packet_id}/outcome')
    def outcome(packet_id: str, body: OutcomeInput, request: Request):
        service = request.app.state.service
        with service.lock:
            record = service.get(packet_id)
            current = record['outcome']
            # Exact replay of the request that produced the CURRENT confirmation is idempotent. Anything
            # else at an old version (different content, or any edit since) is stale and rejected.
            if current and body.version == current.get('confirmedFromVersion') \
                    and record['version'] == current.get('confirmedAtVersion') \
                    and (body.decision, body.reviewer, body.rationale, body.attested) == (
                        current['decision'], current['reviewer'], current['rationale'], current['attested']):
                return {**with_actions(record), 'idempotentReplay': True}
            if body.version != record['version']:
                raise HTTPException(409, 'Review changed. Reload before confirming.')
            if body.decision in ('approve', 'deny'):
                raise HTTPException(409, 'Admission decisions are disabled: clinical analysis and complete criteria coverage are unavailable.')
            if record['job']['state'] != 'text_ready' or not record['reviews'] or not body.attested:
                raise HTTPException(409, 'Review a source page and attest before recording the next step.')
            if record['analysis']['status'] in ('queued', 'checking'):
                raise HTTPException(409, 'Analysis is still running. Wait for it to finish before recording the next step.')
            if any(not f['review'].get('reviewed') for f in record['formFields']):
                raise HTTPException(409, 'Review every extracted field before recording the next step.')
            record['outcome'] = {**body.model_dump(exclude={'version'}), 'confirmedFromVersion': body.version,
                                 'confirmedAtVersion': body.version + 1, 'confirmedAt': service.clock()}
            record['version'] += 1
            service.records[packet_id] = record
            service.mark(packet_id, 'confirmation', decision=body.decision)
            return with_actions(record)

    @app.patch('/api/referrals/{packet_id}/fields/{field_id}')
    def field_review(packet_id: str, field_id: str, body: FieldReviewInput, request: Request):
        service = request.app.state.service
        with service.lock:
            record = service.get(packet_id)       # private copy: a rejected edit changes nothing
            change = apply_field_review(record, field_id, body, now=service.clock)
            service.records[packet_id] = record
            service.mark(packet_id, 'field_review', corrected=record_field_corrected(record, field_id),
                         invalidatedConfirmation=change['invalidatedConfirmation'])
            return {**with_actions(record), 'change': change}

    @app.get('/api/referrals/{packet_id}/export')
    def export(packet_id: str, request: Request):
        service = request.app.state.service
        record = service.get(packet_id)
        if not record['outcome']:
            raise HTTPException(409, 'No current confirmed next step. Review and confirm first.')
        service.mark(packet_id, 'export_viewed')
        return build_export(record)

    @app.get('/api/referrals/{packet_id}/timing')
    def timing(packet_id: str, request: Request):
        service = request.app.state.service
        service.get(packet_id)                       # 404 for unknown IDs
        with service.lock:
            return compute_timing(list(service.timelines.get(packet_id, [])), service.clock())

    @app.post('/api/referrals/{packet_id}/timing')
    def timing_event(packet_id: str, body: TimingInput, request: Request):
        service = request.app.state.service
        with service.lock:
            service.get(packet_id)
            open_now = open_intervals(service.timelines.get(packet_id, []))
            name = 'pause' if body.event in ('pause', 'resume') else 'wait'
            starting = body.event in ('pause', 'wait_start')
            if starting == open_now[name]:
                raise HTTPException(409, f'A {name} interval is already {"open" if starting else "closed"}.')
            service.mark(packet_id, body.event, **({'reason': body.reason} if body.reason else {}))
            return compute_timing(list(service.timelines[packet_id]), service.clock())

    @app.get('/api/timing/summary')
    def timing_summary(request: Request):
        service = request.app.state.service
        with service.lock:
            return summarize({pid: list(ev) for pid, ev in service.timelines.items()}, service.clock())

    @app.get('/api/referrals/{packet_id}/draft')
    def draft(packet_id: str, request: Request):
        record = request.app.state.service.get(packet_id)
        if not record['outcome']:
            raise HTTPException(409, 'No current confirmed next step. Review and confirm first.')
        out = record['outcome']
        return {'version': record['version'], 'sent': False,
                'text': f"UNSENT LOCAL DRAFT\nNext step: {out['decision']}\nReviewer: {out['reviewer']}\n\n{out['rationale']}"
                        + ''.join('\n' + line for line in draft_sections(record))
                        + "\n\nClinical eligibility and authorization have not been established."}

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'frontend/index.html')

    allowed_assets = {name: ROOT / 'frontend' / name for name in (
        'assets/source-sans-3-latin.woff2', 'assets/source-sans-3-LICENSE.txt',
        'index.html', 'app.js', 'styles.css', 'model.js', 'backend-client.js', 'referral-flow.js','referral-flow-model.js','onboarding.js','field-review-model.js', 'field-review.js',
        'team/index.html', 'team/board.js', 'team/tasks.json')}
    allowed_assets.update({
        'challenges/1-referral-intake/criteria/admission-criteria.md': ROOT / 'challenges/1-referral-intake/criteria/admission-criteria.md',
        'docs/frontend-research-and-handoff.md': ROOT / 'docs/frontend-research-and-handoff.md',
    })

    @app.get('/{asset:path}')
    def asset(asset: str):
        asset = 'team/index.html' if asset == 'team/' else asset
        if asset not in allowed_assets:
            raise HTTPException(404, 'Not found.')
        return FileResponse(allowed_assets[asset])

    return app


app = create_app()
