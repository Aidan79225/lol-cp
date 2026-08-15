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
    list_valuations, champions, adjust = build_use_cases(context, "16.15.1")
    w = MainWindow(list_valuations, champions, context.diagnostics, adjust)
    w.reload()
    return w, config_dir


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
    w, config_dir = window
    select_champion(w, "達瑞文")
    assert zhonya_ratio(w) == pytest.approx(0.092, abs=0.001)

    w._on_weight_committed(StatKey.AP, 0.5)

    assert zhonya_ratio(w) > 0.3  # 105 法強從全遮罩變 0.5 權重
    text = (config_dir / "champions" / "Draven.toml").read_text(encoding="utf-8")
    assert "ap = 0.5" in text


def test_weight_commit_back_to_default_removes_the_entry(window):
    w, config_dir = window
    select_champion(w, "達瑞文")
    w._on_weight_committed(StatKey.AP, 0.5)
    w._on_weight_committed(StatKey.AP, 0.0)  # Marksman 的 AP 基準 = 0.0
    text = (config_dir / "champions" / "Draven.toml").read_text(encoding="utf-8")
    assert "ap =" not in text
    assert zhonya_ratio(w) == pytest.approx(0.092, abs=0.001)


def test_weight_panel_follows_profile_switching(window):
    w, _ = window
    select_champion(w, "達瑞文")
    assert w._weight_panel._sliders[StatKey.AD].isEnabled()
    select_champion(w, "全域")
    assert not w._weight_panel._sliders[StatKey.AD].isEnabled()
