"""屬性單價的推導。

兩種定價法並列呈現，因為它們的分歧本身就是分析入口：
差異大的裝備，要嘛被動價值高，要嘛屬性被權威法低估。

PriceTable 的 None 與 0.0 是不同的事：
  None = 未定價（無錨可推 / 未進入求解矩陣）
  0.0  = 定價為零（NNLS 解出來就是零）
混在一起就無法判斷 CP值 低是資料限制還是屬性真的不值錢。

錨定型別（AnchorEntry / AnchorConfig）放在 domain 是因為
「哪件裝備錨定哪種屬性」是業務規則；只有從 toml 讀取才是 infrastructure。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Item
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


class AnchorItemMissingError(RuntimeError):
    """錨定裝備不存在或無法用於定價。刻意不降級 —— 必須大聲失敗。"""


@dataclass(frozen=True)
class PriceTable:
    prices: Mapping[StatKey, float | None]
    low_confidence: frozenset[StatKey]

    def unit_price(self, stat: StatKey) -> float | None:
        return self.prices.get(stat)

    def is_priced(self, stat: StatKey) -> bool:
        return self.prices.get(stat) is not None

    @property
    def priced_stats(self) -> frozenset[StatKey]:
        return frozenset(s for s, p in self.prices.items() if p is not None)

    def unpriced_stats(self, present: Iterable[StatKey]) -> frozenset[StatKey]:
        return frozenset(s for s in present if not self.is_priced(s))


class PriceDeriver(Protocol):
    def derive(self, items: Sequence[Item]) -> PriceTable: ...


class CanonicalDeriver:
    """由指定的錨定基礎裝備反推單價。

    錨定裝備一律以數值 ID 查找。以名稱查找會拿到其他模式的變體
    （長劍 1036 是 350g，771036 是 400g），單價全錯且不會報錯。
    """

    def __init__(self, anchors: AnchorConfig, diagnostics: Diagnostics) -> None:
        self._anchors = anchors
        self._diagnostics = diagnostics

    def derive(self, items: Sequence[Item]) -> PriceTable:
        by_id = {i.item_id: i for i in items}
        prices: dict[StatKey, float | None] = {stat: None for stat in StatKey}
        for entry in self._anchors.entries:
            prices[entry.stat] = self._price_from_anchor(entry, by_id)
        return PriceTable(prices=prices, low_confidence=frozenset())

    def _price_from_anchor(self, entry: AnchorEntry, by_id: dict[int, Item]) -> float:
        anchor = by_id.get(entry.item_id)
        if anchor is None:
            raise AnchorItemMissingError(
                f"錨定裝備 {entry.item_id} 不存在於當前版本"
                f"（{entry.stat.config_key}）。Riot 可能已移除該裝備，需更新 anchors.toml。"
            )
        amount = anchor.amount_of(entry.stat)
        if amount is None:
            raise AnchorItemMissingError(
                f"錨定裝備 {entry.item_id}（{anchor.name}）沒有 "
                f"{entry.stat.name} 屬性，無法用於定價。"
            )
        if amount == 0:
            raise AnchorItemMissingError(
                f"錨定裝備 {entry.item_id}（{anchor.name}）的 "
                f"{entry.stat.name} 數量為 0，無法作為分母。"
            )
        return anchor.total_gold / amount


class LeastSquaresDeriver:
    """把所有裝備當聯立方程式，一次解出全部屬性的單價。

    解 A·x ≈ b，x ≥ 0：
      A[i][j] = 裝備 i 的屬性 j 數量（已正規化）
      b[i]    = 裝備 i 的總價

    用非負最小平方（NNLS）而非普通最小平方，因為屬性單價不該為負。

    優點：所有出現過的屬性都有價，沒有「未定價」黑洞。
    代價：單價不再能用「長劍 350g」直接驗證，且殘差被平均分攤到各屬性上。
    """

    LOW_CONFIDENCE_THRESHOLD = 5

    def __init__(
        self, diagnostics: Diagnostics, low_confidence_threshold: int | None = None
    ) -> None:
        self._diagnostics = diagnostics
        self._threshold = (
            self.LOW_CONFIDENCE_THRESHOLD
            if low_confidence_threshold is None
            else low_confidence_threshold
        )
        self.last_condition_number: float | None = None

    def derive(self, items: Sequence[Item]) -> PriceTable:
        import numpy as np
        from scipy.optimize import nnls

        rows = [i for i in items if i.stats]
        counts: dict[StatKey, int] = {}
        for i in rows:
            for line in i.stats:
                counts[line.stat] = counts.get(line.stat, 0) + 1

        prices: dict[StatKey, float | None] = {stat: None for stat in StatKey}
        if not rows or not counts:
            self.last_condition_number = None
            return PriceTable(prices=prices, low_confidence=frozenset())

        columns = sorted(counts, key=lambda s: s.name)
        matrix = np.array(
            [[i.amount_of(s) or 0.0 for s in columns] for i in rows], dtype=float
        )
        totals = np.array([float(i.total_gold) for i in rows], dtype=float)

        solution, _residual = nnls(matrix, totals)
        self.last_condition_number = float(np.linalg.cond(matrix))

        low: set[StatKey] = set()
        for stat, price in zip(columns, solution, strict=True):
            prices[stat] = float(price)
            if counts[stat] < self._threshold:
                low.add(stat)
                self._diagnostics.low_confidence_price(stat, counts[stat])

        return PriceTable(prices=prices, low_confidence=frozenset(low))
