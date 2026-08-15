"""列出所有裝備在指定英雄視角下的兩種 CP值。"""

from __future__ import annotations

from lolcp.application.ports import ItemRepository
from lolcp.domain.entities import Champion
from lolcp.domain.pricing import PriceDeriver
from lolcp.domain.valuation import ItemComparison, ItemValuation
from lolcp.domain.weights import WeightResolver


class ListValuations:
    def __init__(
        self,
        items: ItemRepository,
        canonical_deriver: PriceDeriver,
        least_squares_deriver: PriceDeriver,
        weight_resolver: WeightResolver,
        valuation: ItemValuation,
    ) -> None:
        self.items = items
        self.canonical_deriver = canonical_deriver
        self.least_squares_deriver = least_squares_deriver
        self.weight_resolver = weight_resolver
        self.valuation = valuation

    def execute(self, champion: Champion | None) -> tuple[ItemComparison, ...]:
        """champion 為 None 代表全域客觀視角（權重全 1.0）。

        兩個定價法各只跑一次 —— 單價是整個裝備集合的性質，不是單件裝備的。
        每件裝備各解一次 NNLS 會慢到不可用。
        """
        items = self.items.all_items()
        canonical_prices = self.canonical_deriver.derive(items)
        least_squares_prices = self.least_squares_deriver.derive(items)
        weights = self.weight_resolver.resolve(champion)

        return tuple(
            ItemComparison.of(
                canonical=self.valuation.evaluate(item, canonical_prices, weights),
                least_squares=self.valuation.evaluate(item, least_squares_prices, weights),
            )
            for item in items
        )
