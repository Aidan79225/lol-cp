"""PlanBuild：fixture 全裝備 × 達瑞文真實基礎值（spec 2026-09-14 §7.2、§8）。"""

from collections import Counter
from pathlib import Path

import pytest

from lolcp.application.use_cases.plan_build import PlanBuild
from lolcp.domain.build_planner import BuildPlanner, is_boots
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
from lolcp.infrastructure.repositories.toml_config import (
    load_combat_config,
    load_kit_configs,
    load_planner_config,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"
CONFIG = Path(__file__).parent.parent.parent / "config"


@pytest.fixture(scope="module")
def use_case():
    """與組裝根相同：綁定裝備被動 —— 黃金快照必須反映實際 app 的模型。"""
    diagnostics = Diagnostics()
    proxy, targets, fight = load_combat_config(CONFIG / "combat_model.toml")
    items = FileItemRepository(FIXTURES, ItemMapper(diagnostics))
    effects = ItemEffectBinder(diagnostics).bind(items.all_items())
    spells = FileChampionSpellsRepository(FIXTURES, ChampionSpellMapper(diagnostics), diagnostics)
    kits = ChampionKitBinder(diagnostics).bind(spells.spells_for, load_kit_configs(CONFIG / "kits"))
    plan_build = PlanBuild(
        items=items,
        planner=BuildPlanner(CombatModel(proxy, fight, effects)),
        targets=targets,
        settings=load_planner_config(CONFIG / "build_planner.toml"),
        kits=kits,
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


def plan_ids(use_case, key, target):
    plan_build, champions = use_case
    return [s.item.item_id for s in plan_build.execute(champions.by_key(key), target, None, ()).steps]


def test_golden_draven_vs_squishy(use_case):
    """雲陶狂箭 → 狂戰士護脛 → 臨界點 → 蒐集者 → 無盡 → 狂暴利刃（含被動與技能）。

    Q 強化普攻不吃暴擊也不是命中特效 —— 鬼索的倍增對達瑞文不划算，轉向暴擊＋穿甲。"""
    assert plan_ids(use_case, "Draven", "squishy") == [3032, 3006, 3302, 6676, 3031, 3097]


def test_golden_draven_vs_tank_opens_with_botrk(use_case):
    """破敗 → 狂戰士護脛 → 多明尼克 → 雲陶狂箭 → 鬼索 → 無盡。

    雲陶狂箭的 Flurry 改為依冷卻實算（不再常駐）後，打坦克時它由第 1 件退到第 4 件，
    開局讓給吃當前生命的破敗 —— 4000 血的目標讓現血傷害更值錢（spec 2026-09-16）。"""
    assert plan_ids(use_case, "Draven", "tank") == [3153, 3006, 3036, 3032, 3124, 3031]


def test_golden_kayle_vs_squishy_opens_with_guinsoo(use_case):
    """鬼索 → 狂戰士護脛 → 海妖 → 臨界點 → 雲陶狂箭 → 無盡。

    E 被動是命中特效、11 級起劍氣 —— 鬼索的 4/3 倍增吃到最多，命中特效流排在前。"""
    assert plan_ids(use_case, "Kayle", "squishy") == [3124, 3006, 6672, 3302, 3032, 3031]


def test_golden_samira_vs_squishy(use_case):
    """雲陶狂箭 → 狂戰士護脛 → 無盡 → 蒐集者 → 多明尼克 → 破堡者。

    R 十發每發可暴擊、Q 吃半額暴傷 —— 無盡提前到第 3 件。"""
    assert plan_ids(use_case, "Samira", "squishy") == [3032, 3006, 3031, 6676, 3036, 2520]


def test_fixture_binds_every_kit(use_case):
    plan_build, _ = use_case
    assert set(plan_build.kits) == {"Draven", "Kayle", "Samira"}


def test_the_three_champions_get_different_plans(use_case):
    """英雄技能這一步的核心驗收（spec champion-kits §10）：推薦反映各自機制。"""
    plan_build, champions = use_case
    sequences = {
        key: tuple(s.item.item_id for s in plan_build.execute(champions.by_key(key), "squishy", None, ()).steps)
        for key in ("Draven", "Kayle", "Samira")
    }
    assert len(set(sequences.values())) == 3, sequences


def test_fixture_binds_every_passive(use_case):
    """快照前提：22 件被動全數綁定（缺一件，快照就不是在測設計的模型）。"""
    plan_build, _ = use_case
    assert len(plan_build._planner._model.effect_ids) == 22


def test_unknown_prefix_ids_are_ignored(use_case):
    plan_build, champions = use_case
    draven = champions.by_key("Draven")
    assert plan_build.execute(draven, "squishy", None, (999999,)) == plan_build.execute(
        draven, "squishy", None, ()
    )
