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

# 盲點修復（2026-08-15）後重解：矩陣 199×25，新增穿甲／全能吸血／
# 魔回欄位，全部單價因此位移。穿甲 NNLS 33.7 與扣除法 30.0 互相印證。
EXPECTED = {
    StatKey.ABILITY_HASTE: 25.49551156955071,
    StatKey.AD: 34.49684452064819,
    StatKey.AP: 21.763464710569853,
    StatKey.ARMOR: 24.05586807238905,
    StatKey.ARMOR_PEN_FLAT: 33.72169217896334,
    StatKey.ARMOR_PEN_PERCENT: 30.03427491659117,  # 低信賴
    StatKey.ATTACK_SPEED: 27.143080099020466,
    StatKey.BASE_HP_REGEN: 0.0,
    StatKey.BASE_MP_REGEN: 2.2041862207918674,
    StatKey.CRIT_CHANCE: 41.622901508000666,
    StatKey.CRIT_DAMAGE: 0.0,  # 低信賴
    StatKey.HEAL_SHIELD_POWER: 87.69347351175705,
    StatKey.HP: 3.1484556229580254,
    StatKey.HP_REGEN_FLAT: 119.82346943538934,  # 低信賴
    StatKey.LIFE_STEAL: 52.66609344006688,
    StatKey.MAGIC_PEN_FLAT: 42.55726189912084,  # 低信賴
    StatKey.MAGIC_PEN_PERCENT: 25.59710662625139,  # 低信賴
    StatKey.MAGIC_RESIST: 21.88364614333552,
    StatKey.MANA: 1.0232288369564027,
    StatKey.MOVE_SPEED_FLAT: 8.265187237134157,
    StatKey.MOVE_SPEED_PERCENT: 42.20059245095754,
    StatKey.MP_REGEN_FLAT: 0.0,  # 低信賴
    StatKey.OMNIVAMP: 27.61891582373378,
    StatKey.SLOW_RESIST: 20.201301397484364,  # 低信賴
    StatKey.TENACITY: 27.40824305794396,
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


def test_matrix_covers_the_twentyfive_summoners_rift_stats(solved):
    table, _deriver, _diag, _items = solved
    assert table.priced_stats <= SR_STATS
    assert len(table.priced_stats) >= 22  # fixture 裁剪後可能略少於 25


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
