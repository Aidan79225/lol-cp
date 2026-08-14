"""最小平方法在 16.15.1 上的結果。

規格撰寫時本機無 scipy，故實際單價由本專案首次求解後釘住。
取得實際值的方式是執行 `uv run python scripts/report_ls_prices.py`
（見本任務 Step 6），不是寫一個不斷言的測試。
"""

import json
from pathlib import Path

import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.pricing import LeastSquaresDeriver
from lolcp.domain.stats import SR_STATS, StatKey
from lolcp.infrastructure.mapping import ItemMapper

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"

EXPECTED = {
    StatKey.ABILITY_HASTE: 29.129744674632903,
    StatKey.AD: 37.92444300496639,
    StatKey.AP: 21.90938971522314,
    StatKey.ARMOR: 23.530691612942334,
    StatKey.ARMOR_PEN_PERCENT: 26.751674612493645,  # 低信賴
    StatKey.ATTACK_SPEED: 25.655047512944066,
    StatKey.BASE_HP_REGEN: 0.9108732300245178,
    StatKey.CRIT_CHANCE: 38.99035474991235,
    StatKey.CRIT_DAMAGE: 0.0,  # 低信賴
    StatKey.HEAL_SHIELD_POWER: 105.194963754671,
    StatKey.HP: 3.0314432726425617,
    StatKey.HP_REGEN_FLAT: 124.6614800734326,  # 低信賴
    StatKey.LIFE_STEAL: 36.990005156804806,
    StatKey.MAGIC_PEN_FLAT: 39.89996628032621,  # 低信賴
    StatKey.MAGIC_PEN_PERCENT: 24.503115869268825,  # 低信賴
    StatKey.MAGIC_RESIST: 21.17346169163412,
    StatKey.MANA: 0.9339979108912655,
    StatKey.MOVE_SPEED_FLAT: 8.992174848872494,
    StatKey.MOVE_SPEED_PERCENT: 55.28641197598388,
    StatKey.SLOW_RESIST: 18.900605405269552,  # 低信賴
    StatKey.TENACITY: 27.565483415860513,
}


@pytest.fixture(scope="module")
def solved():
    dd = json.loads((FIXTURES / "ddragon_items.json").read_text(encoding="utf-8"))["data"]
    binn = json.loads((FIXTURES / "items_bin.json").read_text(encoding="utf-8"))
    items = ItemMapper(Diagnostics()).map_all(dd, binn)
    diagnostics = Diagnostics()
    deriver = LeastSquaresDeriver(diagnostics)
    return deriver.derive(items), deriver, diagnostics, items


def test_every_stat_in_the_matrix_gets_a_price(solved):
    """最小平方法的賣點：沒有未定價黑洞。"""
    table, _deriver, _diag, items = solved
    present = {line.stat for i in items for line in i.stats}
    assert table.unpriced_stats(present) == frozenset()


def test_all_prices_are_non_negative(solved):
    table, _deriver, _diag, _items = solved
    for stat in table.priced_stats:
        assert table.unit_price(stat) >= 0.0, stat


def test_matrix_covers_the_twentyone_summoners_rift_stats(solved):
    table, _deriver, _diag, _items = solved
    assert table.priced_stats <= SR_STATS
    assert len(table.priced_stats) >= 18  # fixture 裁剪後可能略少於 21


def test_rare_stats_are_flagged(solved):
    """暴擊傷害只出現在 3 件裝備，必須被標記為低信賴。"""
    table, _deriver, diagnostics, _items = solved
    assert StatKey.CRIT_DAMAGE in table.low_confidence
    assert StatKey.AD not in table.low_confidence
    assert diagnostics.low_confidence_stats


@pytest.mark.parametrize("stat,expected", EXPECTED.items(), ids=lambda x: getattr(x, "name", x))
def test_least_squares_unit_price(solved, stat, expected):
    table, _deriver, _diag, _items = solved
    assert table.unit_price(stat) == pytest.approx(expected, rel=1e-6)
