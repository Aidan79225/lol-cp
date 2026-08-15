"""釘住 16.15.1 的權威法單價。

這是唯一能發現「改版後計算悄悄變了」的機制。
若這些值變動，先確認是 Riot 改了數值還是我們算錯了。
"""

import json
from pathlib import Path

import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.pricing import CanonicalDeriver
from lolcp.domain.stats import StatKey
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.toml_config import load_anchors

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"
ANCHORS = Path(__file__).parent.parent.parent / "config" / "anchors.toml"

EXPECTED_PRICES = {
    StatKey.AD: 35.0,
    StatKey.AP: 20.0,
    StatKey.HP: 400 / 150,          # 2.6667
    StatKey.MANA: 1.0,
    StatKey.ARMOR: 20.0,
    StatKey.MAGIC_RESIST: 20.0,
    StatKey.CRIT_CHANCE: 40.0,      # 每 1%
    StatKey.ATTACK_SPEED: 25.0,     # 每 1%
    StatKey.ABILITY_HASTE: 50.0,
    StatKey.MOVE_SPEED_FLAT: 12.0,
    StatKey.BASE_HP_REGEN: 3.0,     # 每 1% —— 正規化陷阱，不是 300.0
    StatKey.LIFE_STEAL: 375 / 7,          # 53.571 每 1% —— 扣除錨：權杖 900 − 15AD×35
    StatKey.ARMOR_PEN_PERCENT: 750 / 18,  # 41.667 每 1% —— 扣除錨：最後耳語 1450 − 20AD×35
}

UNPRICED = [
    StatKey.CRIT_DAMAGE, StatKey.HP_REGEN_FLAT,
    StatKey.MOVE_SPEED_PERCENT, StatKey.HEAL_SHIELD_POWER, StatKey.TENACITY,
    StatKey.SLOW_RESIST, StatKey.MAGIC_PEN_FLAT, StatKey.MAGIC_PEN_PERCENT,
    StatKey.ARMOR_PEN_FLAT,   # 盲點修復後現身；下一步將設扣除錨（殘暴之力）
    StatKey.OMNIVAMP, StatKey.BASE_MP_REGEN, StatKey.MP_REGEN_FLAT,
]


@pytest.fixture(scope="module")
def price_table():
    dd = json.loads((FIXTURES / "ddragon_items.json").read_text(encoding="utf-8"))["data"]
    binn = json.loads((FIXTURES / "items_bin.json").read_text(encoding="utf-8"))
    items = ItemMapper(Diagnostics()).map_all(dd, binn)
    return CanonicalDeriver(load_anchors(ANCHORS), Diagnostics()).derive(items)


@pytest.mark.parametrize("stat,expected", EXPECTED_PRICES.items(), ids=lambda x: getattr(x, "name", x))
def test_anchor_unit_price(price_table, stat, expected):
    assert price_table.unit_price(stat) == pytest.approx(expected, rel=1e-9)


def test_base_hp_regen_is_three_not_three_hundred(price_table):
    """治療寶珠 300g，bin 值 1.0 正規化為 100.0，單價 3.0。

    若忘記正規化就用 300/1.0，會得到 300.0，把該屬性放大 100 倍。
    """
    assert price_table.unit_price(StatKey.BASE_HP_REGEN) == pytest.approx(3.0)


@pytest.mark.parametrize("stat", UNPRICED, ids=lambda s: s.name)
def test_stats_without_anchors_stay_unpriced(price_table, stat):
    assert price_table.unit_price(stat) is None


def test_exactly_thirteen_stats_are_priced(price_table):
    assert len(price_table.priced_stats) == 13
