import pytest

from lolcp.domain.entities import Item
from lolcp.domain.pricing import PriceTable
from lolcp.domain.stats import StatKey, StatLine
from lolcp.domain.valuation import ItemComparison, LinearValuation
from lolcp.domain.weights import StatWeights


def item(gold: int, *stats: StatLine) -> Item:
    return Item(item_id=1, name="test", total_gold=gold, sell_gold=gold // 2,
                stats=stats, tags=(), icon="", recipe=())


def table(**prices: float | None) -> PriceTable:
    return PriceTable(
        prices={StatKey[k]: v for k, v in prices.items()}, low_confidence=frozenset()
    )


def test_contribution_is_amount_times_price_times_weight():
    result = LinearValuation().evaluate(
        item(3500, StatLine(StatKey.AD, 75.0)),
        table(AD=35.0),
        StatWeights({StatKey.AD: 1.0}),
    )
    assert result.total_value == pytest.approx(2625.0)
    assert result.contributions[0].gold == pytest.approx(2625.0)


def test_ratio_is_value_over_total_gold():
    result = LinearValuation().evaluate(
        item(3500, StatLine(StatKey.AD, 100.0)),
        table(AD=35.0),
        StatWeights.uniform(),
    )
    assert result.ratio == pytest.approx(3500.0 / 3500.0)


def test_residual_is_positive_when_stats_are_worth_less_than_price():
    result = LinearValuation().evaluate(
        item(3250, StatLine(StatKey.ARMOR, 50.0)),
        table(ARMOR=20.0),
        StatWeights.uniform(),
    )
    assert result.residual == pytest.approx(2250.0)
    assert result.residual_is_passive_value is True


def test_residual_is_negative_when_stats_exceed_price():
    """負殘差代表屬性本身已超值，不可稱為「被動價值」。"""
    result = LinearValuation().evaluate(
        item(3000, StatLine(StatKey.AD, 100.0)),
        table(AD=35.0),
        StatWeights.uniform(),
    )
    assert result.residual == pytest.approx(-500.0)
    assert result.residual_is_passive_value is False


def test_masked_stat_still_produces_a_contribution_with_zero_gold():
    """詳情面板要顯示「105 AP ×20.0 ×0.0 = 0g ⚠遮罩」。"""
    result = LinearValuation().evaluate(
        item(3250, StatLine(StatKey.AP, 105.0)),
        table(AP=20.0),
        StatWeights({StatKey.AP: 0.0}),
    )
    assert len(result.contributions) == 1
    assert result.contributions[0].gold == 0.0
    assert result.contributions[0].weight == 0.0
    assert result.masked == (StatKey.AP,)
    assert result.unpriced == ()


def test_unpriced_stat_produces_no_contribution():
    result = LinearValuation().evaluate(
        item(3500, StatLine(StatKey.AD, 75.0), StatLine(StatKey.CRIT_DAMAGE, 30.0)),
        table(AD=35.0, CRIT_DAMAGE=None),
        StatWeights.uniform(),
    )
    assert [c.stat for c in result.contributions] == [StatKey.AD]
    assert result.unpriced == (StatKey.CRIT_DAMAGE,)
    assert result.masked == ()


def test_masked_and_unpriced_are_tracked_separately():
    """「算不出價」與「英雄用不到」混在一起就無法判斷 CP值 低的原因。"""
    result = LinearValuation().evaluate(
        item(3000, StatLine(StatKey.AP, 100.0), StatLine(StatKey.LIFE_STEAL, 10.0)),
        table(AP=20.0, LIFE_STEAL=None),
        StatWeights({StatKey.AP: 0.0}),
    )
    assert result.masked == (StatKey.AP,)
    assert result.unpriced == (StatKey.LIFE_STEAL,)


def test_a_stat_priced_at_zero_is_not_unpriced():
    """NNLS 可能把屬性解成 0.0，那與無法定價是不同的事。"""
    result = LinearValuation().evaluate(
        item(1000, StatLine(StatKey.TENACITY, 20.0)),
        table(TENACITY=0.0),
        StatWeights.uniform(),
    )
    assert result.unpriced == ()
    assert result.contributions[0].gold == 0.0
    assert result.masked == ()  # 權重是 1.0，不是遮罩


def test_zero_gold_item_does_not_divide_by_zero():
    result = LinearValuation().evaluate(
        item(0, StatLine(StatKey.AD, 10.0)), table(AD=35.0), StatWeights.uniform()
    )
    assert result.ratio == 0.0


def test_comparison_delta_is_least_squares_minus_canonical():
    canonical = LinearValuation().evaluate(
        item(1000, StatLine(StatKey.AD, 10.0)), table(AD=35.0), StatWeights.uniform()
    )
    least_squares = LinearValuation().evaluate(
        item(1000, StatLine(StatKey.AD, 10.0)), table(AD=40.0), StatWeights.uniform()
    )
    comparison = ItemComparison.of(canonical, least_squares)
    assert comparison.delta == pytest.approx(0.05)
