"""屬性單價的推導。

本任務只建立錨定型別；PriceTable 與兩種定價法在 Task 7、8 補上。

錨定型別放在 domain 是因為「哪件裝備錨定哪種屬性」是業務規則，
CanonicalDeriver（domain）必須以它為參數型別。只有從 toml 讀取
才是 infrastructure 的事。
"""

from __future__ import annotations

from dataclasses import dataclass

from lolcp.domain.stats import StatKey


@dataclass(frozen=True)
class AnchorEntry:
    """一種屬性的錨定基礎裝備。

    item_id 一律為數值 ID。以名稱查找會拿到其他模式的變體
    （長劍 1036 是 350g，771036 是 400g），單價全錯且不報錯。
    """

    stat: StatKey
    item_id: int
    reason: str


@dataclass(frozen=True)
class AnchorConfig:
    entries: tuple[AnchorEntry, ...]

    @property
    def stats(self) -> frozenset[StatKey]:
        return frozenset(e.stat for e in self.entries)

    def for_stat(self, stat: StatKey) -> AnchorEntry | None:
        for entry in self.entries:
            if entry.stat is stat:
                return entry
        return None
