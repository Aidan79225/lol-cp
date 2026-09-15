"""Application 層的 port 定義。infrastructure 實作這些 Protocol。

依賴方向：infrastructure → application。application 不認識任何實作。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from lolcp.domain.entities import Champion, Item
from lolcp.domain.spells import ChampionSpells
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import ChampionOverrides


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


class ChampionSpellsRepository(Protocol):
    def spells_for(self, key: str) -> ChampionSpells | None: ...


class PatchGateway(Protocol):
    def latest_version(self) -> str: ...

    def download_patch(
        self,
        version: str,
        dest: Path,
        on_progress: Callable[[int, int], None] | None = None,
        champion_keys: Sequence[str] = (),
    ) -> None: ...

    def download_champion_bins(
        self,
        version: str,
        keys: Sequence[str],
        dest: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None: ...


class CacheStore(Protocol):
    def is_complete(self, version: str) -> bool: ...

    def latest_complete(self) -> str | None: ...

    def open_staging(self, version: str) -> Path: ...

    def commit(self, version: str, staging: Path) -> Path: ...

    def discard(self, staging: Path) -> None: ...

    def dir_for(self, version: str) -> Path: ...

    def missing_champion_bins(self, version: str, keys: Sequence[str]) -> tuple[str, ...]: ...


class OverridesStore(Protocol):
    def load(self) -> ChampionOverrides: ...

    def set_weight(
        self, champion_key: str, stat: StatKey, value: float | None
    ) -> None: ...
