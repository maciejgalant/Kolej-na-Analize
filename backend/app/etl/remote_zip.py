"""Czytanie pojedynczych plików z archiwum ZIP na serwerze HTTP bez pobierania całości.

Paczka BDOT10k dla Warszawy ma ok. 90 MB, a potrzebne są z niej dwa pliki (ok. 10 MB
po kompresji). Serwer GUGiK obsługuje nagłówek Range, więc `zipfile` może czytać
archiwum przez ten obiekt jak zwykły plik.
"""

import io
import time
import zipfile

import httpx

RETRY_DELAYS_S = (2.0, 6.0, 15.0)


class RemoteFileUnavailable(RuntimeError):
    """Serwer z danymi nie odpowiada mimo ponowień."""


class HttpRangeFile(io.RawIOBase):
    def __init__(
        self, client: httpx.Client, url: str, retry_delays_s: tuple[float, ...] = RETRY_DELAYS_S
    ) -> None:
        self._client = client
        self._url = url
        self._pos = 0
        self._retry_delays_s = retry_delays_s
        self.requests_made = 0
        head = self._request("HEAD")
        if head.headers.get("accept-ranges", "").lower() != "bytes":
            raise RuntimeError(f"Serwer nie obsługuje pobierania zakresów: {url}")
        self.size = int(head.headers["content-length"])
        self.last_modified = head.headers.get("last-modified")

    def _request(self, method: str, headers: dict[str, str] | None = None) -> httpx.Response:
        """Zapytanie z ponowieniami przy błędach sieci i odpowiedziach 5xx/429."""
        last_error: Exception | None = None
        for delay in (0.0, *self._retry_delays_s):
            if delay:
                time.sleep(delay)
            self.requests_made += 1
            try:
                response = self._client.request(
                    method, self._url, headers=headers, follow_redirects=True
                )
                if response.status_code < 500 and response.status_code != 429:
                    response.raise_for_status()
                    return response
                last_error = RuntimeError(f"HTTP {response.status_code}")
            except httpx.TransportError as error:
                last_error = error
        raise RemoteFileUnavailable(
            f"Serwer nie odpowiada ({self._url}): {last_error}. Spróbuj ponownie za kilka minut."
        ) from last_error

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self.size}[whence]
        self._pos = max(0, base + offset)
        return self._pos

    def readinto(self, buffer) -> int:
        if self._pos >= self.size or len(buffer) == 0:
            return 0
        end = min(self.size, self._pos + len(buffer)) - 1
        response = self._request("GET", {"Range": f"bytes={self._pos}-{end}"})
        if response.status_code != 206:
            raise RuntimeError(
                f"Oczekiwano odpowiedzi 206 dla zakresu, jest {response.status_code}"
            )
        data = response.content
        buffer[: len(data)] = data
        self._pos += len(data)
        return len(data)


def open_remote_zip(
    client: httpx.Client,
    url: str,
    buffer_size: int = 2 * 1024 * 1024,
    retry_delays_s: tuple[float, ...] = RETRY_DELAYS_S,
) -> tuple[zipfile.ZipFile, HttpRangeFile]:
    raw = HttpRangeFile(client, url, retry_delays_s)
    return zipfile.ZipFile(io.BufferedReader(raw, buffer_size=buffer_size)), raw
