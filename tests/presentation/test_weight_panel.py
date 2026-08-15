import pytest

from lolcp.domain.entities import Champion
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import StatWeights
from lolcp.presentation.widgets.weight_panel import WeightPanel

pytestmark = pytest.mark.usefixtures("qapp")

DRAVEN = Champion("Draven", 119, "達瑞文", ("Marksman",), "Mana")


def defaults() -> StatWeights:
    return StatWeights({StatKey.AD: 1.0, StatKey.AP: 0.0, StatKey.MANA: 0.4})


def test_sliders_reflect_defaults_and_overrides():
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {StatKey.AP: 0.5})
    assert panel._sliders[StatKey.AD].value() == 20  # 1.0 / 0.05
    assert panel._sliders[StatKey.AP].value() == 10  # 覆寫 0.5
    assert panel._values[StatKey.AP].text() == "0.50"
    assert panel._names[StatKey.AP].font().bold() is True
    assert panel._names[StatKey.AD].font().bold() is False


def test_global_view_disables_everything():
    panel = WeightPanel()
    panel.set_context(None, None, {})
    assert not panel._sliders[StatKey.AD].isEnabled()
    assert panel._values[StatKey.AD].text() == "—"


def test_release_emits_the_slider_value():
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {})
    seen: list[tuple[object, float]] = []
    panel.weight_committed.connect(lambda s, v: seen.append((s, v)))
    panel._sliders[StatKey.AP].setValue(13)
    panel._sliders[StatKey.AP].sliderReleased.emit()
    assert seen == [(StatKey.AP, pytest.approx(0.65))]


def test_reset_emits_the_default_value():
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {StatKey.AP: 0.5})
    seen: list[tuple[object, float]] = []
    panel.weight_committed.connect(lambda s, v: seen.append((s, v)))
    panel._on_reset(StatKey.AP)
    assert seen == [(StatKey.AP, 0.0)]


def test_reset_all_emits_for_every_override():
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {StatKey.AP: 0.5, StatKey.MANA: 0.9})
    seen: list[object] = []
    panel.weight_committed.connect(lambda s, v: seen.append(s))
    panel._on_reset_all()
    assert set(seen) == {StatKey.AP, StatKey.MANA}


def test_panel_lists_only_sr_stats():
    """25 個 StatKey 中只有 21 個出現在召喚峽谷裝備 —— 其餘 4 個
    是死拉桿（調了也不影響任何價格），不該出現。"""
    from lolcp.domain.stats import SR_STATS

    panel = WeightPanel()
    assert set(panel._sliders) == set(SR_STATS)


def test_keyboard_value_change_commits_without_release():
    """鍵盤方向鍵／PageUp 改值不會發 sliderReleased，也必須提交。"""
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {})
    seen: list[tuple[object, float]] = []
    panel.weight_committed.connect(lambda s, v: seen.append((s, v)))
    panel._sliders[StatKey.AP].setValue(7)  # 程式化改值 = 非拖曳路徑
    assert seen == [(StatKey.AP, pytest.approx(0.35))]


def test_click_without_move_does_not_overwrite_hand_edited_value():
    """手調 0.87 不是 0.05 的倍數；只按一下不拖動不可把它改寫成 0.85。"""
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {StatKey.AP: 0.87})
    seen: list[tuple[object, float]] = []
    panel.weight_committed.connect(lambda s, v: seen.append((s, v)))
    panel._sliders[StatKey.AP].sliderReleased.emit()  # 點擊未移動
    assert seen == []
    assert panel._values[StatKey.AP].text() == "0.87"
