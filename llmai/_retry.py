"""
Retry/backoff helper used by the optional cloud-connected layers.

Importable from anywhere — no logger config side-effects, no init order
constraints. The caller controls which exceptions trigger a retry.
"""
from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    *,
    attempts: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 5.0,
    backoff: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    label: str = "",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorate a callable so transient failures are retried with backoff.

    The default catches every Exception; pass ``retry_on=(httpx.ConnectError,
    httpx.ReadTimeout)`` to limit. ``label`` is just for log readability.
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exc: BaseException | None = None
            for n in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except retry_on as exc:
                    last_exc = exc
                    if n >= attempts:
                        break
                    logger.warning(
                        "%s attempt %d/%d failed: %s — retrying in %.1fs",
                        label or fn.__name__, n, attempts, exc, delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff, max_delay)
            assert last_exc is not None  # for type checkers
            raise last_exc
        return wrapper
    return decorator
