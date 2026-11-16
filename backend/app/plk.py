"""Read-only PLK client. One shared cache/budget per backend process; no disk history."""

from collections import OrderedDict, deque
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from time import monotonic

import httpx

BASE_URL = "https://pdp-api.plk-sa.pl/api/v1/"
ALLOWED = {
    "dictionaries/stations": "stations",
    "operations": "trains",
    "disruptions": "disruptions",
    "schedules": "routes",
}


class PlkError(Exception):
    def __init__(self, code: str, message: str, status: int = 503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class PlkClient:
    def __init__(self, key: str, transport=None, clock=monotonic):
        self._key = key
        self._transport = transport
        self._clock = clock
        self._lock = Lock()
        self._cache = OrderedDict()
        self._requests = deque()
        self._blocked_until = 0.0

    def fetch(self, endpoint: str, params: dict) -> dict:
        if endpoint not in ALLOWED:
            raise ValueError("Unsupported PLK endpoint")
        if not self._key:
            raise PlkError("not_configured", "Nie skonfigurowano klucza API PKP PLK.")
        identity = (endpoint, tuple(sorted(params.items())))
        ttl = 86400 if endpoint == "dictionaries/stations" else 300
        # Coalesce simultaneous requests, including clicks from multiple browser tabs.
        with self._lock:
            now = self._clock()
            entry = self._cache.get(identity)
            if entry and now - entry[0] < ttl:
                result = deepcopy(entry[1])
                result["cached"] = True
                return result
            if now < self._blocked_until:
                raise PlkError("cooldown", "API PKP PLK wymaga przerwy. Spróbuj później.")
            while self._requests and now - self._requests[0] >= 86400:
                self._requests.popleft()
            if len(self._requests) >= 900 or sum(now - t < 3600 for t in self._requests) >= 90:
                raise PlkError("local_limit", "Wykorzystano lokalny limit zapytań PKP PLK.")
            self._requests.append(now)
            try:
                with httpx.Client(timeout=15, transport=self._transport) as client:
                    response = client.get(
                        BASE_URL + endpoint,
                        params=params,
                        headers={"X-API-Key": self._key, "Accept": "application/json"},
                    )
                if response.status_code in (401, 403):
                    self._blocked_until = now + 60
                    raise PlkError("unauthorized", "PKP PLK odrzuciło klucz lub uprawnienia.")
                if response.status_code == 429:
                    delay = response.headers.get("Retry-After", "300")
                    seconds = int(delay) if delay.isdigit() else 300
                    self._blocked_until = now + max(300, seconds)
                    raise PlkError("rate_limited", "Osiągnięto limit zapytań PKP PLK.")
                response.raise_for_status()
                payload = response.json()
                field = ALLOWED[endpoint]
                if not isinstance(payload, dict) or not isinstance(
                    payload.get(field), list | type(None)
                ):
                    raise ValueError("Unexpected response")
                if field not in payload:
                    raise ValueError("Missing collection")
            except (httpx.HTTPError, ValueError):
                # Never forward upstream exceptions, headers, or bodies containing secrets.
                self._blocked_until = now + 30
                raise PlkError("unavailable", "Nie udało się pobrać danych PKP PLK.") from None
            result = {
                "source": "PKP Polskie Linie Kolejowe S.A. — Otwarte Dane Kolejowe",
                "fetched_at": datetime.now(UTC).isoformat(),
                "cached": False,
                "cache_seconds": ttl,
                "data": payload,
            }
            self._cache[identity] = (self._clock(), result)
            self._cache.move_to_end(identity)
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
            return deepcopy(result)
