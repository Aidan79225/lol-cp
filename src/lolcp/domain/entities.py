"""領域實體。皆為不可變值物件。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from lolcp.domain.stats import StatKey, StatLine

MANA_PARTYPE = "Mana"


@dataclass(frozen=True)
class Item:
    """一件裝備。stats 內的 amount 一律已正規化（見 stats.NORMALIZE_X100）。"""

    item_id: int
    name: str
    total_gold: int
    sell_gold: int
    stats: tuple[StatLine, ...]
    tags: tuple[str, ...]
    icon: str
    recipe: tuple[int, ...]

    def amount_of(self, stat: StatKey) -> float | None:
        """回傳屬性數量；沒有這條屬性回 None。

        None 與 0.0 是不同的事，呼叫端必須區分。
        """
        for line in self.stats:
            if line.stat is stat:
                return line.amount
        return None

    @cached_property
    def stat_keys(self) -> frozenset[StatKey]:
        return frozenset(line.stat for line in self.stats)


@dataclass(frozen=True)
class Champion:
    """一隻英雄。partype 與 tags 一律取自 en_US（在地化字串不可用於邏輯判斷）。"""

    key: str
    numeric_id: int
    name: str          # 顯示用，取自 zh_TW
    tags: tuple[str, ...]
    partype: str       # en_US，例如 "Mana" / "Flow" / "None"

    @property
    def uses_mana(self) -> bool:
        return self.partype == MANA_PARTYPE

    @property
    def partype_unknown(self) -> bool:
        """partype 為空字串。視為未知，不可推論為無法力。"""
        return self.partype == ""
