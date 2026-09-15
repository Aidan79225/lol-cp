"""技能等級推算（spec champion-kits §4）。"""

import pytest

from lolcp.domain.skill_ranks import skill_ranks

DRAVEN = ("Q", "W", "E")


def test_first_three_levels_learn_each_basic_in_order():
    assert skill_ranks(1, DRAVEN) == {"Q": 1, "W": 0, "E": 0, "R": 0}
    assert skill_ranks(3, DRAVEN) == {"Q": 1, "W": 1, "E": 1, "R": 0}


def test_max_order_respects_the_half_level_cap():
    """達瑞文 Q>W>E：Q 在 1/4/5/7/9 級，9 級滿 —— 主流加點。"""
    assert skill_ranks(5, DRAVEN)["Q"] == 3
    assert skill_ranks(8, DRAVEN) == {"Q": 4, "W": 2, "E": 1, "R": 1}
    assert skill_ranks(9, DRAVEN)["Q"] == 5


def test_ultimate_ranks_at_6_11_16():
    assert [skill_ranks(lv, DRAVEN)["R"] for lv in (5, 6, 10, 11, 15, 16, 18)] == [0, 1, 1, 2, 2, 3, 3]


def test_level_18_maxes_everything():
    assert skill_ranks(18, DRAVEN) == {"Q": 5, "W": 5, "E": 5, "R": 3}


def test_kayle_order_maxes_e_first():
    ranks = skill_ranks(9, ("E", "Q", "W"))
    assert ranks["E"] == 5 and ranks["Q"] == 2 and ranks["W"] == 1


@pytest.mark.parametrize("order", [("Q", "W", "E"), ("E", "Q", "W"), ("Q", "E", "W")])
def test_invariants_hold_at_every_level(order):
    for level in range(1, 19):
        ranks = skill_ranks(level, order)
        assert sum(ranks.values()) == level
        assert all(ranks[s] <= min(5, (level + 1) // 2) for s in ("Q", "W", "E"))
        assert ranks["R"] <= 3


def test_skill_order_must_be_a_permutation_of_basics():
    for bad in (("Q", "Q", "E"), ("Q", "W"), ("Q", "W", "R")):
        with pytest.raises(ValueError, match="skill_order"):
            skill_ranks(5, bad)


def test_level_must_be_within_1_and_18():
    with pytest.raises(ValueError):
        skill_ranks(0, DRAVEN)
    with pytest.raises(ValueError):
        skill_ranks(19, DRAVEN)
