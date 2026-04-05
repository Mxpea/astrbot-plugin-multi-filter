import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class RequestTrace:
    trace_id: str
    method: str
    path: str
    started_at: float

    @classmethod
    def create(cls, method: str, path: str) -> "RequestTrace":
        return cls(trace_id=new_trace_id(), method=method, path=path, started_at=time.perf_counter())

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started_at) * 1000)


def log_request_start(logger: Any, trace: RequestTrace, extra: Dict[str, Any] | None = None):
    payload = dict(extra or {})
    logger.info(
        "[multi_filter][web][%s] request start method=%s path=%s extra=%s",
        trace.trace_id,
        trace.method,
        trace.path,
        payload,
    )


def log_request_end(logger: Any, trace: RequestTrace, status: int, ok: bool):
    logger.info(
        "[multi_filter][web][%s] request end method=%s path=%s status=%s ok=%s cost_ms=%s",
        trace.trace_id,
        trace.method,
        trace.path,
        status,
        ok,
        trace.elapsed_ms(),
    )
