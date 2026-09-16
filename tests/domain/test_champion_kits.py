"""英雄技能模型與戰鬥窗口（spec champion-kits §3、§6、§10）。

真技能 bin（16.15 fixture）× 玩具英雄：AD 100、攻速 1.0、生命 1000、雙抗 0、
成長 0、遠程 550；目標雙抗 0、生命 2000；基準技能傷 0；戰鬥時長 10 秒。
所有期望值由 fixture 陣列手算（註解列出技能等級與取值）。
"""

from dataclasses import replace
from pathlib import Path

import pytest

from lolcp.domain.combat import CombatModel, FightAssumptions, SpellProxy, TargetProfile
from lolcp.domain.champion_kits import KITS, BoundKit, ChampionKitBinder
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import ChampionBaseStats, Item
from lolcp.domain.item_effects import ItemEffectBinder
from lolcp.domain.kit_settings import KIT_ASSUMPTIONS
from lolcp.domain.spells import KIT_CHAMPION_KEYS, ChampionSpells
from lolcp.domain.stats import StatKey, StatLine
from lolcp.infrastructure.champion_spell_mapper import ChampionSpellMapper
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.file_champion_spells_repository import (
    FileChampionSpellsRepository,
)
from lolcp.infrastructure.repositories.file_item_repository import FileItemRepository
from lolcp.infrastructure.repositories.toml_config import load_kit_configs

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"
KITS_DIR = Path(__file__).parent.parent.parent / "config" / "kits"

TOY = ChampionBaseStats(
    attack_damage=100.0, attack_damage_growth=0.0,
    attack_speed=1.0, attack_speed_growth=0.0,
    hp=1000.0, hp_growth=0.0,
    armor=0.0, armor_growth=0.0,
    magic_resist=0.0, magic_resist_growth=0.0,
    attack_range=550.0,
)
MELEE_TOY = replace(TOY, attack_range=175.0)
DUMMY = TargetProfile("dummy", "木樁", armor=0.0, magic_resist=0.0, hp=2000.0)
FIGHT = FightAssumptions(average_current_hp_ratio=0.5, energized_attacks=4, fight_duration_seconds=10.0)
NO_SPELL = SpellProxy(base_damage=0.0, ap_ratio=0.0, base_cooldown=8.0)
FULL_CRIT = Item(item_id=990001, name="玩具暴擊", total_gold=3000, sell_gold=2100,
                 stats=(StatLine(StatKey.CRIT_CHANCE, 100.0),), tags=(), icon="", recipe=())


@pytest.fixture(scope="module")
def spells():
    diagnostics = Diagnostics()
    repo = FileChampionSpellsRepository(FIXTURES, ChampionSpellMapper(diagnostics), diagnostics)
    return {key: repo.spells_for(key) for key in KIT_CHAMPION_KEYS}


@pytest.fixture(scope="module")
def settings():
    return load_kit_configs(KITS_DIR)


@pytest.fixture(scope="module")
def items():
    return {i.item_id: i for i in FileItemRepository(FIXTURES, ItemMapper(Diagnostics())).all_items()}


def bound(spells, settings, key, **assumptions):
    s = settings[key]
    if assumptions:
        s = replace(s, assumptions={**s.assumptions, **assumptions})
    return BoundKit(KITS[key], spells[key], s)


def model_for(kit, effects=None, proxy=NO_SPELL):
    return CombatModel(proxy, FIGHT, effects or {}).for_champion(kit)


# ---- 註冊表、綁定、不變量 ----

def test_registry_keys_agree_everywhere():
    assert set(KITS) == set(KIT_CHAMPION_KEYS) == set(KIT_ASSUMPTIONS)


def test_every_kit_binds_on_real_data(spells, settings):
    diagnostics = Diagnostics()
    kits = ChampionKitBinder(diagnostics).bind(spells.get, settings)
    assert set(kits) == set(KIT_CHAMPION_KEYS)
    assert diagnostics.unbound_champion_kits == {}


def test_missing_calculation_unbinds_the_kit_and_is_recorded(spells, settings):
    draven = spells["Draven"]
    q = draven.spell("DravenSpinning")
    broken_q = replace(q, calculations=tuple(p for p in q.calculations if p[0] != "TotalDamage"))
    broken = ChampionSpells("Draven", tuple((n, broken_q if n == "DravenSpinning" else s)
                                           for n, s in draven.spells))
    diagnostics = Diagnostics()
    kits = ChampionKitBinder(diagnostics).bind({**spells, "Draven": broken}.get, settings)
    assert "Draven" not in kits
    assert diagnostics.unbound_champion_kits == {"Draven": ("calculation DravenSpinning.TotalDamage",)}


def test_missing_spells_file_skips_the_kit_silently_here(spells, settings):
    """缺檔已由 repository 留痕，binder 不重複記錄。"""
    diagnostics = Diagnostics()
    kits = ChampionKitBinder(diagnostics).bind({**spells, "Kayle": None}.get, settings)
    assert "Kayle" not in kits and diagnostics.unbound_champion_kits == {}


def test_no_kit_means_the_generic_spell_proxy(spells, settings):
    base_model = CombatModel(SpellProxy(300.0, 0.7, 8.0), FIGHT, {})
    plain = base_model.profile(TOY, 9, [])
    assert base_model.for_champion(None).total_dps(plain, DUMMY) == base_model.total_dps(plain, DUMMY)


def test_kit_replaces_the_generic_spell_proxy(spells, settings):
    """有 kit 時泛用基準技能（300 傷）不再計入 —— 達瑞文 1 級只有 Q，無窗口施放傷害。"""
    generic = CombatModel(SpellProxy(300.0, 0.7, 8.0), FIGHT, {})
    kit_model = generic.for_champion(bound(spells, settings, "Draven", q_empowered_attack_ratio=0.0))
    profile = kit_model.profile(TOY, 1, [])
    assert kit_model.total_dps(profile, DUMMY) == pytest.approx(profile.attack_speed * 100.0)


# ---- 達瑞文（§6.1）----

def test_draven_q_empowers_attacks_by_the_assumed_ratio(spells, settings):
    """9 級 Q5：TotalDamage = 60 + 1.15 × 額外 AD 0 = 60；不吃暴擊、不是命中特效。"""
    on = model_for(bound(spells, settings, "Draven", q_empowered_attack_ratio=1.0))
    off = model_for(bound(spells, settings, "Draven", q_empowered_attack_ratio=0.0))
    p_on, p_off = on.profile(TOY, 9, []), off.profile(TOY, 9, [])
    assert p_on.attack_speed == p_off.attack_speed
    assert on.total_dps(p_on, DUMMY) - off.total_dps(p_off, DUMMY) == pytest.approx(p_on.attack_speed * 60.0)


def test_draven_w_attack_speed_scales_with_uptime(spells, settings):
    """9 級 W2：Temp_AS[2] = 25%，乘達瑞文攻速係數 0.679 → 1 + 0.25 × 0.679。"""
    full = model_for(bound(spells, settings, "Draven", w_uptime=1.0)).profile(TOY, 9, [])
    none = model_for(bound(spells, settings, "Draven", w_uptime=0.0)).profile(TOY, 9, [])
    assert full.attack_speed == pytest.approx(1.0 + 0.25 * 0.679, abs=1e-4)
    assert none.attack_speed == pytest.approx(1.0)


def test_draven_window_damage_counts_e_and_both_r_passes(spells, settings):
    """5 級：E1 75（冷卻 18 → 1 次）；6 級再加 R1 (200 + 1.1 × 0) × 2 = 400。"""
    model = model_for(bound(spells, settings, "Draven"))
    assert model.profile(TOY, 5, []).modifiers.spell_window_physical == pytest.approx(75.0)
    assert model.profile(TOY, 6, []).modifiers.spell_window_physical == pytest.approx(475.0)


def test_spellblade_procs_follow_real_casts_within_the_window(spells, settings, items):
    """9 級＋三相（加速 15）：Q 冷卻 8→6.96 施放 2、W 1、E 1、R 1 = 5 次；
    觸發率 min(5, 10 ÷ 1.5) ÷ 10 = 0.5 → 每秒 0.5 × 基礎 AD × 2 = 100。"""
    kit = bound(spells, settings, "Draven")
    effects = ItemEffectBinder(Diagnostics()).bind(items.values())
    with_fx, without_fx = model_for(kit, effects), model_for(kit)
    build = [items[3078]]
    delta = with_fx.total_dps(with_fx.profile(TOY, 9, build), DUMMY) - without_fx.total_dps(
        without_fx.profile(TOY, 9, build), DUMMY
    )
    assert delta == pytest.approx(100.0)


# ---- 凱爾（§6.2）----

def test_kayle_becomes_ranged_at_level_6(spells, settings, items):
    kit = bound(spells, settings, "Kayle")
    assert not kit.is_ranged(5, MELEE_TOY) and kit.is_ranged(6, MELEE_TOY)
    effects = ItemEffectBinder(Diagnostics()).bind(items.values())
    model = model_for(kit, effects)
    melee = model.profile(MELEE_TOY, 5, [items[3153]]).modifiers.on_hit_current_hp_ratio
    ranged = model.profile(MELEE_TOY, 6, [items[3153]]).modifiers.on_hit_current_hp_ratio
    assert (melee, ranged) == (pytest.approx(0.09 * 0.5), pytest.approx(0.06 * 0.5))


def test_kayle_passive_attack_speed_stacks_from_level_1(spells, settings):
    """玩具基礎攻速 1.0 但凱爾係數 0.667 → 1 + 0.30 × 0.667。"""
    profile = model_for(bound(spells, settings, "Kayle")).profile(TOY, 1, [])
    assert profile.attack_speed == pytest.approx(1.0 + 0.30 * 0.667, abs=1e-3)


REAL_KAYLE_AS = replace(TOY, attack_speed=0.625)
PLUS_100_AS = Item(item_id=990002, name="玩具攻速", total_gold=3000, sell_gold=2100,
                   stats=(StatLine(StatKey.ATTACK_SPEED, 100.0),), tags=(), icon="", recipe=())


def test_kayle_attack_speed_uses_her_ratio_not_her_base(spells, settings):
    """凱爾實值：0.625 + (100% 裝備 + 30% 被動) × 0.667 = 1.492（舊公式會得 1.4375）。"""
    profile = model_for(bound(spells, settings, "Kayle")).profile(REAL_KAYLE_AS, 1, [PLUS_100_AS])
    assert profile.attack_speed == pytest.approx(0.625 + 1.30 * 0.667, abs=1e-3)


def test_champion_without_a_kit_keeps_the_old_formula(spells, settings):
    """無技能模型的英雄係數 = 基礎攻速 —— 與舊公式完全等價。"""
    plain = CombatModel(NO_SPELL, FIGHT, {}).profile(REAL_KAYLE_AS, 1, [PLUS_100_AS])
    assert plain.attack_speed == pytest.approx(0.625 * (1 + 1.0))


def test_draven_ratio_equals_his_base_attack_speed(spells, settings):
    """達瑞文係數 0.679 = 他的基礎攻速 → 與舊公式 base × (1 + 加成) 等價。

    要驗等價就必須用他真實的基礎攻速（玩具的 1.0 與係數不相稱）。"""
    real_draven_as = replace(TOY, attack_speed=0.679)
    kit = bound(spells, settings, "Draven", w_uptime=0.0, q_empowered_attack_ratio=0.0)
    profile = model_for(kit).profile(real_draven_as, 1, [PLUS_100_AS])
    assert profile.attack_speed == pytest.approx(0.679 * 2)


def test_kayle_waves_start_at_level_11(spells, settings):
    model = model_for(bound(spells, settings, "Kayle"))
    assert model.profile(TOY, 10, []).modifiers.magic_per_attack == 0.0
    assert model.profile(TOY, 11, []).modifiers.magic_per_attack == pytest.approx(20.0)


def test_kayle_e_active_hits_missing_health(spells, settings):
    """9 級 E5：(10 + 0) × 1%，冷卻 6 → 2 次；× 已損生命比 0.5 → 0.1。"""
    m = model_for(bound(spells, settings, "Kayle")).profile(TOY, 9, []).modifiers
    assert m.spell_window_missing_hp_magic_ratio == pytest.approx(0.1)


def test_kayle_q_shred_is_weighted_by_uptime(spells, settings):
    """9 級 Q2：冷卻 11 → 1 次 × 4 秒 ÷ 10 = 0.4；15% × 0.4 = 6% 雙抗。"""
    m = model_for(bound(spells, settings, "Kayle")).profile(TOY, 9, []).modifiers
    assert (m.armor_shred, m.magic_shred) == (pytest.approx(0.06), pytest.approx(0.06))


# ---- 煞蜜拉（§6.3）----

def test_samira_window_damage_without_crit(spells, settings):
    """6 級 Q3 W1 E1 R1：
    Q (10 + 1.1 × 100) = 120 × 3 次（冷卻 4）= 360；W 20 × 2 段 × 1 次 = 40；
    R (20 + 0.3 × 100) = 50 × 10 發 × 2 次（1 + (10−3)//(3+2)）= 1000。"""
    m = model_for(bound(spells, settings, "Samira")).profile(TOY, 6, []).modifiers
    assert m.spell_window_physical == pytest.approx(1400.0)
    assert m.spell_window_magic == pytest.approx(50.0)   # E 50 + 0.2 × 額外 AD 0


def test_samira_crit_expectation_q_half_r_full(spells, settings):
    """暴擊 100%、暴傷倍率 1.75：Q × 1.375、R × 1.75 → 495 + 40 + 1750 = 2285。"""
    m = model_for(bound(spells, settings, "Samira")).profile(TOY, 6, [FULL_CRIT]).modifiers
    assert m.spell_window_physical == pytest.approx(2285.0)


def test_samira_r_needs_the_combo_to_fit_the_window(spells, settings):
    m = model_for(bound(spells, settings, "Samira", combo_seconds=11.0)).profile(TOY, 6, []).modifiers
    assert m.spell_window_physical == pytest.approx(400.0)


def test_samira_e_attack_speed_weighted_by_uptime(spells, settings):
    """E1 BonusAttackSpeed[1] = 0.2 × 持續率 (1 次 × 5 秒 ÷ 10) = +10%，
    乘煞蜜拉攻速係數 0.658 → 1 + 0.10 × 0.658。"""
    profile = model_for(bound(spells, settings, "Samira")).profile(TOY, 6, [])
    assert profile.attack_speed == pytest.approx(1.0 + 0.10 * 0.658, abs=1e-4)


def test_samira_melee_passive_scales_with_the_melee_ratio(spells, settings):
    """6 級：(2 + 1 × 5) + (3.5% + 7% × 5/17) × AD 100，× 近戰比例 0.6。"""
    expected = 0.6 * (7.0 + (0.035 + 0.07 * 5 / 17) * 100.0)
    m = model_for(bound(spells, settings, "Samira")).profile(TOY, 6, []).modifiers
    assert m.magic_per_attack == pytest.approx(expected, rel=1e-6)
