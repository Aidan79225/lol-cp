import pytest

from lolcp.domain.entities import Champion, Item
from lolcp.domain.stats import StatKey, StatLine


def make_item(**kw) -> Item:
    defaults = dict(
        item_id=3031,
        name="無盡之刃",
        total_gold=3500,
        sell_gold=2450,
        stats=(StatLine(StatKey.AD, 75.0), StatLine(StatKey.CRIT_CHANCE, 25.0)),
        tags=("CriticalStrike", "Damage"),
        icon="3031.png",
        recipe=(1038, 1037, 1018),
    )
    return Item(**{**defaults, **kw})


def test_amount_of_returns_normalized_amount():
    item = make_item()
    assert item.amount_of(StatKey.AD) == 75.0
    assert item.amount_of(StatKey.CRIT_CHANCE) == 25.0


def test_amount_of_returns_none_for_absent_stat():
    assert make_item().amount_of(StatKey.AP) is None


def test_amount_of_distinguishes_absent_from_zero():
    """0.0 與 None 是不同的事：有這屬性但值為 0，vs 沒有這屬性。"""
    item = make_item(stats=(StatLine(StatKey.AP, 0.0),))
    assert item.amount_of(StatKey.AP) == 0.0
    assert item.amount_of(StatKey.AD) is None


def test_stat_keys():
    assert make_item().stat_keys == frozenset({StatKey.AD, StatKey.CRIT_CHANCE})


def test_item_is_frozen():
    with pytest.raises(AttributeError):
        make_item().total_gold = 1  # type: ignore[misc]


def test_champion_uses_mana():
    draven = Champion(key="Draven", numeric_id=119, name="達瑞文",
                      tags=("Marksman",), partype="Mana")
    assert draven.uses_mana is True
    assert draven.partype_unknown is False


def test_champion_with_non_mana_resource_does_not_use_mana():
    """犽宿的資源是 Flow，法力裝備對他無用。mp>0 不代表吃法力。"""
    yasuo = Champion(key="Yasuo", numeric_id=157, name="犽宿",
                     tags=("Fighter", "Assassin"), partype="Flow")
    assert yasuo.uses_mana is False


def test_champion_with_empty_partype_is_flagged_unknown_not_manaless():
    """空 partype 視為未知，不可當成無法力（隱藏資訊比多算屬性糟）。"""
    weird = Champion(key="Weird", numeric_id=1, name="?", tags=("Mage",), partype="")
    assert weird.partype_unknown is True
    assert weird.uses_mana is False
