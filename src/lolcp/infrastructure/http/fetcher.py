"""最小的 HTTP 取用層。只用標準庫，不引入 requests。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from lolcp.application.ports import NetworkUnavailableError

CHUNK_SIZE = 256 * 1024

# raw.communitydragon.org 對 urllib 的預設 User-Agent（Python-urllib/3.x）
# 回 403。實測發現於 Task 3 的 fixture 腳本，兩處都必須送這個標頭。
USER_AGENT = "lol-cp (https://github.com/local/lol-cp)"


class HttpFetcher:
    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout

    def _request(self, url: str) -> urllib.request.Request:
        return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    def get_json(self, url: str):
        try:
            with urllib.request.urlopen(self._request(url), timeout=self._timeout) as response:
                return json.load(response)
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise NetworkUnavailableError(f"取得 {url} 失敗：{exc}") from exc

    def download(
        self,
        url: str,
        dest: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """串流下載到 dest。on_progress(已下載, 總計) —— 總計未知時為 0。"""
        try:
            with urllib.request.urlopen(self._request(url), timeout=self._timeout) as response:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                with dest.open("wb") as fh:
                    while chunk := response.read(CHUNK_SIZE):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if on_progress:
                            on_progress(downloaded, total)
        except (urllib.error.URLError, OSError) as exc:
            dest.unlink(missing_ok=True)
            raise NetworkUnavailableError(f"下載 {url} 失敗：{exc}") from exc
