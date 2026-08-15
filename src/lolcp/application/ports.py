"""Application 層的 port 定義。infrastructure 實作這些 Protocol。

依賴方向：infrastructure → application。application 不認識任何實作。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from lolcp.domain.entities import Champion, Item


class ItemRepository(Protocol):
    def all_items(self) -> tuple[Item, ...]: ...


class ChampionRepository(Protocol):
    def all_champions(self) -> tuple[Champion, ...]: ...

    def by_key(self, key: str) -> Champion | None: ...


class NetworkUnavailableError(RuntimeError):
    """網路不可用或伺服器回應失敗。呼叫端應降級為讀取舊快取。

    定義在 application 而非 infrastructure：這是 PatchGateway 契約的一部分，
    SyncGameData 必須 catch 它才能降級。放在 infrastructure 會迫使
    application 為了一個例外型別而 import 外層。
    """


class PatchGateway(Protocol):
    def latest_version(self) -> str: ...

    def download_patch(
        self,
        version: str,
        dest: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None: ...
