"""裝備被動（spec 2026-09-15 §5、§8）。

真裝備（16.15.1 fixture，含 data values 與公式樹）× 玩具英雄：
AD 100、攻速 1.0、生命 1000、雙抗 0、成長 0、遠程 550；基準技能傷 0。
被動的貢獻一律以「同一組裝備、有效果 − 無效果」隔離，不依賴裝備屬性的實際數值。
"""

from dataclasses import replace
from pathlib import Path

import pytest

from lolcp.domain.combat import CombatModel, FightAssumptions, SpellProxy, TargetProfile
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import ChampionBaseStats
from lolcp.domain.item_effects import (
    EFFECTS,
    EffectCategory,
    ItemEffectBinder,
    flurry_uptime,
    passive_status,
)
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.file_item_repository import FileItemRepository

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"

RANGED = ChampionBaseStats(
    attack_damage=100.0, attack_damage_growth=0.0,
    attack_speed=1.0, attack_speed_growth=0.0,
    hp=1000.0, hp_growth=0.0,
    armor=0.0, armor_growth=0.0,
    magic_resist=0.0, magic_resist_growth=0.0,
    attack_range=550.0,
)
MELEE = replace(RANGED, attack_range=175.0)
DUMMY = TargetProfile("dummy", "木樁", armor=0.0, magic_resist=0.0, hp=2000.0, bonus_hp=0.0)
FIGHT = FightAssumptions(average_current_hp_ratio=0.5, energized_attacks=4)
NO_SPELL = SpellProxy(base_damage=0.0, ap_ratio=0.0, base_cooldown=8.0)

SPEC_IDS = {
    3053, 2501, 4633, 3032, 3089,              # 屬性轉換
    3153, 6672, 3115, 3091, 3302, 3124,        # 命中特效
    3097, 3094, 3087, 6699,                    # 充能普攻
    3071, 3036, 6676,                          # 削弱目標
    3078, 6662, 3100, 2510,                    # 魔法彎刀
}


@pytest.fixture(scope="module")
def items():
    repo = FileItemRepository(FIXTURES, ItemMapper(Diagnostics()))
    return {i.item_id: i for i in repo.all_items()}


@pytest.fixture(scope="module")
def effects(items):
    return ItemEffectBinder(Diagnostics()).bind(tuple(items.values()))


def with_effects(effects, proxy=NO_SPELL):
    return CombatModel(proxy, FIGHT, effects)


def without_effects(proxy=NO_SPELL):
    return CombatModel(proxy)


def dps(model, ids, items, base=RANGED, target=DUMMY, level=18):
    build = [items[i] for i in ids]
    return model.total_dps(model.profile(base, level, build), target)


def passive_delta(effects, ids, items, **kw):
    return dps(with_effects(effects), ids, items, **kw) - dps(without_effects(), ids, items, **kw)


# ---- 註冊表與綁定 ----

def test_registry_matches_the_spec_list():
    assert set(EFFECTS) == SPEC_IDS


def test_every_registered_effect_binds_on_real_data():
    """改版警報：綁定名稱在 fixture 上零缺漏。"""
    diagnostics = Diagnostics()
    repo = FileItemRepository(FIXTURES, ItemMapper(diagnostics))
    bound = ItemEffectBinder(diagnostics).bind(repo.all_items())
    assert set(bound) == SPEC_IDS
    assert diagnostics.unbound_item_effects == {}


def test_missing_data_value_disables_the_effect_and_is_recorded(items):
    botrk = items[3153]
    broken = replace(botrk, data_values=tuple(p for p in botrk.data_values if p[0] != "RangedValue"))
    diagnostics = Diagnostics()
    bound = ItemEffectBinder(diagnostics).bind((broken,))
    assert 3153 not in bound
    assert diagnostics.unbound_item_effects == {3153: ("data value RangedValue",)}


def plain_dps(ids, items, target=DUMMY, base=RANGED, level=18):
    """對照組：無效果模型自己產生的 profile（profile 內帶有被動修飾量，不可混用）。"""
    return dps(without_effects(), ids, items, base=base, target=target, level=level)


def test_passive_status_distinguishes_modelled_unbound_and_unmodelled(effects):
    """詳情面板的三種狀態（spec §6）—— 「沒建模」與「綁定失敗」是不同的事。"""
    unbound = {6672: ("calculation DamageAmount",)}
    bound = {k: v for k, v in effects.items() if k != 6672}

    botrk = passive_status(3153, bound, unbound)
    assert botrk.category is EffectCategory.ON_HIT and botrk.modelled

    kraken = passive_status(6672, bound, unbound)
    assert kraken.category is EffectCategory.ON_HIT and not kraken.modelled
    assert kraken.missing == ("calculation DamageAmount",)

    ie = passive_status(3031, bound, unbound)
    assert ie.category is None and not ie.modelled


def test_duplicate_items_apply_the_passive_once(effects, items):
    model = with_effects(effects)
    single = model.profile(RANGED, 18, [items[3089]])
    double = model.profile(RANGED, 18, [items[3089], items[3089]])
    # 死亡之帽屬性疊兩次（出裝列允許重複），被動 ×1.3 只乘一次
    assert double.ap == pytest.approx(single.ap * 2)


# ---- 屬性轉換（§5.1）----

def test_steraks_bonus_ad_reads_the_patch_value(effects, items):
    """16.15.1 ADtoAD = 0.45（16.16.1 為 0.5 —— 寫死常數就會錯）。"""
    plain = without_effects().profile(RANGED, 18, [items[3053]])
    model = with_effects(effects).profile(RANGED, 18, [items[3053]])
    assert model.attack_damage - plain.attack_damage == pytest.approx(100.0 * 0.45)


def test_rabadon_multiplies_after_riftmaker_conversion(effects, items):
    plain = without_effects().profile(RANGED, 18, [items[4633], items[3089]])
    bonus_hp = plain.hp - RANGED.hp
    expected = (plain.ap + 0.02 * bonus_hp) * 1.3
    for order in ([4633, 3089], [3089, 4633]):
        profile = with_effects(effects).profile(RANGED, 18, [items[i] for i in order])
        assert profile.ap == pytest.approx(expected)


def test_overlords_converts_bonus_hp_to_ad(effects, items):
    plain = without_effects().profile(RANGED, 18, [items[2501]])
    model = with_effects(effects).profile(RANGED, 18, [items[2501]])
    assert model.attack_damage - plain.attack_damage == pytest.approx(0.025 * (plain.hp - RANGED.hp))


def test_yun_tal_adds_stacked_crit(effects, items):
    plain = without_effects().profile(RANGED, 18, [items[3032]])
    model = with_effects(effects).profile(RANGED, 18, [items[3032]])
    assert model.crit_chance - plain.crit_chance == pytest.approx(25.0)


# ---- 雲陶狂箭 Flurry 持續率（spec 2026-09-16 §3.3）----

def test_flurry_uptime_is_hand_computable():
    """攻速 2.0、暴擊 50%：每秒減冷卻 2.0 × (1 + 0.5) = 3 秒 →
    就緒 30 ÷ 4 = 7.5 秒 → 持續率 6 ÷ 7.5 = 0.8。"""
    assert flurry_uptime(cooldown=30.0, duration=6.0, per_attack=1.0, per_crit=2.0,
                         attack_speed=2.0, crit_chance=0.5) == pytest.approx(0.8)


def test_flurry_uptime_caps_at_one():
    assert flurry_uptime(cooldown=30.0, duration=6.0, per_attack=1.0, per_crit=2.0,
                         attack_speed=10.0, crit_chance=1.0) == 1.0


def test_flurry_uptime_without_attacks_is_duration_over_cooldown():
    assert flurry_uptime(cooldown=30.0, duration=6.0, per_attack=1.0, per_crit=2.0,
                         attack_speed=0.0, crit_chance=0.0) == pytest.approx(0.2)


def test_yun_tal_attack_speed_is_weighted_by_flurry_uptime(effects, items):
    """雲陶狂箭自身 45% 攻速、被動 25% 暴擊 → 估算攻速 1.45、暴擊 25%：
    每秒減冷卻 1.45 × 1.25 = 1.8125 → 就緒 30 ÷ 2.8125 ≈ 10.67 →
    持續率 ≈ 0.5625 → 攻速加成 30% × 0.5625 = 16.875 個百分點。"""
    uptime = flurry_uptime(cooldown=30.0, duration=6.0, per_attack=1.0, per_crit=2.0,
                           attack_speed=1.45, crit_chance=0.25)
    profile = with_effects(effects).profile(RANGED, 18, [items[3032]])
    assert profile.attack_speed == pytest.approx(1.45 + 0.30 * uptime)
    assert uptime < 1.0  # 不再是常駐


def test_yun_tal_unbinds_without_the_cooldown_values(items):
    """四個數值全部讀自 bin —— 缺任一個即停用並留痕。"""
    yun_tal = items[3032]
    broken = replace(yun_tal, data_values=tuple(p for p in yun_tal.data_values if p[0] != "AACDR"))
    diagnostics = Diagnostics()
    bound = ItemEffectBinder(diagnostics).bind((broken,))
    assert 3032 not in bound
    assert diagnostics.unbound_item_effects == {3032: ("data value AACDR",)}


def test_riftmaker_amplifies_all_damage(effects, items):
    """基準技能傷 0 → AP 轉換不影響輸出，比值只剩 8% 增傷。"""
    assert dps(with_effects(effects), [4633], items) / plain_dps([4633], items) == pytest.approx(1.08)


# ---- 命中特效（§5.2）----

def test_botrk_hits_average_current_health(effects, items):
    """遠程 6% × (2000 × 0.5) = 每下 60 物理。"""
    profile = with_effects(effects).profile(RANGED, 18, [items[3153]])
    assert passive_delta(effects, [3153], items) == pytest.approx(profile.attack_speed * 60.0)


def test_botrk_uses_the_melee_value_for_melee(effects, items):
    profile = with_effects(effects).profile(MELEE, 18, [items[3153]])
    assert passive_delta(effects, [3153], items, base=MELEE) == pytest.approx(profile.attack_speed * 90.0)


def test_kraken_every_third_attack_amplified_by_missing_health(effects, items):
    """遠程 18 級：160 × (1 + 0.75 × 0.5) ÷ 3 ≈ 73.33。"""
    profile = with_effects(effects).profile(RANGED, 18, [items[6672]])
    assert passive_delta(effects, [6672], items) == pytest.approx(profile.attack_speed * 160 * 1.375 / 3)


def test_guinsoo_stacks_attack_speed_and_multiplies_on_hits(effects, items):
    """鬼索攻速 +32%；納什之牙 + 鬼索的命中特效 × 4/3。"""
    plain = without_effects().profile(RANGED, 18, [items[3124], items[3115]])
    model = with_effects(effects)
    profile = model.profile(RANGED, 18, [items[3124], items[3115]])
    assert profile.attack_speed - plain.attack_speed == pytest.approx(0.32)
    nashor = 15.0 + 0.15 * profile.ap
    expected = profile.attack_speed * (profile.attack_damage + (30.0 + nashor) * 4 / 3)
    assert model.total_dps(profile, DUMMY) == pytest.approx(expected)


def test_wits_end_is_flat_magic_on_hit(effects, items):
    profile = with_effects(effects).profile(RANGED, 18, [items[3091]])
    assert passive_delta(effects, [3091], items) == pytest.approx(profile.attack_speed * 45.0)


def test_terminus_penetrates_both_resistances(effects, items):
    target = TargetProfile("wall", "牆", armor=100.0, magic_resist=100.0, hp=2000.0)
    model = with_effects(effects)
    profile = model.profile(RANGED, 18, [items[3302]])
    on_hit = 30.0 + 0.1 * (profile.attack_damage - RANGED.attack_damage) + 0.1 * profile.ap
    expected = profile.attack_speed * (profile.attack_damage + on_hit) * 100 / 170  # 100 × 0.7 = 70
    assert model.total_dps(profile, target) == pytest.approx(expected)


def test_terminus_adds_resistances_for_ehp(effects, items):
    plain = without_effects().profile(RANGED, 14, [items[3302]])
    model = with_effects(effects).profile(RANGED, 14, [items[3302]])
    assert model.armor - plain.armor == pytest.approx(24.0)
    assert model.magic_resist - plain.magic_resist == pytest.approx(24.0)


# ---- 充能普攻（§5.3）----

def test_stormrazor_energized_damage_is_spread_per_attack(effects, items):
    """每 4 下 100 魔法 → 每下 25。"""
    profile = with_effects(effects).profile(RANGED, 18, [items[3097]])
    assert passive_delta(effects, [3097], items) == pytest.approx(profile.attack_speed * 25.0)


def test_energized_items_stack_on_the_same_proc(effects, items):
    profile = with_effects(effects).profile(RANGED, 18, [items[3097], items[3094]])
    assert passive_delta(effects, [3097, 3094], items) == pytest.approx(profile.attack_speed * 140 / 4)


def test_voltaic_uses_percentage_points_of_current_health(effects, items):
    """PercentCurrentHPRanged = 7（百分點）→ 7% × 1000 ÷ 4 = 17.5。"""
    profile = with_effects(effects).profile(RANGED, 18, [items[6699]])
    assert passive_delta(effects, [6699], items) == pytest.approx(profile.attack_speed * 17.5)


# ---- 削弱目標（§5.4）----

def test_black_cleaver_shreds_armor_before_penetration(effects, items):
    target = TargetProfile("tank", "坦克", armor=200.0, magic_resist=0.0, hp=4000.0)
    model = with_effects(effects)
    profile = model.profile(RANGED, 18, [items[3071]])
    expected = profile.attack_speed * profile.attack_damage * 100 / 240  # 200 × 0.7 = 140
    assert model.total_dps(profile, target) == pytest.approx(expected)


def test_dominik_scales_with_target_bonus_health(effects, items):
    model = with_effects(effects)
    for bonus, amp in ((2000.0, 1.15), (300.0, 1.03), (0.0, 1.0)):
        target = replace(DUMMY, bonus_hp=bonus)
        ratio = dps(model, [3036], items, target=target) / plain_dps([3036], items, target=target)
        assert ratio == pytest.approx(amp)


def test_collector_execute_shortens_the_kill(effects, items):
    ratio = dps(with_effects(effects), [6676], items) / plain_dps([6676], items)
    assert ratio == pytest.approx(1 / 0.95)


# ---- 魔法彎刀（§5.5）----

def test_trinity_spellblade_procs_once_per_cast(effects, items):
    """基準技能冷卻 8 ÷ (1 + 三相 15 加速) → 觸發率 1.15/8；傷害 基礎 AD × 2 = 200。"""
    profile = with_effects(effects).profile(RANGED, 18, [items[3078]])
    rate = (1 + profile.ability_haste / 100) / 8.0
    assert passive_delta(effects, [3078], items) == pytest.approx(200.0 * rate)


def test_spellblade_rate_is_floored_by_its_cooldown(effects, items):
    fast = SpellProxy(base_damage=0.0, ap_ratio=0.0, base_cooldown=1.0)
    with_fx = with_effects(effects, proxy=fast)
    no_fx = without_effects(proxy=fast)
    build = [items[3078]]
    delta = with_fx.total_dps(with_fx.profile(RANGED, 18, build), DUMMY) - no_fx.total_dps(
        no_fx.profile(RANGED, 18, build), DUMMY
    )
    assert delta == pytest.approx(200.0 / 1.5)


def test_lich_bane_spellblade_is_magic(effects, items):
    target = TargetProfile("mr", "魔抗牆", armor=0.0, magic_resist=100.0, hp=2000.0)
    model = with_effects(effects)
    profile = model.profile(RANGED, 18, [items[3100]])
    rate = (1 + profile.ability_haste / 100) / 8.0
    damage = 0.75 * 100.0 + 0.45 * profile.ap
    delta = model.total_dps(profile, target) - plain_dps([3100], items, target=target)
    assert delta == pytest.approx(damage * rate * 0.5)
