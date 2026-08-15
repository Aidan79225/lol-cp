"""Application 層的 port 定義。infrastructure 實作這些 Protocol。

依賴方向：infrastructure → application。application 不認識任何實作。
"""

from __future__ import annotations

from typing import Protocol

from lolcp.domain.entities import Champion, Item


class ItemRepository(Protocol):
    def all_items(self) -> tuple[Item, ...]: ...


class ChampionRepository(Protocol):
    def all_champions(self) -> tuple[Champion, ...]: ...

    def by_key(self, key: str) -> Champion | None: ...
