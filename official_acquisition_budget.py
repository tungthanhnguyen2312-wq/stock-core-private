"""Synchronous shared resource bounds for the existing public official transports.

Limits are operational protection, never source qualification. Rejected payloads
are counted but never returned to immutable retention. One extra probe byte may
be downloaded to distinguish an exact boundary from a truncated response.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import time
import hashlib
from typing import Callable
from urllib.request import HTTPRedirectHandler, build_opener


class _NoAutomaticRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("OFFICIAL_ROUTE_REDIRECT_NOT_ADMITTED")


class AcquisitionBudgetExceeded(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class AcquisitionLimits:
    max_requests: int = 64
    max_total_bytes: int = 32 * 1024 * 1024
    max_response_bytes: int = 8 * 1024 * 1024
    max_seconds: float = 180
    request_timeout_seconds: float = 30
    max_pages_per_surface: int = 16

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < float('inf'):
                raise ValueError(f'INVALID_ACQUISITION_LIMIT:{name}')
        for name in ('max_requests', 'max_total_bytes', 'max_response_bytes', 'max_pages_per_surface'):
            if not isinstance(getattr(self, name), int):
                raise ValueError(f'INVALID_ACQUISITION_LIMIT:{name}')


class AcquisitionBudget:
    def __init__(self, limits: AcquisitionLimits | None = None, *, clock: Callable = time.monotonic):
        self.limits = limits or AcquisitionLimits()
        self.clock = clock
        self.started = clock()
        self.requests = []
        self.downloaded_bytes = 0
        self.reason = None
        self.termination = None

    def elapsed(self):
        return max(0.0, self.clock() - self.started)

    def fail(self, reason):
        self.reason = self.reason or reason
        raise AcquisitionBudgetExceeded(self.reason)

    def check_time(self):
        if self.reason:
            raise AcquisitionBudgetExceeded(self.reason)
        if self.elapsed() >= self.limits.max_seconds:
            self.fail('WALL_CLOCK_BUDGET_EXHAUSTED')

    def check_page(self, page, *, surface=None):
        self.check_time()
        if page is not None and page > self.limits.max_pages_per_surface:
            self.termination = {'surface': surface, 'page': page}
            self.fail('PAGE_BUDGET_EXHAUSTED')

    def timeout(self):
        self.check_time()
        return min(self.limits.request_timeout_seconds, self.limits.max_seconds - self.elapsed())

    def _account(self, receipt, count):
        receipt['response_bytes'] += count
        self.downloaded_bytes += count
        receipt['cumulative_bytes'] = self.downloaded_bytes
        if receipt['response_bytes'] > self.limits.max_response_bytes:
            self.fail('RESPONSE_BYTE_LIMIT_EXCEEDED')
        if self.downloaded_bytes > self.limits.max_total_bytes:
            self.fail('TOTAL_BYTE_BUDGET_EXHAUSTED')

    def open(self, request):
        # Redirects are additional HTTP requests and route changes, never hidden budget use.
        return build_opener(_NoAutomaticRedirect()).open(request, timeout=self.timeout())

    def read(self, response):
        receipt = self.requests[-1]
        receipt['transport_accounted'] = True
        chunks = []
        while True:
            self.check_time()
            remaining = min(self.limits.max_response_bytes - receipt['response_bytes'],
                            self.limits.max_total_bytes - self.downloaded_bytes)
            # A bounded read and a one-byte overflow probe; never response.read() unbounded.
            reader = getattr(response, 'read1', response.read)
            chunk = reader(min(65536, remaining + 1))
            self._account(receipt, len(chunk))
            self.check_time()
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)

    def request(self, fetcher, url, *, surface, page=None, **kwargs):
        self.termination = dict(surface=surface, requested_url=url, page=page)
        self.check_page(page, surface=surface)
        if len(self.requests) >= self.limits.max_requests:
            self.fail('REQUEST_BUDGET_EXHAUSTED')
        if self.downloaded_bytes >= self.limits.max_total_bytes:
            self.fail('TOTAL_BYTE_BUDGET_EXHAUSTED')
        receipt = dict(request_number=len(self.requests)+1, surface=surface, requested_url=url,
                       page=page, response_bytes=0, cumulative_bytes=self.downloaded_bytes,
                       elapsed_seconds=round(self.elapsed(), 6), status='STARTED')
        self.requests.append(receipt)
        try:
            if getattr(fetcher, 'bounded_transport', False):
                response = fetcher(url, _budget=self, **kwargs)
            else:
                # Offline injected fetchers still share accounting before retention.
                response = fetcher(url, **kwargs)
            if not receipt.get('transport_accounted'):
                self._account(receipt, len(response['data']))
            self.check_time()
            receipt['response_sha256'] = hashlib.sha256(response['data']).hexdigest()
            receipt['status'] = 'RETURNED' if response.get('http_status') == 200 else 'SOURCE_FAILURE'
            return response
        except Exception as exc:
            receipt['status'] = 'BUDGET_TERMINATED' if isinstance(exc, AcquisitionBudgetExceeded) else 'FETCH_EXCEPTION'
            raise
        finally:
            receipt.pop('transport_accounted', None)
            receipt['elapsed_seconds'] = round(self.elapsed(), 6)

    def report(self):
        return dict(contract_version='official_acquisition_budget/v1', limits=asdict(self.limits),
                    request_count=len(self.requests), downloaded_bytes=self.downloaded_bytes,
                    elapsed_seconds=round(self.elapsed(), 6), terminal_state='EXHAUSTED' if self.reason else 'WITHIN_LIMITS',
                    reason=self.reason, termination=self.termination if self.reason else None, requests=[dict(row) for row in self.requests])
