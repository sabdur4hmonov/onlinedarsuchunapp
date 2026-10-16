import asyncio
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Simple in-memory limiter: at most `max_attempts` hits per key within `window_seconds`.

    NOTE: memory is per process. If the server is later run with several workers
    or on several machines, move this to Redis so all of them share the counters.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, *keys: str) -> bool:
        """Registers one attempt for every key. Returns False if any key is over the limit."""
        now = time.monotonic()
        async with self._lock:
            allowed = True
            for key in keys:
                hits = self._hits[key]
                while hits and now - hits[0] > self.window_seconds:
                    hits.popleft()
                if len(hits) >= self.max_attempts:
                    allowed = False
                else:
                    hits.append(now)
            return allowed

    def reset(self) -> None:
        self._hits.clear()
