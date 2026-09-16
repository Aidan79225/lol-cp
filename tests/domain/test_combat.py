"""CombatModel 的手算黃金值（spec 2026-08-17 §3／§8）。"""

import pytest

from lolcp.domain.combat import (
    AS_CAP,
    CombatModel,
    SpellProxy,
    TargetProfile,
    growth_factor,
)
from lolcp.domain.entities import ChampionBaseStats, Item
from lolcp.domain.stats import StatKey, StatLine

DRAVEN_BASE = ChampionBaseStats(
    attack_damage=62.0, attack_damage_growth=0.0,
    attack_speed=0.679, attack_speed_growth=2.7,
    hp=675.0, hp_growth=104.0,
    armor=29.0, armor_growth=4.5,
    magic_resist=30.0, magic_resist_growth=1.3,
)

SQUISHY = TargetProfile(key="squishy", name="脆皮", armor=60.0, magic_resist=50.0, hp=1800.0)
TANK = TargetProfile(key="tank", name="坦克", armor=200.0, magic_resist=120.0, hp=4000.0)

PROXY = SpellProxy(base_damage=300.0, ap_ratio=0.7, base_cooldown=8.0)


def item(item_id: int, gold: int, *stats: StatLine) -> Item:
    return Item(item_id=item_id, name=f"item{item_id}", total_gold=gold,
                sell_gold=gold // 2, stats=stats, tags=(), icon="", recipe=())


def model() -> CombatModel:
    return CombatModel(PROXY)


def spell_const(target: TargetProfile) -> float:
    """無 AP／魔穿／加速時的常數基準技能 DPS。"""
    return 300.0 * (100 / (100 + target.magic_resist)) / 8


def aa_dps(profile, target) -> float:
    """隔離普攻通道：總 DPS 扣掉常數基準技能（比值斷言用）。"""
    return model().total_dps(profile, target) - spell_const(target)


def test_growth_factor_is_riot_nonlinear_formula():
    """stat(lv) = base + growth × (lv−1) × (0.7025 + 0.0175×(lv−1))，非線性。"""
    assert growth_factor(1) == 0.0
    assert growth_factor(11) == pytest.approx(8.775)
    assert growth_factor(18) == pytest.approx(17.0)  # 17 × (0.7025 + 0.2975)


def test_draven_level_11_base_profile():
    profile = model().profile(DRAVEN_BASE, 11, [])
    assert profile.attack_damage == pytest.approx(62.0)      # 成長 0
    assert profile.attack_speed == pytest.approx(0.679 * 1.236925)
    assert profile.hp == pytest.approx(675 + 104 * 8.775)


def test_naked_draven_dps_is_auto_attack_plus_base_spell():
    """普攻 32.55 + 基準技能 300×(100/150)/8 = 25 —— 基準傷恆計入
    （代表每隻英雄都有的泛用技能循環），常數在邊際比較中抵銷。"""
    profile = model().profile(DRAVEN_BASE, 11, [])
    dps = model().total_dps(profile, SQUISHY)
    assert dps == pytest.approx(62 * 0.679 * 1.236925 * 0.625 + 25.0, rel=1e-6)


def test_crit_factor_multiplies_chance_and_damage():
    """25% 暴擊 + 30% 裝備暴傷：1 + 0.25 × (0.75 + 0.30) = 1.2625。"""
    weapons = [item(1, 1000, StatLine(StatKey.CRIT_CHANCE, 25.0),
                    StatLine(StatKey.CRIT_DAMAGE, 30.0))]
    profile = model().profile(DRAVEN_BASE, 11, weapons)
    base_profile = model().profile(DRAVEN_BASE, 11, [])
    ratio = aa_dps(profile, SQUISHY) / aa_dps(base_profile, SQUISHY)
    assert ratio == pytest.approx(1.2625)


def test_crit_chance_is_capped_at_100():
    weapons = [item(1, 1000, StatLine(StatKey.CRIT_CHANCE, 160.0))]
    profile = model().profile(DRAVEN_BASE, 11, weapons)
    base_profile = model().profile(DRAVEN_BASE, 11, [])
    ratio = aa_dps(profile, SQUISHY) / aa_dps(base_profile, SQUISHY)
    assert ratio == pytest.approx(1.75)  # 100% 暴擊 × 基礎暴傷 175%


def test_penetration_order_percent_before_flat():
    """Riot 規則：% 先算、穿甲後扣。200 甲、30% 物穿 + 10 穿甲 → 130。"""
    weapons = [item(1, 1000, StatLine(StatKey.ARMOR_PEN_PERCENT, 30.0),
                    StatLine(StatKey.ARMOR_PEN_FLAT, 10.0))]
    profile = model().profile(DRAVEN_BASE, 11, weapons)
    base_profile = model().profile(DRAVEN_BASE, 11, [])
    ratio = aa_dps(profile, TANK) / aa_dps(base_profile, TANK)
    assert ratio == pytest.approx(300 / 230)  # 100/(100+130) ÷ 100/(100+200)


def test_effective_armor_never_goes_negative():
    weapons = [item(1, 1000, StatLine(StatKey.ARMOR_PEN_FLAT, 999.0))]
    profile = model().profile(DRAVEN_BASE, 11, weapons)
    naked_ad = 62 * 0.679 * 1.236925
    assert aa_dps(profile, SQUISHY) == pytest.approx(naked_ad)  # 倍率封頂 1.0，不放大


def test_attack_speed_items_scale_the_base_ratio_and_cap():
    """裝備攻速是對攻速係數的百分比加成（無 kit 時係數 = 基礎攻速）；
    上限 3.003（維基：全單位唯一上限；舊值 2.5 是錯的，spec 2026-09-16 §3.2）。"""
    weapons = [item(1, 1000, StatLine(StatKey.ATTACK_SPEED, 50.0))]
    profile = model().profile(DRAVEN_BASE, 11, weapons)
    assert profile.attack_speed == pytest.approx(0.679 * (1 + 0.236925 + 0.5))
    silly = [item(1, 1000, StatLine(StatKey.ATTACK_SPEED, 900.0))]
    assert model().profile(DRAVEN_BASE, 11, silly).attack_speed == AS_CAP
    assert AS_CAP == 3.003


def test_ap_item_delta_is_only_its_scaling_share():
    """AP 100 的增量 = 0.7×100 × 100/150 ÷ 8 ≈ 5.83 —— 基準傷已在
    基線裡，AP 件不繼承它。"""
    weapons = [item(1, 1000, StatLine(StatKey.AP, 100.0))]
    profile = model().profile(DRAVEN_BASE, 11, weapons)
    base_profile = model().profile(DRAVEN_BASE, 11, [])
    delta = model().total_dps(profile, SQUISHY) - model().total_dps(base_profile, SQUISHY)
    assert delta == pytest.approx(70 * (100 / 150) / 8)


def test_ability_haste_100_doubles_the_whole_spell_channel():
    """加速 100 = 冷卻減半 = 整段法術 DPS（含基準傷）加倍。"""
    ap_only = [item(1, 1000, StatLine(StatKey.AP, 100.0))]
    hasted = [item(1, 1000, StatLine(StatKey.AP, 100.0),
                   StatLine(StatKey.ABILITY_HASTE, 100.0))]
    m = model()
    spell_full = (300 + 70) * (100 / 150) / 8   # 未加速的整段法術 DPS
    dps_ap = m.total_dps(m.profile(DRAVEN_BASE, 11, ap_only), SQUISHY)
    dps_hasted = m.total_dps(m.profile(DRAVEN_BASE, 11, hasted), SQUISHY)
    assert dps_hasted - dps_ap == pytest.approx(spell_full)  # 加倍 = 再加一整段


def test_mixed_ehp_is_the_average_of_both_defenses():
    profile = model().profile(DRAVEN_BASE, 11, [])
    hp = 675 + 104 * 8.775
    armor = 29 + 4.5 * 8.775
    mr = 30 + 1.3 * 8.775
    expected = (hp * (1 + armor / 100) + hp * (1 + mr / 100)) / 2
    assert model().mixed_ehp(profile) == pytest.approx(expected)


# ---- MarginalValuation ----

from lolcp.domain.combat import MarginalValuation


def marginal(build, candidates):
    return MarginalValuation(model(), (SQUISHY, TANK)).evaluate(
        DRAVEN_BASE, 11, build, candidates
    )


def test_long_sword_marginal_dps_is_hand_computable():
    """ΔDPS = 10 AD × AS × 護甲倍率；每千金 = Δ ÷ 350 × 1000。"""
    sword = item(1036, 350, StatLine(StatKey.AD, 10.0))
    (result,) = marginal([], [sword])
    expected = 10 * (0.679 * 1.236925) * 0.625 / 350 * 1000
    assert result.dps_per_1k["squishy"] == pytest.approx(expected)


def test_infinity_edge_synergy_with_crit_items():
    """線性模型永遠答不對的那件事：無盡的邊際值隨已有暴擊率上升。"""
    ie = item(3031, 3500, StatLine(StatKey.AD, 75.0),
              StatLine(StatKey.CRIT_CHANCE, 25.0), StatLine(StatKey.CRIT_DAMAGE, 30.0))
    crit_build = [
        item(6676, 3000, StatLine(StatKey.AD, 50.0), StatLine(StatKey.CRIT_CHANCE, 25.0)),
        item(1018, 600, StatLine(StatKey.CRIT_CHANCE, 15.0)),
    ]
    (alone,) = marginal([], [ie])
    (with_crit,) = marginal(crit_build, [ie])
    assert with_crit.dps_per_1k["squishy"] > alone.dps_per_1k["squishy"]


def test_percent_pen_is_worth_more_against_tanks_flat_pen_against_squishies():
    """模型自己教的一課：百分比物穿對坦克更值錢（60→42 差 0.079 倍率、
    200→140 差 0.083），穿甲（固定值）反而對低甲目標絕對增益更大
    （d/da 100/(100+a) 隨 a 遞減）—— 出裝常識「打坦克買 LDR、
    打脆皮買穿甲」的數學根源。"""
    percent_pen = item(9, 1000, StatLine(StatKey.ARMOR_PEN_PERCENT, 30.0))
    (pp,) = marginal([], [percent_pen])
    assert pp.dps_per_1k["tank"] > pp.dps_per_1k["squishy"] > 0

    flat_pen = item(8, 1000, StatLine(StatKey.ARMOR_PEN_FLAT, 10.0))
    (fp,) = marginal([], [flat_pen])
    assert fp.dps_per_1k["squishy"] > fp.dps_per_1k["tank"] > 0


def test_boots_are_outside_the_model_and_show_zero():
    """誠實邊界：移速不在公式裡，鞋子兩欄皆 0，不假裝算到。"""
    boots = item(1001, 300, StatLine(StatKey.MOVE_SPEED_FLAT, 25.0))
    (result,) = marginal([], [boots])
    assert result.dps_per_1k["squishy"] == 0.0
    assert result.ehp_per_1k == 0.0


def test_ruby_crystal_adds_ehp_but_no_dps():
    ruby = item(1028, 400, StatLine(StatKey.HP, 150.0))
    (result,) = marginal([], [ruby])
    assert result.dps_per_1k["squishy"] == 0.0
    assert result.ehp_per_1k > 0


def test_zero_gold_items_are_skipped():
    free = item(9, 0, StatLine(StatKey.AD, 10.0))
    assert marginal([], [free]) == ()



def test_cheap_ap_component_does_not_dominate_the_ranking():
    """回歸鎖：曾有 AP>0 閘門讓 435g 增幅典籍繼承整段基準傷（~60/千金）
    而霸榜。修正後它的 ΔDPS/千金 應低於長劍。"""
    tome = item(1052, 435, StatLine(StatKey.AP, 20.0))
    sword = item(1036, 350, StatLine(StatKey.AD, 10.0))
    tome_r, sword_r = marginal([], [tome, sword])
    assert tome_r.dps_per_1k["squishy"] < sword_r.dps_per_1k["squishy"]


def test_magic_pen_and_haste_act_on_the_base_spell():
    """魔穿與加速對 AD 英雄也有合理價值 —— 他們的技能也有基礎傷。"""
    haste = item(7, 1000, StatLine(StatKey.ABILITY_HASTE, 20.0))
    (result,) = marginal([], [haste])
    assert result.dps_per_1k["squishy"] > 0
