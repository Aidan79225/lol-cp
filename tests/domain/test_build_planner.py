"""出裝規劃器（spec 2026-09-14 §3–§5）。

玩具英雄：護甲／魔抗／成長皆 0、基準技能傷 0 → DPS = AD × 攻速、
EHP = 生命。所有期望值皆可手算。
"""

from itertools import permutations

import pytest

from lolcp.domain.build_planner import (
    BuildPlanner,
    PlannerSettings,
    is_boots,
    is_legendary,
)
from lolcp.domain.combat import CombatModel, SpellProxy, TargetProfile
from lolcp.domain.entities import ChampionBaseStats, GroupLimit, Item
from lolcp.domain.stats import StatKey, StatLine

TOY_BASE = ChampionBaseStats(
    attack_damage=100.0, attack_damage_growth=0.0,
    attack_speed=1.0, attack_speed_growth=0.0,
    hp=1000.0, hp_growth=0.0,
    armor=0.0, armor_growth=0.0,
    magic_resist=0.0, magic_resist_growth=0.0,
)
DUMMY = TargetProfile(key="dummy", name="木樁", armor=0.0, magic_resist=0.0, hp=1000.0)
BOOTS_GROUP = (GroupLimit("Boots", 1),)
LEVELS = (9, 11, 13, 15, 16, 18)


def planner() -> BuildPlanner:
    return BuildPlanner(CombatModel(SpellProxy(base_damage=0.0, ap_ratio=0.0, base_cooldown=8.0)))


def settings(beta=0.0, boots_slot=0, beam_width=8, final=3000.0,
             alternative_tolerance=0.03, max_alternatives=3) -> PlannerSettings:
    # 窄 beam：玩具池多為同質件；boots_slot=0 時第 2 階段每集合窮舉 720 種排列
    return PlannerSettings(
        levels=LEVELS, final_holding_gold=final, beta=beta,
        boots_slot=boots_slot, beam_width=beam_width,
        alternative_tolerance=alternative_tolerance, max_alternatives=max_alternatives,
    )


def item(item_id, gold, *stats, epicness=5, upgrades=(), groups=()) -> Item:
    return Item(item_id=item_id, name=f"item{item_id}", total_gold=gold,
                sell_gold=gold // 2, stats=stats, tags=(), icon="", recipe=(),
                epicness=epicness, upgrades=upgrades, group_limits=groups)


def boots(item_id, gold=1100, attack_speed=0.0) -> Item:
    stats = (StatLine(StatKey.ATTACK_SPEED, attack_speed),) if attack_speed else ()
    return item(item_id, gold, *stats, epicness=4, groups=BOOTS_GROUP)


def ad(n):
    return StatLine(StatKey.AD, n)


def asp(n):
    return StatLine(StatKey.ATTACK_SPEED, n)


def hp(n):
    return StatLine(StatKey.HP, n)


def ids(plan):
    return tuple(s.item.item_id for s in plan.steps)


# ---- 候選池判準（spec §4.1）----

def test_legendary_judgement():
    assert is_legendary(item(1, 3000, ad(50)))
    assert not is_legendary(item(2, 400, ad(5)))                  # 任務裝價位
    assert not is_legendary(item(3, 2250, ad(5), upgrades=(9,)))  # 會升級
    assert not is_legendary(item(4, 3000, ad(50), epicness=4))
    assert not is_legendary(item(5, 3000, ad(50), epicness=None))


def test_boots_judgement():
    assert is_boots(boots(10))
    assert not is_boots(item(11, 1300, ad(40), epicness=4))       # 暴風之劍：史詩部件
    assert not is_legendary(boots(10))


# ---- 評分（spec §3）----

def test_sequence_value_is_hand_computable():
    """A=+50AD/2000g、B=+100AD/3000g、final=3000：
    (A,B) = 150×3000 + 250×3000 = 1,200,000
    (B,A) = 200×2000 + 250×3000 = 1,150,000
    便宜又強的先買，其戰力被加權更久 —— 順序有意義的原因。"""
    a, b = item(1, 2000, ad(50)), item(2, 3000, ad(100))
    p, s = planner(), settings()
    assert p.sequence_value(TOY_BASE, DUMMY, (a, b), s) == pytest.approx(1_200_000)
    assert p.sequence_value(TOY_BASE, DUMMY, (b, a), s) == pytest.approx(1_150_000)


def test_beta_zero_scores_pure_dps():
    tank_item = item(1, 3000, hp(1000))
    plan = planner().plan(TOY_BASE, DUMMY, [], [tank_item], settings(beta=0.0))
    assert plan.steps[0].score == pytest.approx(100.0)   # DPS = 100 × 1.0


def test_beta_weights_ehp_ratio_against_naked():
    """EHP 2000 / 裸裝 1000 = 2；β=0.5 → score = 100 × √2。"""
    tank_item = item(1, 3000, hp(1000))
    plan = planner().plan(TOY_BASE, DUMMY, [], [tank_item], settings(beta=0.5))
    step = plan.steps[0]
    assert (step.dps, step.ehp) == (pytest.approx(100.0), pytest.approx(2000.0))
    assert step.score == pytest.approx(100.0 * 2 ** 0.5)


def test_higher_beta_buys_more_ehp():
    pool = [item(i, 3000, ad(60)) for i in range(1, 7)] + [
        item(i, 3000, ad(40), hp(800)) for i in range(7, 13)
    ]
    greedy = planner().plan(TOY_BASE, DUMMY, pool, [], settings(beta=0.0))
    tanky = planner().plan(TOY_BASE, DUMMY, pool, [], settings(beta=1.0))
    assert tanky.steps[-1].ehp > greedy.steps[-1].ehp


# ---- 限制（spec §4.2）----

def test_group_cap_prevents_two_members():
    whisper = (GroupLimit("LastWhisper", 1),)
    pool = [item(1, 3000, ad(90), groups=whisper), item(2, 3000, ad(80), groups=whisper)]
    pool += [item(i, 3000, ad(10)) for i in range(3, 9)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [], settings())
    assert not {1, 2} <= set(ids(plan))
    assert 1 in ids(plan)


def test_group_cap_of_two_allows_two_members():
    pair = (GroupLimit("Pair", 2),)
    pool = [item(1, 3000, ad(90), groups=pair), item(2, 3000, ad(80), groups=pair)]
    pool += [item(i, 3000, ad(10)) for i in range(3, 9)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [], settings())
    assert {1, 2} <= set(ids(plan))


def test_no_duplicates_and_six_slots():
    pool = [item(i, 3000, ad(50 + i)) for i in range(1, 10)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [], settings())
    assert len(plan.steps) == 6
    assert len(set(ids(plan))) == 6


def test_exactly_one_boots_at_the_configured_slot():
    """鞋幾乎沒戰力 —— 放任搜尋會排到最後；鞋位固定在第 2 件。"""
    pool = [item(i, 3000, ad(50)) for i in range(1, 8)] + [boots(20), boots(21)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [], settings(boots_slot=2))
    flags = [is_boots(s.item) for s in plan.steps]
    assert flags == [False, True, False, False, False, False]


def test_boots_slot_zero_means_no_boots():
    pool = [item(i, 3000, ad(50)) for i in range(1, 8)] + [boots(20, attack_speed=90.0)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [], settings(boots_slot=0))
    assert not any(is_boots(s.item) for s in plan.steps)


def test_boots_rule_is_skipped_when_pool_has_no_boots():
    pool = [item(i, 3000, ad(50)) for i in range(1, 8)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [], settings(boots_slot=2))
    assert len(plan.steps) == 6


# ---- 已購前綴（spec §4.3）----

def test_prefix_keeps_order_and_components_are_skipped():
    l1, l2 = item(1, 3000, ad(10)), item(2, 3000, ad(20))
    component = item(99, 600, StatLine(StatKey.CRIT_CHANCE, 15.0), epicness=None)
    pool = [l1, l2] + [item(i, 3000, ad(50)) for i in range(3, 9)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [component, l2, l1], settings())
    assert ids(plan)[:2] == (2, 1)
    assert plan.skipped == (component,)


def test_prefix_already_holding_boots_satisfies_the_rule_anywhere():
    b = boots(20)
    pool = [b] + [item(i, 3000, ad(50)) for i in range(1, 8)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [item(1, 3000, ad(50)), item(2, 3000, ad(50)), b],
                          settings(boots_slot=2))
    assert [is_boots(s.item) for s in plan.steps].count(True) == 1


def test_prefix_past_the_boots_slot_puts_boots_next():
    pool = [item(i, 3000, ad(50)) for i in range(1, 8)] + [boots(20)]
    prefix = [pool[0], pool[1], pool[2]]
    plan = planner().plan(TOY_BASE, DUMMY, pool, prefix, settings(boots_slot=2))
    assert is_boots(plan.steps[3].item)


def test_full_prefix_is_scored_without_search():
    six = [item(i, 3000, ad(10)) for i in range(1, 7)]
    s = settings()
    plan = planner().plan(TOY_BASE, DUMMY, [], six, s)
    assert ids(plan) == (1, 2, 3, 4, 5, 6)
    assert plan.value == pytest.approx(planner().sequence_value(TOY_BASE, DUMMY, tuple(six), s))


# ---- 搜尋（spec §5）----

def _brute_force_best(pool_legend, pool_boots, s, groups_ok):
    p = planner()
    best = float("-inf")
    for b in pool_boots:
        for perm in permutations(pool_legend, 5):
            seq = (perm[0], b, *perm[1:])
            if groups_ok(seq):
                best = max(best, p.sequence_value(TOY_BASE, DUMMY, seq, s))
    return best


def test_search_matches_brute_force_on_a_small_pool():
    """集合數 ≤ beam 寬度時兩階段搜尋必為全域最佳 —— 以窮舉 5040 條序列驗證。
    攻速 × AD 的乘法協同讓順序與組合都非平凡。"""
    whisper = (GroupLimit("LastWhisper", 1),)
    legend = [
        item(1, 3000, ad(70)),
        item(2, 2600, asp(40)),
        item(3, 3300, ad(40), asp(30)),
        item(4, 3100, ad(55), groups=whisper),
        item(5, 3000, ad(60), groups=whisper),
        item(6, 2800, ad(20), asp(35)),
        item(7, 3400, ad(80), hp(300)),
    ]
    shoes = [boots(20, 1100, attack_speed=30.0), boots(21, 1000)]
    s = settings(beta=0.25, boots_slot=2, beam_width=1000)

    def groups_ok(seq):
        return sum(1 for i in seq if i.item_id in (4, 5)) <= 1

    plan = planner().plan(TOY_BASE, DUMMY, legend + shoes, [], s)
    assert plan.value == pytest.approx(_brute_force_best(legend, shoes, s, groups_ok))
    assert plan.value == pytest.approx(
        planner().sequence_value(TOY_BASE, DUMMY, tuple(st.item for st in plan.steps), s)
    )


# ---- 接近的替代選項（spec 2026-09-16 near-tie §3、§6）----
#
# β=0、雙抗 0、基礎 AD 100、攻速 1.0 → 第 1 步分數 = 100 + 該件 AD。
# AD 100／98／96／94／90 對應比例 1.00／0.99／0.98／0.97／0.95。

def tie_pool():
    strong = [item(i, 3000, ad(amount)) for i, amount in
              ((1, 100.0), (2, 98.0), (3, 96.0), (4, 94.0), (5, 90.0))]
    filler = [item(i, 3000, ad(10.0)) for i in range(6, 10)]
    return strong + filler


def alt_ids(step):
    return [a.item.item_id for a in step.alternatives]


def test_alternatives_are_within_the_tolerance_and_sorted():
    plan = planner().plan(TOY_BASE, DUMMY, tie_pool(), [], settings())
    first = plan.steps[0]
    assert first.item.item_id == 1
    assert alt_ids(first) == [2, 3, 4]          # 0.99／0.98／0.97 入列，0.95 不入列
    assert [round(a.score_ratio, 4) for a in first.alternatives] == [0.99, 0.98, 0.97]


def test_tighter_tolerance_drops_the_further_ones():
    plan = planner().plan(TOY_BASE, DUMMY, tie_pool(), [], settings(alternative_tolerance=0.02))
    assert alt_ids(plan.steps[0]) == [2, 3]


def test_alternatives_are_capped():
    plan = planner().plan(TOY_BASE, DUMMY, tie_pool(), [], settings(max_alternatives=1))
    assert alt_ids(plan.steps[0]) == [2]


def test_alternatives_never_include_the_chosen_item():
    plan = planner().plan(TOY_BASE, DUMMY, tie_pool(), [], settings())
    for step in plan.steps:
        assert step.item.item_id not in alt_ids(step)


def test_alternatives_respect_group_caps_from_the_prefix():
    """前綴已有同群組的件 → 另一件不可列為替代（買了也吃不到）。"""
    whisper = (GroupLimit("LastWhisper", 1),)
    chosen = item(1, 3000, ad(100.0), groups=whisper)
    sibling = item(2, 3000, ad(99.0), groups=whisper)
    pool = [chosen, sibling] + [item(i, 3000, ad(98.0)) for i in range(3, 10)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [chosen], settings())
    assert plan.steps[0].item.item_id == 1
    assert 2 not in alt_ids(plan.steps[1])


def test_alternatives_respect_the_boots_slot():
    pool = [item(i, 3000, ad(50.0)) for i in range(1, 8)] + [boots(20), boots(21)]
    plan = planner().plan(TOY_BASE, DUMMY, pool, [], settings(boots_slot=2))
    assert all(is_boots(a.item) for a in plan.steps[1].alternatives)      # 鞋位只列鞋
    assert not any(is_boots(a.item) for a in plan.steps[2].alternatives)  # 其餘位置不列鞋


def test_plan_is_deterministic():
    pool = [item(i, 3000, ad(50)) for i in range(1, 10)] + [boots(20), boots(21)]
    s = settings(beta=0.25, boots_slot=2)
    assert planner().plan(TOY_BASE, DUMMY, pool, [], s) == planner().plan(TOY_BASE, DUMMY, pool, [], s)


def test_settings_require_six_levels():
    with pytest.raises(ValueError):
        PlannerSettings(levels=(9, 11), final_holding_gold=3000.0, beta=0.25,
                        boots_slot=2, beam_width=40)
