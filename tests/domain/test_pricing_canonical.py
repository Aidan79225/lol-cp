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


def test_deduction_anchor_prices_the_remainder():
    """吸血鬼權杖 (900 − 15AD×35) / 7 = 53.571... 每 1%。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    table = CanonicalDeriver(config, Diagnostics()).derive(items)
    assert table.unit_price(StatKey.LIFE_STEAL) == pytest.approx(375 / 7)


def test_deduction_entry_order_in_config_does_not_matter():
    """扣除錨寫在它依賴的純錨之前也要能解 —— 兩趟推導與設定順序無關。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
        AnchorEntry(StatKey.AD, 1036, "test"),
    ))
    table = CanonicalDeriver(config, Diagnostics()).derive(items)
    assert table.unit_price(StatKey.LIFE_STEAL) == pytest.approx(375 / 7)


def test_extra_stat_on_deduction_anchor_fails_loudly():
    """Riot 幫權杖加了新屬性 —— 目標∪deduct 必須恰好等於裝備全屬性。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0),
             StatLine(StatKey.HP, 100.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="屬性集合"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_deduct_listing_a_stat_the_item_lacks_fails_loudly():
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1018, 600, StatLine(StatKey.CRIT_CHANCE, 15.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.CRIT_CHANCE, 1018, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test",
                    deduct=(StatKey.AD, StatKey.CRIT_CHANCE)),
    ))
    with pytest.raises(AnchorItemMissingError, match="屬性集合"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_deduct_referencing_an_unanchored_stat_fails_loudly():
    """單層依賴：deduct 只能引用設定內的純錨定屬性。"""
    items = [
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="純錨定"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_deduct_referencing_another_deduction_anchor_fails_loudly():
    """扣除錨引用扣除錨也違反單層依賴，同樣要炸。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
        item(3172, 1100, StatLine(StatKey.LIFE_STEAL, 5.0), StatLine(StatKey.TENACITY, 20.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
        AnchorEntry(StatKey.TENACITY, 3172, "test", deduct=(StatKey.LIFE_STEAL,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="純錨定"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_nonpositive_remainder_fails_loudly():
    """扣完 ≤ 0 代表錨定假設崩壞，不可產生負單價或零單價。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 400, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="殘額"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_exactly_zero_remainder_also_fails():
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 525, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="殘額"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_pure_entries_default_to_empty_deduct():
    assert AnchorEntry(StatKey.AD, 1036, "test").deduct == ()
