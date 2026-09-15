"""ComputeMarginals：fixture 全裝備 × 達瑞文真實基礎值。"""

from pathlib import Path

import pytest

from lolcp.application.use_cases.compute_marginals import ComputeMarginals
from lolcp.domain.combat import CombatModel
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion
from lolcp.domain.champion_kits import ChampionKitBinder
from lolcp.domain.item_effects import ItemEffectBinder
from lolcp.infrastructure.champion_spell_mapper import ChampionSpellMapper
from lolcp.infrastructure.repositories.file_champion_spells_repository import (
    FileChampionSpellsRepository,
)
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.file_champion_repository import (
    FileChampionRepository,
)
from lolcp.infrastructure.repositories.file_item_repository import FileItemRepository
from lolcp.infrastructure.repositories.toml_config import load_combat_config, load_kit_configs

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"
CONFIG = Path(__file__).parent.parent.parent / "config"


def build(with_kits: bool):
    diagnostics = Diagnostics()
    proxy, targets, fight = load_combat_config(CONFIG / "combat_model.toml")
    items = FileItemRepository(FIXTURES, ItemMapper(diagnostics))
    effects = ItemEffectBinder(diagnostics).bind(items.all_items())  # 與組裝根相同
    kits = {}
    if with_kits:
        spells = FileChampionSpellsRepository(FIXTURES, ChampionSpellMapper(diagnostics), diagnostics)
        kits = ChampionKitBinder(diagnostics).bind(spells.spells_for, load_kit_configs(CONFIG / "kits"))
    return ComputeMarginals(
        items=items,
        model=CombatModel(proxy, fight, effects),
        targets=targets,
        kits=kits,
    ), FileChampionRepository(FIXTURES, diagnostics)


@pytest.fixture(scope="module")
def use_case():
    return build(with_kits=True)


def test_kit_changes_the_marginals_for_its_champion():
    """有技能模型時，達瑞文的邊際值不再來自泛用基準技能。"""
    with_kit, champions = build(with_kits=True)
    generic, _ = build(with_kits=False)
    draven = champions.by_key("Draven")

    def ie(compute):
        return next(r for r in compute.execute(draven, 11, ()) if r.item.item_id == 3031).dps_per_1k["squishy"]

    assert ie(with_kit) != pytest.approx(ie(generic))


def test_returns_one_result_per_item(use_case):
    compute, champions = use_case
    draven = champions.by_key("Draven")
    results = compute.execute(draven, 11, ())
    assert len(results) == len(compute.items.all_items())


def test_none_champion_yields_empty(use_case):
    compute, _ = use_case
    assert compute.execute(None, 11, ()) == ()


def test_champion_without_base_stats_yields_empty(use_case):
    compute, _ = use_case
    ghost = Champion("Ghost", 1, "無數值", ("Mage",), "Mana", base_stats=None)
    assert compute.execute(ghost, 11, ()) == ()


def test_build_ids_change_the_marginals(use_case):
    """出裝脈絡生效：蒐集者+靈巧披風在手後，無盡之刃的邊際值上升。"""
    compute, champions = use_case
    draven = champions.by_key("Draven")

    def ie_dps(build_ids):
        results = compute.execute(draven, 11, build_ids)
        return next(r for r in results if r.item.item_id == 3031).dps_per_1k["squishy"]

    assert ie_dps((6676, 1018)) > ie_dps(())


def test_unknown_build_ids_are_ignored(use_case):
    compute, champions = use_case
    draven = champions.by_key("Draven")
    with_ghost = compute.execute(draven, 11, (999999,))
    without = compute.execute(draven, 11, ())
    assert with_ghost == without
