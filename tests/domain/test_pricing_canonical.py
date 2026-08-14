import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Item
from lolcp.domain.pricing import (
    AnchorConfig,
    AnchorEntry,
    AnchorItemMissingError,
    CanonicalDeriver,
    PriceTable,
)
from lolcp.domain.stats import StatKey, StatLine


def item(item_id: int, gold: int, *stats: StatLine) -> Item:
    return Item(item_id=item_id, name=f"item{item_id}", total_gold=gold,
                sell_gold=gold // 2, stats=stats, tags=(), icon="", recipe=())


def anchors(*pairs: tuple[StatKey, int]) -> AnchorConfig:
    return AnchorConfig(tuple(AnchorEntry(s, i, "test") for s, i in pairs))


def test_price_table_distinguishes_zero_from_unpriced():
    table = PriceTable(prices={StatKey.AD: 0.0, StatKey.AP: None}, low_confidence=frozenset())
    assert table.unit_price(StatKey.AD) == 0.0
    assert table.is_priced(StatKey.AD) is True
    assert table.unit_price(StatKey.AP) is None
    assert table.is_priced(StatKey.AP) is False


def test_unpriced_stats_reports_only_present_stats_without_a_price():
    table = PriceTable(prices={StatKey.AD: 35.0, StatKey.AP: None}, low_confidence=frozenset())
    present = [StatKey.AD, StatKey.AP, StatKey.TENACITY]
    assert table.unpriced_stats(present) == frozenset({StatKey.AP, StatKey.TENACITY})


def test_derives_unit_price_from_anchor_item():
    items = [item(1036, 350, StatLine(StatKey.AD, 10.0))]
    table = CanonicalDeriver(anchors((StatKey.AD, 1036)), Diagnostics()).derive(items)
    assert table.unit_price(StatKey.AD) == 35.0


def test_normalized_percent_anchor_gives_price_per_one_percent():
    """靈巧披風 600g / 15.0（正規化後的 15%）= 40.0 每 1%。"""
    items = [item(1018, 600, StatLine(StatKey.CRIT_CHANCE, 15.0))]
    table = CanonicalDeriver(anchors((StatKey.CRIT_CHANCE, 1018)), Diagnostics()).derive(items)
    assert table.unit_price(StatKey.CRIT_CHANCE) == 40.0


def test_stats_without_an_anchor_are_unpriced_not_zero():
    items = [item(1036, 350, StatLine(StatKey.AD, 10.0))]
    table = CanonicalDeriver(anchors((StatKey.AD, 1036)), Diagnostics()).derive(items)
    assert table.unit_price(StatKey.TENACITY) is None


def test_missing_anchor_item_fails_loudly():
    """錨定裝備被 Riot 移除時必須立刻大聲失敗，不可靜默降級。

    藍水晶曾被移除過，這種事遲早發生。
    """
    with pytest.raises(AnchorItemMissingError, match="1036"):
        CanonicalDeriver(anchors((StatKey.AD, 1036)), Diagnostics()).derive([])


def test_anchor_item_lacking_the_stat_fails_loudly():
    items = [item(1036, 350, StatLine(StatKey.AP, 20.0))]
    with pytest.raises(AnchorItemMissingError, match="AD"):
        CanonicalDeriver(anchors((StatKey.AD, 1036)), Diagnostics()).derive(items)


def test_anchor_item_with_zero_amount_fails_loudly():
    """比對「數量為 0」而非只比對 "0" —— 後者會被訊息裡的裝備 ID 1036 誤中，
    連錯誤分支都能讓測試通過。"""
    items = [item(1036, 350, StatLine(StatKey.AD, 0.0))]
    with pytest.raises(AnchorItemMissingError, match="數量為 0"):
        CanonicalDeriver(anchors((StatKey.AD, 1036)), Diagnostics()).derive(items)


def test_canonical_has_no_low_confidence_stats():
    """權威法的單價直接來自單一裝備，沒有統計信賴度問題。"""
    items = [item(1036, 350, StatLine(StatKey.AD, 10.0))]
    table = CanonicalDeriver(anchors((StatKey.AD, 1036)), Diagnostics()).derive(items)
    assert table.low_confidence == frozenset()
