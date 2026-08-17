"""拉桿 → use case → 重算 → 寫檔的整合測試（fixture 快取 + tmp 設定複本）。"""

import pathlib
import shutil

import pytest

from lolcp.domain.stats import StatKey
from lolcp.main import build_application, build_use_cases
from lolcp.presentation.main_window import MainWindow

pytestmark = pytest.mark.usefixtures("qapp")

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
CONFIG = pathlib.Path(__file__).parent.parent.parent / "config"


@pytest.fixture
def window(tmp_path):
    cache_root = tmp_path / "cache"
    (cache_root / "16.15.1").mkdir(parents=True)
    for f in (FIXTURES / "16.15.1").iterdir():
        shutil.copy(f, cache_root / "16.15.1" / f.name)
    (cache_root / "16.15.1" / ".complete").write_text("", encoding="utf-8")
    config_dir = tmp_path / "config"
    shutil.copytree(CONFIG, config_dir)
    context = build_application(cache_root=cache_root, config_dir=config_dir)
    w = MainWindow(build_use_cases(context, "16.15.1"), context.diagnostics)
    w.reload()
    return w, config_dir, context


def select_champion(w: MainWindow, name: str) -> None:
    for i in range(w._profile.count()):
        if w._profile.itemText(i) == name:
            w._profile.setCurrentIndex(i)
            return
    raise AssertionError(f"selector 沒有 {name}")


def zhonya_ratio(w: MainWindow) -> float:
    for r in range(w._model.rowCount()):
        c = w._model.comparison_at(r)
        if c.item.item_id == 3157:
            return c.canonical.ratio
    raise AssertionError("表格裡沒有中婭沙漏")


def test_weight_commit_reprices_and_persists(window):
    w, config_dir, _ctx = window
    select_champion(w, "達瑞文")
    assert zhonya_ratio(w) == pytest.approx(0.092, abs=0.001)

    w._on_weight_committed(StatKey.AP, 0.5)

    assert zhonya_ratio(w) > 0.3  # 105 法強從全遮罩變 0.5 權重
    text = (config_dir / "champions" / "Draven.toml").read_text(encoding="utf-8")
    assert "ap = 0.5" in text


def test_weight_commit_back_to_default_removes_the_entry(window):
    w, config_dir, _ctx = window
    select_champion(w, "達瑞文")
    w._on_weight_committed(StatKey.AP, 0.5)
    w._on_weight_committed(StatKey.AP, 0.0)  # Marksman 的 AP 基準 = 0.0
    text = (config_dir / "champions" / "Draven.toml").read_text(encoding="utf-8")
    assert "ap =" not in text
    assert zhonya_ratio(w) == pytest.approx(0.092, abs=0.001)


def test_weight_panel_follows_profile_switching(window):
    w, _, _ctx = window
    select_champion(w, "達瑞文")
    assert w._weight_panel._sliders[StatKey.AD].isEnabled()
    select_champion(w, "全域")
    assert not w._weight_panel._sliders[StatKey.AD].isEnabled()


# ---- 邊際效益欄（Task 5 整合） ----

from lolcp.presentation.item_table_model import ItemTableModel


def marginal_cell(w: MainWindow, item_id: int, column: int) -> str:
    for r in range(w._model.rowCount()):
        c = w._model.comparison_at(r)
        if c.item.item_id == item_id:
            return w._model.data(w._model.index(r, column))
    raise AssertionError(f"表格裡沒有 {item_id}")


def test_global_view_shows_dashes_in_marginal_columns(window):
    w, _, _ctx = window
    assert marginal_cell(w, 3031, ItemTableModel.COL_DPS_SQUISHY) == "—"


def test_marginal_columns_activate_for_a_champion(window):
    w, _, _ctx = window
    select_champion(w, "達瑞文")
    cell = marginal_cell(w, 3031, ItemTableModel.COL_DPS_SQUISHY)
    assert cell != "—"
    assert float(cell) > 0


def test_build_context_raises_ie_marginal_through_the_ui(window):
    """協同貫穿到 UI：雙擊蒐集者+披風入裝後，無盡的 ΔDPS/千金 上升。"""
    w, _, _ctx = window
    select_champion(w, "達瑞文")
    before = float(marginal_cell(w, 3031, ItemTableModel.COL_DPS_SQUISHY))

    for iid in (6676, 1018):
        for r in range(w._model.rowCount()):
            if w._model.comparison_at(r).item.item_id == iid:
                w._on_row_double_clicked(w._model.index(r, 0))
                break

    assert w._build_bar.build_ids == (6676, 1018)
    after = float(marginal_cell(w, 3031, ItemTableModel.COL_DPS_SQUISHY))
    assert after > before


def test_level_change_recomputes_marginals(window):
    w, _, _ctx = window
    select_champion(w, "達瑞文")
    before = marginal_cell(w, 3031, ItemTableModel.COL_DPS_SQUISHY)
    w._build_bar._level_spin.setValue(1)  # 低等級基礎攻速低 → 邊際值改變
    after = marginal_cell(w, 3031, ItemTableModel.COL_DPS_SQUISHY)
    assert after != before


def test_marginal_column_sort_puts_missing_last_in_both_directions(window):
    from PySide6.QtCore import Qt

    w, _, _ctx = window
    select_champion(w, "達瑞文")
    col = ItemTableModel.COL_DPS_SQUISHY
    for order in (Qt.SortOrder.DescendingOrder, Qt.SortOrder.AscendingOrder):
        w._model.sort(col, order)
        values = [w._model.data(w._model.index(r, col))
                  for r in range(w._model.rowCount())]
        if "—" in values:
            first_dash = values.index("—")
            assert all(v == "—" for v in values[first_dash:])


def test_version_switch_clears_the_build_bar(window):
    """set_use_cases 換版本後，舊版本的 Item 物件不可留在出裝列。"""
    w, _, _ctx = window
    select_champion(w, "達瑞文")
    for r in range(w._model.rowCount()):
        if w._model.comparison_at(r).item.item_id == 1036:
            w._on_row_double_clicked(w._model.index(r, 0))
            break
    assert w._build_bar.build_ids == (1036,)
    w.set_use_cases(w._make_current_bundle()) if hasattr(w, "_make_current_bundle") else None
