import pytest

from lolcp.application.use_cases.sync_game_data import SyncResult
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion, Item
from lolcp.domain.pricing import PriceTable
from lolcp.domain.stats import StatKey, StatLine
from lolcp.domain.valuation import ItemComparison, LinearValuation
from lolcp.domain.weights import StatWeights
from lolcp.presentation.widgets.detail_panel import DetailPanel
from lolcp.presentation.widgets.filter_bar import FilterBar
from lolcp.presentation.widgets.profile_selector import ProfileSelector
from lolcp.presentation.widgets.status_bar import StatusBarWidget

pytestmark = pytest.mark.usefixtures("qapp")

DRAVEN = Champion("Draven", 119, "達瑞文", ("Marksman",), "Mana")
KAYLE = Champion("Kayle", 10, "凱爾", ("Mage", "Marksman"), "Mana")


def zhonyas() -> Item:
    return Item(item_id=3157, name="中婭沙漏", total_gold=3250, sell_gold=2275,
                stats=(StatLine(StatKey.AP, 105.0), StatLine(StatKey.ARMOR, 50.0)),
                tags=("SpellDamage", "Armor"), icon="", recipe=())


def evaluate(item, weights, prices):
    return LinearValuation().evaluate(item, PriceTable(prices, frozenset()), weights)


# ---- DetailPanel ----

def test_detail_lines_mark_masked_stats():
    result = evaluate(
        zhonyas(),
        StatWeights({StatKey.AP: 0.0, StatKey.ARMOR: 0.3}),
        {StatKey.AP: 20.0, StatKey.ARMOR: 20.0},
    )
    text = "\n".join(DetailPanel.render_lines(result))
    assert "遮罩" in text
    assert "105" in text and "×0.0" in text


def test_detail_lines_mark_unpriced_stats():
    item = Item(item_id=3031, name="無盡之刃", total_gold=3500, sell_gold=2450,
                stats=(StatLine(StatKey.AD, 75.0), StatLine(StatKey.CRIT_DAMAGE, 30.0)),
                tags=(), icon="", recipe=())
    result = evaluate(item, StatWeights.uniform(),
                      {StatKey.AD: 35.0, StatKey.CRIT_DAMAGE: None})
    text = "\n".join(DetailPanel.render_lines(result))
    assert "未定價" in text


def test_positive_residual_is_described_as_passive_value():
    result = evaluate(zhonyas(), StatWeights.uniform(),
                      {StatKey.AP: 20.0, StatKey.ARMOR: 20.0})
    text = "\n".join(DetailPanel.render_lines(result))
    assert "被動" in text


def test_negative_residual_is_not_called_passive_value():
    """負殘差代表屬性本身超值，稱作「被動價值」是錯的。

    道具名不可含「超值」二字 —— 否則斷言會被標題列白白滿足。"""
    cheap = Item(item_id=1, name="多蘭之刃", total_gold=1000, sell_gold=500,
                 stats=(StatLine(StatKey.AD, 50.0),), tags=(), icon="", recipe=())
    result = evaluate(cheap, StatWeights.uniform(), {StatKey.AD: 35.0})
    text = "\n".join(DetailPanel.render_lines(result))
    assert "被動" not in text
    assert "屬性本身已超值" in text


def test_detail_panel_accepts_none_without_crashing():
    panel = DetailPanel()
    panel.show_comparison(None)
    assert panel is not None


# ---- ProfileSelector ----

def test_profile_selector_starts_on_global_view():
    selector = ProfileSelector()
    selector.set_champions([DRAVEN, KAYLE])
    assert selector.current_champion() is None


def test_profile_selector_lists_global_plus_champions():
    selector = ProfileSelector()
    selector.set_champions([DRAVEN, KAYLE])
    labels = [selector.itemText(i) for i in range(selector.count())]
    assert labels[0] == "全域"
    assert "達瑞文" in labels and "凱爾" in labels


def test_profile_selector_emits_on_change():
    selector = ProfileSelector()
    selector.set_champions([DRAVEN, KAYLE])
    received: list[object] = []
    selector.profile_changed.connect(received.append)
    selector.setCurrentIndex(1)
    assert received and received[-1] is DRAVEN


# ---- FilterBar ----

def make_comparison(item: Item) -> ItemComparison:
    weights = StatWeights.uniform()
    prices = PriceTable({StatKey.AP: 20.0, StatKey.ARMOR: 20.0, StatKey.AD: 35.0},
                        frozenset())
    v = LinearValuation()
    return ItemComparison.of(v.evaluate(item, prices, weights),
                             v.evaluate(item, prices, weights))


def test_filter_bar_matches_everything_by_default():
    bar = FilterBar()
    bar.set_tags(["SpellDamage", "Armor"])
    assert bar.matches(make_comparison(zhonyas())) is True


def test_filter_bar_filters_by_tag():
    bar = FilterBar()
    bar.set_tags(["SpellDamage", "Damage"])
    bar.select_tag("Damage")
    assert bar.matches(make_comparison(zhonyas())) is False
    bar.select_tag("SpellDamage")
    assert bar.matches(make_comparison(zhonyas())) is True


def test_filter_bar_emits_on_tag_change():
    bar = FilterBar()
    bar.set_tags(["SpellDamage"])
    fired: list[int] = []
    bar.filter_changed.connect(lambda: fired.append(1))
    bar.select_tag("SpellDamage")
    assert fired


# ---- StatusBarWidget ----

def test_status_bar_shows_version_and_clean_diagnostics():
    widget = StatusBarWidget()
    widget.update_status(
        SyncResult(version="16.15.1", offline=False, downloaded=False), Diagnostics()
    )
    assert "16.15.1" in widget.text()
    assert "無異常" in widget.text()


def test_status_bar_flags_offline():
    widget = StatusBarWidget()
    widget.update_status(
        SyncResult(version="16.15.1", offline=True, downloaded=False), Diagnostics()
    )
    assert "離線" in widget.text()


def test_status_bar_surfaces_diagnostics():
    diagnostics = Diagnostics()
    diagnostics.unknown_bin_field("mNewMod", 3031)
    diagnostics.filtered_variant(323003)
    widget = StatusBarWidget()
    widget.update_status(
        SyncResult(version="16.15.1", offline=False, downloaded=True), diagnostics
    )
    assert "未知屬性欄位" in widget.text()
    assert "過濾變體" in widget.text()
