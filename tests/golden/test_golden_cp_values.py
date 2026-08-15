"""16.15.1 的 CP值 黃金測試（權威法）。

12 個值 = 4 件裝備 × 3 個視角。全域／達瑞文／凱爾三個視角同時驗證了
RoleDefaults 套用、union_max 聯集、遮罩與未定價分離。
"""

import json
from pathlib import Path

import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion
from lolcp.domain.pricing import CanonicalDeriver
from lolcp.domain.stats import StatKey
from lolcp.domain.valuation import LinearValuation
from lolcp.domain.weights import ResourceRule, WeightResolver
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.toml_config import (
    load_anchors,
    load_champion_overrides,
    load_role_defaults,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"
CONFIG = Path(__file__).parent.parent.parent / "config"

IE, TRIFORCE, ZHONYA, BOTRK = 3031, 3078, 3157, 3153

DRAVEN = Champion("Draven", 119, "達瑞文", ("Marksman",), "Mana")
KAYLE = Champion("Kayle", 10, "凱爾", ("Mage", "Marksman"), "Mana")

# (視角, 裝備) → (CP值 %, 殘差, 未定價數, 遮罩數)
EXPECTED = {
    (None, TRIFORCE): (109.5, -315.0, 0, 0),
    (None, IE): (103.6, -125.0, 1, 0),
    (None, ZHONYA): (95.4, 150.0, 0, 0),
    (None, BOTRK): (80.0, 639.3, 0, 0),         # 吸血以扣除法計價後不再是下限

    ("Draven", IE): (103.6, -125.0, 1, 0),      # 與全域相同：完全適配
    ("Draven", TRIFORCE): (82.2, 593.0, 0, 0),
    ("Draven", BOTRK): (80.0, 639.3, 0, 0),     # 與全域相同：AD/攻速/吸血權重皆 1.0
    ("Draven", ZHONYA): (9.2, 2950.0, 0, 1),    # 105 法強全遮罩

    ("Kayle", IE): (103.6, -125.0, 1, 0),
    ("Kayle", TRIFORCE): (98.8, 40.0, 0, 0),
    ("Kayle", ZHONYA): (80.0, 650.0, 0, 0),     # 聯集保住 AP，遮罩數為 0
    ("Kayle", BOTRK): (80.0, 639.3, 0, 0),      # Mage∪Marksman 聯集後同上
}


@pytest.fixture(scope="module")
def engine():
    dd = json.loads((FIXTURES / "ddragon_items.json").read_text(encoding="utf-8"))["data"]
    binn = json.loads((FIXTURES / "items_bin.json").read_text(encoding="utf-8"))
    items = ItemMapper(Diagnostics()).map_all(dd, binn)
    by_id = {i.item_id: i for i in items}
    prices = CanonicalDeriver(load_anchors(CONFIG / "anchors.toml"), Diagnostics()).derive(items)
    diagnostics = Diagnostics()
    resolver = WeightResolver(
        role_defaults=load_role_defaults(CONFIG / "role_defaults.toml"),
        resource_rule=ResourceRule(diagnostics),
        overrides=load_champion_overrides(CONFIG / "champions"),
        diagnostics=diagnostics,
    )
    champions = {"Draven": DRAVEN, "Kayle": KAYLE, None: None}
    return by_id, prices, resolver, champions


@pytest.mark.parametrize(
    "view,item_id,expected",
    [(v, i, e) for (v, i), e in EXPECTED.items()],
    ids=[f"{v or 'global'}-{i}" for v, i in EXPECTED],
)
def test_golden_cp_value(engine, view, item_id, expected):
    by_id, prices, resolver, champions = engine
    expected_ratio, expected_residual, expected_unpriced, expected_masked = expected

    weights = resolver.resolve(champions[view])
    result = LinearValuation().evaluate(by_id[item_id], prices, weights)

    assert result.ratio * 100 == pytest.approx(expected_ratio, abs=0.05)
    assert result.residual == pytest.approx(expected_residual, abs=1.0)
    assert len(result.unpriced) == expected_unpriced
    assert len(result.masked) == expected_masked


def test_zhonyas_differs_eightfold_between_draven_and_kayle(engine):
    """union_max 的最強斷言。

    若聯集誤用平均，凱爾的 AP 權重會掉到 0.5，中婭沙漏變成 ~48%；
    若誤取單一 tag，會變成 9.2% 或 80.0% 之一。只有 max 給出 80.0%。
    """
    by_id, prices, resolver, _ = engine
    draven = LinearValuation().evaluate(by_id[ZHONYA], prices, resolver.resolve(DRAVEN))
    kayle = LinearValuation().evaluate(by_id[ZHONYA], prices, resolver.resolve(KAYLE))
    assert kayle.ratio / draven.ratio == pytest.approx(8.67, abs=0.1)
    assert draven.masked == (StatKey.AP,)
    assert kayle.masked == ()


def test_infinity_edge_is_identical_across_all_three_views(engine):
    """英雄視角不是一律壓低數字，而是有選擇性的。"""
    by_id, prices, resolver, _ = engine
    ratios = {
        name: LinearValuation().evaluate(by_id[IE], prices, resolver.resolve(champ)).ratio
        for name, champ in (("global", None), ("draven", DRAVEN), ("kayle", KAYLE))
    }
    assert len(set(round(r, 6) for r in ratios.values())) == 1


def test_crit_damage_is_the_unpriced_stat_on_infinity_edge(engine):
    """無盡之刃 103.6% 是下限 —— 30% 暴擊傷害沒被算進去。"""
    by_id, prices, resolver, _ = engine
    result = LinearValuation().evaluate(by_id[IE], prices, resolver.resolve(None))
    assert result.unpriced == (StatKey.CRIT_DAMAGE,)


def test_vampiric_scepter_is_locked_to_exactly_100_percent(engine):
    """扣除錨的固有代價：錨定裝備自身 CP值 恆為 100%、殘差 0。

    這個黃金值同時驗證扣除法的算式 —— 若單價不是 375/7，比率不會是 1。
    """
    by_id, prices, resolver, _ = engine
    result = LinearValuation().evaluate(by_id[1053], prices, resolver.resolve(None))
    assert result.ratio == pytest.approx(1.0)
    assert result.residual == pytest.approx(0.0, abs=1e-9)
    assert result.unpriced == ()
