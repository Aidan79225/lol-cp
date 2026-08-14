import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import KNOWN_ROLES, RoleDefaults, StatWeights


def test_uniform_gives_every_stat_the_same_weight():
    w = StatWeights.uniform(1.0)
    assert w.of(StatKey.AD) == 1.0
    assert w.of(StatKey.TENACITY) == 1.0


def test_undefined_stat_defaults_to_one_not_zero():
    """0 會隱藏資訊，1 只是多算一個邊緣屬性。兩者代價不對稱。"""
    w = StatWeights({StatKey.AD: 0.5})
    assert w.of(StatKey.AD) == 0.5
    assert w.of(StatKey.CRIT_DAMAGE) == 1.0


def test_masked_stats_lists_only_explicit_zeros():
    w = StatWeights({StatKey.AD: 1.0, StatKey.AP: 0.0, StatKey.HP: 0.4})
    assert w.masked_stats == frozenset({StatKey.AP})


def test_union_max_takes_the_larger_of_each_pair():
    mage = StatWeights({StatKey.AD: 0.0, StatKey.AP: 1.0, StatKey.ATTACK_SPEED: 0.1})
    marksman = StatWeights({StatKey.AD: 1.0, StatKey.AP: 0.0, StatKey.ATTACK_SPEED: 1.0})
    merged = mage.union_max(marksman)
    assert merged.of(StatKey.AD) == 1.0
    assert merged.of(StatKey.AP) == 1.0
    assert merged.of(StatKey.ATTACK_SPEED) == 1.0


def test_union_max_is_not_mean():
    """若誤用平均，混合傷害英雄的 AD 與 AP 都會掉到 0.5。"""
    a = StatWeights({StatKey.AP: 1.0})
    b = StatWeights({StatKey.AP: 0.0})
    assert a.union_max(b).of(StatKey.AP) == 1.0


def test_merged_with_overrides_replaces_values():
    base = StatWeights({StatKey.AD: 1.0, StatKey.ARMOR_PEN_PERCENT: 0.8})
    merged = base.merged_with({StatKey.ARMOR_PEN_PERCENT: 0.4})
    assert merged.of(StatKey.ARMOR_PEN_PERCENT) == 0.4
    assert merged.of(StatKey.AD) == 1.0


def test_with_stat_returns_a_new_instance():
    base = StatWeights({StatKey.MANA: 0.9})
    changed = base.with_stat(StatKey.MANA, 0.0)
    assert changed.of(StatKey.MANA) == 0.0
    assert base.of(StatKey.MANA) == 0.9  # 原物件不變


def test_known_roles_are_the_six_data_dragon_tags():
    assert KNOWN_ROLES == ("Assassin", "Fighter", "Mage", "Marksman", "Support", "Tank")


def test_role_defaults_union_over_multiple_tags():
    defaults = RoleDefaults({
        "Mage": StatWeights({StatKey.AD: 0.0, StatKey.AP: 1.0}),
        "Marksman": StatWeights({StatKey.AD: 1.0, StatKey.AP: 0.0}),
    })
    merged = defaults.union_max(("Mage", "Marksman"), Diagnostics())
    assert merged.of(StatKey.AD) == 1.0
    assert merged.of(StatKey.AP) == 1.0


def test_role_defaults_single_tag_needs_no_union():
    defaults = RoleDefaults({"Marksman": StatWeights({StatKey.AP: 0.0})})
    merged = defaults.union_max(("Marksman",), Diagnostics())
    assert merged.of(StatKey.AP) == 0.0


def test_unknown_tag_is_recorded_and_skipped():
    diagnostics = Diagnostics()
    defaults = RoleDefaults({"Marksman": StatWeights({StatKey.AP: 0.0})})
    merged = defaults.union_max(("Marksman", "Juggernaut"), diagnostics)
    assert merged.of(StatKey.AP) == 0.0
    assert diagnostics.unknown_roles == ("Juggernaut",)


def test_no_tags_yields_uniform_weights_not_all_zero():
    """沒有 tag 的英雄不該讓所有裝備歸零。"""
    merged = RoleDefaults({}).union_max((), Diagnostics())
    assert merged.of(StatKey.AD) == 1.0
    assert merged.of(StatKey.AP) == 1.0
