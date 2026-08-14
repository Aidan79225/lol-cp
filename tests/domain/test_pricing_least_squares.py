import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Item
from lolcp.domain.pricing import LeastSquaresDeriver
from lolcp.domain.stats import StatKey, StatLine


def item(item_id: int, gold: int, *stats: StatLine) -> Item:
    return Item(item_id=item_id, name=f"item{item_id}", total_gold=gold,
                sell_gold=gold // 2, stats=stats, tags=(), icon="", recipe=())


def test_solves_a_system_with_an_exact_known_answer():
    """10 AD = 350g、20 AP = 400g、10 AD + 20 AP = 750g → AD 35、AP 20。"""
    items = [
        item(1, 350, StatLine(StatKey.AD, 10.0)),
        item(2, 400, StatLine(StatKey.AP, 20.0)),
        item(3, 750, StatLine(StatKey.AD, 10.0), StatLine(StatKey.AP, 20.0)),
    ]
    deriver = LeastSquaresDeriver(Diagnostics(), low_confidence_threshold=1)
    table = deriver.derive(items)
    assert table.unit_price(StatKey.AD) == pytest.approx(35.0, abs=1e-6)
    assert table.unit_price(StatKey.AP) == pytest.approx(20.0, abs=1e-6)


def test_solution_is_never_negative():
    """NNLS 而非普通最小平方：屬性單價不該是負的。"""
    items = [
        item(1, 100, StatLine(StatKey.AD, 10.0)),
        item(2, 100, StatLine(StatKey.AD, 10.0), StatLine(StatKey.AP, 50.0)),
    ]
    table = LeastSquaresDeriver(Diagnostics(), low_confidence_threshold=1).derive(items)
    for stat in (StatKey.AD, StatKey.AP):
        price = table.unit_price(stat)
        assert price is not None and price >= 0.0


def test_stats_absent_from_the_matrix_are_none_not_zero():
    items = [item(1, 350, StatLine(StatKey.AD, 10.0))]
    table = LeastSquaresDeriver(Diagnostics(), low_confidence_threshold=1).derive(items)
    assert table.unit_price(StatKey.TENACITY) is None


def test_a_stat_solved_as_zero_is_zero_not_none():
    """解出 0.0 與無法定價是不同的事，必須可區分。"""
    items = [
        item(1, 350, StatLine(StatKey.AD, 10.0)),
        item(2, 350, StatLine(StatKey.AD, 10.0), StatLine(StatKey.TENACITY, 20.0)),
        item(3, 700, StatLine(StatKey.AD, 20.0), StatLine(StatKey.TENACITY, 20.0)),
    ]
    table = LeastSquaresDeriver(Diagnostics(), low_confidence_threshold=1).derive(items)
    assert table.unit_price(StatKey.TENACITY) == pytest.approx(0.0, abs=1e-6)
    assert table.is_priced(StatKey.TENACITY) is True


def test_rare_stats_are_flagged_low_confidence():
    """出現在少於門檻件數的屬性，解出的單價實質是殘差在硬湊。"""
    items = [
        item(1, 350, StatLine(StatKey.AD, 10.0)),
        item(2, 700, StatLine(StatKey.AD, 20.0)),
        item(3, 1050, StatLine(StatKey.AD, 30.0)),
        item(4, 1400, StatLine(StatKey.AD, 40.0)),
        item(5, 1750, StatLine(StatKey.AD, 50.0)),
        item(6, 500, StatLine(StatKey.CRIT_DAMAGE, 30.0)),
    ]
    diagnostics = Diagnostics()
    table = LeastSquaresDeriver(diagnostics, low_confidence_threshold=5).derive(items)
    assert StatKey.CRIT_DAMAGE in table.low_confidence
    assert StatKey.AD not in table.low_confidence
    assert diagnostics.low_confidence_stats == {StatKey.CRIT_DAMAGE: 1}


def test_condition_number_is_exposed():
    items = [
        item(1, 350, StatLine(StatKey.AD, 10.0)),
        item(2, 400, StatLine(StatKey.AP, 20.0)),
    ]
    deriver = LeastSquaresDeriver(Diagnostics(), low_confidence_threshold=1)
    deriver.derive(items)
    assert deriver.last_condition_number is not None
    assert deriver.last_condition_number > 0


def test_items_without_any_stats_are_excluded_from_the_matrix():
    items = [
        item(1, 350, StatLine(StatKey.AD, 10.0)),
        item(2, 500),  # 純被動裝備，無屬性
    ]
    table = LeastSquaresDeriver(Diagnostics(), low_confidence_threshold=1).derive(items)
    assert table.unit_price(StatKey.AD) == pytest.approx(35.0, abs=1e-6)


def test_empty_item_list_yields_all_unpriced():
    table = LeastSquaresDeriver(Diagnostics()).derive([])
    assert table.priced_stats == frozenset()
