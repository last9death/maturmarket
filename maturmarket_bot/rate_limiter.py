from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta


class SlidingWindowRateLimiter:
    def __init__(self, max_events: int, window_seconds: int) -> None:
        self.max_events = max_events
        self.window = timedelta(seconds=window_seconds)
        self.events: deque[datetime] = deque()

    def allow(self) -> bool:
        now = datetime.utcnow()
        while self.events and now - self.events[0] > self.window:
            self.events.popleft()
        if len(self.events) >= self.max_events:
            return False
        self.events.append(now)
        return True
