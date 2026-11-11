"""Czytanie pojedynczych plików z archiwum ZIP na serwerze HTTP bez pobierania całości.

Paczka BDOT10k dla Warszawy ma ok. 90 MB, a potrzebne są z niej dwa pliki (ok. 10 MB
po kompresji). Serwer GUGiK obsługuje nagłówek Range, więc `zipfile` może czytać
archiwum przez ten obiekt jak zwykły plik.
"""

import io
import zipfile

import httpx


class HttpRangeFile(io.RawIOBase):
    def __init__(self, client: httpx.Client, url: str) -> None:
        self._client = client
        self._url = url
        self._pos = 0
        head = client.head(url, follow_redirects=True)
        head.raise_for_status()
        if head.headers.get("accept-ranges", "").lower() != "bytes":
            raise RuntimeError(f"Serwer nie obsługuje pobierania zakresów: {url}")
        self.size = int(head.headers["content-length"])
        self.last_modified = head.headers.get("last-modified")
        self.requests_made = 1

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
        response = self._client.get(
            self._url, headers={"Range": f"bytes={self._pos}-{end}"}, follow_redirects=True
        )
        if response.status_code != 206:
            raise RuntimeError(
                f"Oczekiwano odpowiedzi 206 dla zakresu, jest {response.status_code}"
            )
        self.requests_made += 1
        data = response.content
        buffer[: len(data)] = data
        self._pos += len(data)
        return len(data)


def open_remote_zip(
    client: httpx.Client, url: str, buffer_size: int = 2 * 1024 * 1024
) -> tuple[zipfile.ZipFile, HttpRangeFile]:
    raw = HttpRangeFile(client, url)
    return zipfile.ZipFile(io.BufferedReader(raw, buffer_size=buffer_size)), raw
