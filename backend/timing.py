"""BE-06: review timing derived from an in-memory event log. No clinical content is stored here.

Events are `{at, kind, version, ...}` with only non-content extras (decision label, booleans, status
code). Durations are computed from those timestamps; anything that cannot be known is `None`, never 0.

Definitions (also in docs/backend-tickets/BE-06-measurement.md):
* elapsed: received -> the current confirmed next step. `None` until one exists.
* paused / waiting: explicit pause/resume and wait_start/wait_end intervals reported by the reviewer.
* active: first review event -> confirmed next step, minus the union of paused and waiting intervals.
  This is a timestamp estimate, not a stopwatch of attention. `None` if any interval is still open,
  events are out of order, or there is no review/confirmation.
* A clarification or clinical-review confirmation is an INTERMEDIATE state, never a completed
  admission disposition. This prototype cannot approve or deny.
* No savings percentage is computed. The 120-minute baseline is user-reported and unmeasured.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

INTERVAL_EVENTS = {'pause': ('pause', 'resume'), 'wait': ('wait_start', 'wait_end')}
BASELINE = {'reportedMinutes': 120, 'measured': False,
            'note': 'User-reported, not measured. 90/60/30 minutes are targets for 25/50/75% less time, not results.'}


class TimingInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event: Literal['pause', 'resume', 'wait_start', 'wait_end']
    reason: Literal['coordinator-break', 'hospital', 'authorization', 'other'] | None = None


def _t(event: dict) -> datetime:
    return datetime.fromisoformat(event['at'])


def open_intervals(events: list[dict]) -> dict[str, bool]:
    state = {'pause': False, 'wait': False}
    for e in events:
        for name, (start, end) in INTERVAL_EVENTS.items():
            if e['kind'] == start:
                state[name] = True
            elif e['kind'] == end:
                state[name] = False
    return state


def _merge(intervals: list[tuple[datetime, datetime]]) -> float:
    total, current = 0.0, None
    for start, end in sorted(intervals):
        if current and start <= current[1]:
            current = (current[0], max(current[1], end))
        else:
            if current:
                total += (current[1] - current[0]).total_seconds()
            current = (start, end)
    if current:
        total += (current[1] - current[0]).total_seconds()
    return total


def _seconds(a: datetime | None, b: datetime | None) -> float | None:
    return None if a is None or b is None else (b - a).total_seconds()


def compute(events: list[dict], now: str) -> dict[str, Any]:
    anomalies: list[str] = []
    try:
        times = [_t(e) for e in events]
    except (ValueError, KeyError):
        times, anomalies = [], ['unparseable_timestamp']
    if times and any(b < a for a, b in zip(times, times[1:])):
        anomalies.append('out_of_order_events')
    usable = not anomalies

    first = lambda *kinds: next((e for e in events if e['kind'] in kinds), None)
    received, text_ready = first('received'), first('text_ready')
    text_failed, first_review = first('text_failed'), first('page_note', 'field_review', 'confirmation')
    current = None
    for e in events:                     # the confirmation that is still in force
        if e['kind'] == 'confirmation':
            current = e
        elif e['kind'] in ('page_note', 'field_review') and e.get('invalidatedConfirmation'):
            current = None
    at = lambda e: _t(e) if e is not None and usable else None

    open_state = open_intervals(events)
    paused = waiting = active = None
    reason = None
    start, end = at(first_review), at(current)
    if current is None:
        reason = 'No current confirmed next step.'
    elif not usable:
        reason = 'Event timestamps are unusable.'
    elif any(open_state.values()):
        reason = 'A pause or wait interval is still open.'
    elif start is None or end < start:
        reason = 'No review event before the confirmation.'
    else:
        spans = {'pause': [], 'wait': []}
        opened: dict[str, datetime | None] = {'pause': None, 'wait': None}
        for e, t in zip(events, times):
            for name, (s, f) in INTERVAL_EVENTS.items():
                if e['kind'] == s:
                    opened[name] = t
                elif e['kind'] == f and opened[name] is not None:
                    lo, hi = max(opened[name], start), min(t, end)
                    if hi > lo:
                        spans[name].append((lo, hi))
                    opened[name] = None
        paused, waiting = _merge(spans['pause']), _merge(spans['wait'])
        active = (end - start).total_seconds() - _merge(spans['pause'] + spans['wait'])

    if text_failed and not current:
        status = 'text-failed'
    elif current:
        status = 'confirmed-intermediate'
    else:
        status = 'unfinished'
    count = lambda kind: sum(e['kind'] == kind for e in events)
    return {
        'status': status,
        'receivedAt': received and received['at'], 'textReadyAt': text_ready and text_ready['at'],
        'firstReviewAt': first_review and first_review['at'], 'confirmedAt': current and current['at'],
        'processingSeconds': _seconds(at(received), at(text_ready)),
        'elapsedSeconds': _seconds(at(received), at(current)),
        'elapsedSoFarSeconds': None if current or not usable else _seconds(at(received), datetime.fromisoformat(now)),
        'pausedSeconds': paused, 'waitingSeconds': waiting, 'activeSeconds': active,
        'activeUnknownReason': reason if active is None else None,
        'openIntervals': [k for k, v in open_state.items() if v],
        'counts': {'pageNotes': count('page_note'), 'fieldReviews': count('field_review'),
                   'corrections': sum(e['kind'] == 'field_review' and bool(e.get('corrected')) for e in events),
                   'confirmations': count('confirmation'),
                   'invalidatedConfirmations': sum(bool(e.get('invalidatedConfirmation')) for e in events)},
        'disposition': {'kind': 'intermediate', 'decision': current.get('decision'), 'complete': False} if current else None,
        'anomalies': anomalies,
        'definitions': 'active = first review to current confirmation minus explicit pauses and waits (timestamp estimate); '
                       'unknown values are null, never 0; a clarification is not a completed disposition.',
    }


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {'n': 0, 'median': None, 'min': None, 'max': None}
    return {'n': len(values), 'median': statistics.median(values), 'min': min(values), 'max': max(values)}


def summarize(all_events: dict[str, list[dict]], now: str) -> dict[str, Any]:
    rows = {pid: compute(ev, now) for pid, ev in all_events.items()}
    by_status = lambda s: sum(r['status'] == s for r in rows.values())
    known = lambda key: [r[key] for r in rows.values() if r[key] is not None]
    return {
        'packets': len(rows), 'confirmedIntermediate': by_status('confirmed-intermediate'),
        'unfinished': by_status('unfinished'), 'textFailed': by_status('text-failed'),
        'completedAdmissionDispositions': 0,
        'activeSeconds': {**_stats(known('activeSeconds')), 'unknown': sum(r['activeSeconds'] is None for r in rows.values())},
        'elapsedSeconds': {**_stats(known('elapsedSeconds')), 'unknown': sum(r['elapsedSeconds'] is None for r in rows.values())},
        'baseline': BASELINE, 'savingsPercent': None,
        'note': 'Failed and unfinished packets are counted, not dropped. Statistics cover only packets with a known value; '
                'the unknown count is shown. No time saving is inferred: that needs manual and assisted work of equivalent scope, '
                'with sample size and quality checks. Session data only, lost on restart.',
    }
