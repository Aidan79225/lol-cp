"""啟動時的版本檢查與下載。

流程（見 spec §6.2）：
  1. 取得最新版本號（2 KB，短超時）
     失敗 → 用本地最新完整版本，標示離線
  2. 已有該版本的完整快取 → 直接用（瞬開）
     否則 → 背景下載到 staging，成功才原子提交
     下載失敗 → 退回本地最新完整版本，標示離線
  3. 無任何本地完整版本且網路失敗 → NoDataAvailableError

本模組不得 import Qt，也不得 import infrastructure。進度以普通 Callable
回傳，快取以 CacheStore Protocol 注入。兩條皆有測試守著。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from lolcp.application.ports import CacheStore, NetworkUnavailableError, PatchGateway

ProgressCallback = Callable[[int, int], None]


class NoDataAvailableError(RuntimeError):
    """網路不可用且本地沒有任何完整快取。"""


@dataclass(frozen=True)
class SyncResult:
    version: str
    offline: bool
    downloaded: bool


class SyncGameData:
    def __init__(self, gateway: PatchGateway, cache: CacheStore) -> None:
        self._gateway = gateway
        self._cache = cache

    def execute(self, on_progress: ProgressCallback | None = None) -> SyncResult:
        try:
            latest = self._gateway.latest_version()
        except NetworkUnavailableError:
            return self._offline_fallback()

        if self._cache.is_complete(latest):
            return SyncResult(version=latest, offline=False, downloaded=False)

        staging = self._cache.open_staging(latest)
        try:
            self._gateway.download_patch(latest, staging, on_progress)
        except NetworkUnavailableError:
            self._cache.discard(staging)
            return self._offline_fallback()

        self._cache.commit(latest, staging)
        return SyncResult(version=latest, offline=False, downloaded=True)

    def _offline_fallback(self) -> SyncResult:
        local = self._cache.latest_complete()
        if local is None:
            raise NoDataAvailableError(
                "無法連線且本地沒有任何完整快取。請連上網路後重試。"
            )
        return SyncResult(version=local, offline=True, downloaded=False)
