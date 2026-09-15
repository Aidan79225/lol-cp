"""PlanBuild：fixture 全裝備 × 達瑞文真實基礎值（spec 2026-09-14 §7.2、§8）。"""

from collections import Counter
from pathlib import Path

import pytest

from lolcp.application.use_cases.plan_build import PlanBuild
from lolcp.domain.build_planner import BuildPlanner, is_boots
from lolcp.domain.combat import CombatModel
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.file_champion_repository import (
    FileChampionRepository,
)
from lolcp.infrastructure.repositories.file_item_repository import FileItemRepository
from lolcp.infrastructure.repositories.toml_config import (
    load_combat_config,
    load_planner_config,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"
CONFIG = Path(__file__).parent.parent.parent / "config"


@pytest.fixture(scope="module")
def use_case():
    diagnostics = Diagnostics()
    proxy, targets = load_combat_config(CONFIG / "combat_model.toml")
    plan_build = PlanBuild(
        items=FileItemRepository(FIXTURES, ItemMapper(diagnostics)),
        planner=BuildPlanner(CombatModel(proxy)),
        targets=targets,
        settings=load_planner_config(CONFIG / "build_planner.toml"),
    )
    return plan_build, FileChampionRepository(FIXTURES, diagnostics)


@pytest.fixture(scope="module")
def draven_plans(use_case):
    plan_build, champions = use_case
    draven = champions.by_key("Draven")
    return {
        beta: plan_build.execute(draven, "squishy", beta, ())
        for beta in (0.0, 0.25, 1.0)
    }


def test_none_champion_yields_none(use_case):
    plan_build, _ = use_case
    assert plan_build.execute(None, "squishy", None, ()) is None


def test_champion_without_base_stats_yields_none(use_case):
    plan_build, _ = use_case
    ghost = Champion("Ghost", 1, "無數值", ("Mage",), "Mana", base_stats=None)
    assert plan_build.execute(ghost, "squishy", None, ()) is None


def test_unknown_target_key_is_rejected(use_case):
    plan_build, champions = use_case
    with pytest.raises(ValueError, match="nobody"):
        plan_build.execute(champions.by_key("Draven"), "nobody", None, ())


def test_exposes_default_settings_and_targets_for_the_ui(use_case):
    plan_build, _ = use_case
    assert plan_build.settings.beta == 0.25
    assert [t.key for t in plan_build.targets] == ["squishy", "tank"]


def test_plan_has_six_distinct_items(draven_plans):
    for plan in draven_plans.values():
        ids = [s.item.item_id for s in plan.steps]
        assert len(ids) == 6
        assert len(set(ids)) == 6


def test_plan_has_exactly_one_boots_in_the_second_slot(draven_plans):
    for plan in draven_plans.values():
        assert [is_boots(s.item) for s in plan.steps] == [False, True, False, False, False, False]


def test_plan_never_exceeds_a_group_cap(draven_plans):
    for plan in draven_plans.values():
        held: Counter[str] = Counter()
        caps: dict[str, int] = {}
        for step in plan.steps:
            for limit in step.item.group_limits:
                held[limit.group_id] += 1
                caps[limit.group_id] = limit.max_owned
        assert all(held[g] <= caps[g] for g in held)


def test_higher_beta_ends_with_at_least_as_much_ehp(draven_plans):
    assert draven_plans[1.0].steps[-1].ehp >= draven_plans[0.0].steps[-1].ehp


def test_prefix_ids_are_kept_and_components_reported(use_case):
    """出裝列：無盡之刃 + 靈巧披風（部件）→ 無盡保留為第 1 件、披風進 skipped。"""
    plan_build, champions = use_case
    plan = plan_build.execute(champions.by_key("Draven"), "squishy", None, (3031, 1018))
    assert plan.steps[0].item.item_id == 3031
    assert [i.item_id for i in plan.skipped] == [1018]


# ---- 黃金快照（spec §8）：改版後推薦悄悄改變時，這是唯一的警報 ----


def test_golden_draven_vs_squishy(use_case):
    """無盡 → 狂戰士護脛 → 幻影之舞 → 狂暴利刃 → 多明尼克 → 嗜血者。"""
    plan_build, champions = use_case
    plan = plan_build.execute(champions.by_key("Draven"), "squishy", None, ())
    assert [s.item.item_id for s in plan.steps] == [3031, 3006, 3046, 3097, 3036, 3072]


def test_golden_draven_vs_tank_buys_dominik_earlier(use_case):
    """打坦克時多明尼克從第 5 件提前到第 3 件 —— 百分比物穿對高護甲值錢
    （與邊際效益 spec §8 同一條數學），規劃器自己排出了這個順序。"""
    plan_build, champions = use_case
    plan = plan_build.execute(champions.by_key("Draven"), "tank", None, ())
    assert [s.item.item_id for s in plan.steps] == [3031, 3006, 3036, 3046, 3097, 3072]


def test_unknown_prefix_ids_are_ignored(use_case):
    plan_build, champions = use_case
    draven = champions.by_key("Draven")
    assert plan_build.execute(draven, "squishy", None, (999999,)) == plan_build.execute(
        draven, "squishy", None, ()
    )
