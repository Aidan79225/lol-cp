"""裝備估值。

  每條屬性貢獻 = 數量 × 單價 × 權重
  總價值       = Σ 貢獻
  CP值         = 總價值 / 售價
  殘差         = 售價 − 總價值

殘差有兩種語意，介面措辭必須區分：
  正殘差 —— 至少這些金幣花在被動／主動效果上
  負殘差 —— 屬性本身已超值

unpriced 與 masked 必須分開儲存：「這屬性算不出價」與「這屬性對你的
英雄沒用」是完全不同的事，混在一起就無法判斷 CP值 低是資料限制
還是英雄不適配。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lolcp.domain.entities import Item
from lolcp.domain.pricing import PriceTable
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import StatWeights


@dataclass(frozen=True, slots=True)
class Contribution:
    stat: StatKey
    amount: float
    unit_price: float
    weight: float
    gold: float


@dataclass(frozen=True)
class ValuationResult:
    item: Item
    contributions: tuple[Contribution, ...]
    unpriced: tuple[StatKey, ...]
    masked: tuple[StatKey, ...]
    total_value: float
    ratio: float
    residual: float

    @property
    def residual_is_passive_value(self) -> bool:
        """殘差為正時才能稱為「被動的隱含價值」。"""
        return self.residual > 0


@dataclass(frozen=True)
class ItemComparison:
    canonical: ValuationResult
    least_squares: ValuationResult
    delta: float

    @classmethod
    def of(cls, canonical: ValuationResult, least_squares: ValuationResult) -> ItemComparison:
        return cls(canonical, least_squares, least_squares.ratio - canonical.ratio)

    @property
    def item(self) -> Item:
        return self.canonical.item


class ItemValuation(Protocol):
    def evaluate(
        self, item: Item, prices: PriceTable, weights: StatWeights
    ) -> ValuationResult: ...


class LinearValuation:
    """線性加總估值。

    這個模型假設「屬性可獨立定價後相加」。實戰價值其實是相乘的
    （DPS = AD × 攻速 × (1 + 暴擊率 × 暴擊傷害)），因此本模型回答的是
    「這件裝備的原料划不划算」，不是「這件裝備對我的英雄好不好」。
    後者需要另一個 ItemValuation 實作（見 spec §5.5）。
    """

    def evaluate(
        self, item: Item, prices: PriceTable, weights: StatWeights
    ) -> ValuationResult:
        contributions: list[Contribution] = []
        unpriced: list[StatKey] = []
        masked: list[StatKey] = []

        for line in item.stats:
            unit_price = prices.unit_price(line.stat)
            if unit_price is None:
                unpriced.append(line.stat)
                continue
            weight = weights.of(line.stat)
            if weight == 0.0:
                masked.append(line.stat)
            contributions.append(
                Contribution(
                    stat=line.stat,
                    amount=line.amount,
                    unit_price=unit_price,
                    weight=weight,
                    gold=line.amount * unit_price * weight,
                )
            )

        total_value = sum(c.gold for c in contributions)
        return ValuationResult(
            item=item,
            contributions=tuple(contributions),
            unpriced=tuple(unpriced),
            masked=tuple(masked),
            total_value=total_value,
            ratio=(total_value / item.total_gold) if item.total_gold else 0.0,
            residual=item.total_gold - total_value,
        )
