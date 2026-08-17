import pytest

from lolcp.domain.entities import Item
from lolcp.domain.stats import StatKey, StatLine
from lolcp.presentation.widgets.build_bar import BuildBar

pytestmark = pytest.mark.usefixtures("qapp")


def item(item_id: int, name: str = "x") -> Item:
    return Item(item_id=item_id, name=name, total_gold=1000, sell_gold=500,
                stats=(StatLine(StatKey.AD, 10.0),), tags=(), icon="", recipe=())


def test_add_and_remove_items():
    bar = BuildBar()
    fired: list[int] = []
    bar.build_changed.connect(lambda: fired.append(1))
    bar.add_item(item(1, "劍"))
    bar.add_item(item(2, "斧"))
    assert bar.build_ids == (1, 2)
    bar._remove(bar._buttons[0])
    assert bar.build_ids == (2,)
    assert len(fired) == 3


def test_six_slot_cap():
    bar = BuildBar()
    for i in range(8):
        bar.add_item(item(i))
    assert len(bar.build_ids) == 6


def test_duplicates_are_allowed():
    """疊同件是使用者的判斷（如雙多蘭）。"""
    bar = BuildBar()
    bar.add_item(item(1055))
    bar.add_item(item(1055))
    assert bar.build_ids == (1055, 1055)


def test_clear_resets_and_emits_once():
    bar = BuildBar()
    bar.add_item(item(1))
    fired: list[int] = []
    bar.build_changed.connect(lambda: fired.append(1))
    bar.clear()
    bar.clear()  # 空的再清不發訊號
    assert bar.build_ids == ()
    assert len(fired) == 1


def test_level_defaults_to_11_and_emits_on_change():
    bar = BuildBar()
    assert bar.level == 11
    seen: list[int] = []
    bar.level_changed.connect(seen.append)
    bar._level_spin.setValue(18)
    assert bar.level == 18
    assert seen == [18]
