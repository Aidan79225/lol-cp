from pathlib import Path

import pytest

from lolcp.application.use_cases.list_valuations import ListValuations
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion
from lolcp.domain.pricing import CanonicalDeriver, LeastSquaresDeriver
from lolcp.domain.valuation import LinearValuation
from lolcp.domain.weights import ResourceRule, WeightResolver
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.file_item_repository import FileItemRepository
from lolcp.infrastructure.repositories.toml_config import (
    load_anchors,
    load_champion_overrides,
    load_role_defaults,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"
CONFIG = Path(__file__).parent.parent.parent / "config"
# champions/ 是使用者可變資料（權重拉桿會寫入），測試讀凍結複本
FROZEN_CHAMPIONS = Path(__file__).parent.parent / "fixtures" / "config" / "champions"

DRAVEN = Champion("Draven", 119, "達瑞文", ("Marksman",), "Mana")


@pytest.fixture(scope="module")
def use_case():
    diagnostics = Diagnostics()
    repo = FileItemRepository(FIXTURES, ItemMapper(diagnostics))
    return ListValuations(
        items=repo,
        canonical_deriver=CanonicalDeriver(load_anchors(CONFIG / "anchors.toml"), diagnostics),
        least_squares_deriver=LeastSquaresDeriver(diagnostics),
        weight_resolver=WeightResolver(
            role_defaults=load_role_defaults(CONFIG / "role_defaults.toml"),
            resource_rule=ResourceRule(diagnostics),
            overrides=load_champion_overrides(FROZEN_CHAMPIONS),
            diagnostics=diagnostics,
        ),
        valuation=LinearValuation(),
    )


def test_returns_one_comparison_per_item(use_case):
    comparisons = use_case.execute(None)
    assert len(comparisons) == len(use_case.items.all_items())


def test_each_comparison_carries_both_pricing_methods(use_case):
    comparison = next(c for c in use_case.execute(None) if c.item.item_id == 3031)
    assert comparison.canonical.ratio > 0
    assert comparison.least_squares.ratio > 0
    assert comparison.delta == pytest.approx(
        comparison.least_squares.ratio - comparison.canonical.ratio
    )


def test_global_view_masks_nothing(use_case):
    for comparison in use_case.execute(None):
        assert comparison.canonical.masked == ()


def test_champion_view_masks_ability_power_items(use_case):
    zhonya = next(c for c in use_case.execute(DRAVEN) if c.item.item_id == 3157)
    assert zhonya.canonical.masked != ()
    assert zhonya.canonical.ratio < 0.2


def test_switching_view_changes_results_without_reloading_items(use_case):
    before = use_case.items.all_items()
    use_case.execute(DRAVEN)
    assert use_case.items.all_items() is before  # repository 有快取


def test_prices_are_derived_once_per_execute_not_per_item(use_case):
    """定價法必須在 execute 內只跑一次；每件裝備各解一次 NNLS 會慢到不可用。"""
    calls = {"n": 0}
    original = use_case.least_squares_deriver.derive

    def counting(items):
        calls["n"] += 1
        return original(items)

    use_case.least_squares_deriver.derive = counting  # type: ignore[method-assign]
    try:
        use_case.execute(None)
    finally:
        use_case.least_squares_deriver.derive = original  # type: ignore[method-assign]
    assert calls["n"] == 1
