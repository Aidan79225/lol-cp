"""AppCoordinator 的視窗生命週期。

視窗只建立一次並重用 —— 原始計畫的 main() 每收到一次 finished
就再開一個視窗，按一次「檢查更新」畫面上就多一個視窗。
"""

import pathlib

import pytest

from lolcp.application.use_cases.sync_game_data import SyncResult
from lolcp.main import build_application, build_use_cases
from lolcp.presentation.app_coordinator import AppCoordinator

pytestmark = pytest.mark.usefixtures("qapp")

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"


class FakeThread:
    def __init__(self):
        self.start_calls = 0
        self.quit_calls = 0

    def start(self):
        self.start_calls += 1

    def quit(self):
        self.quit_calls += 1


class FakeApp:
    def __init__(self):
        self.quit_calls = 0

    def quit(self):
        self.quit_calls += 1


@pytest.fixture
def coordinator(tmp_path):
    cache_root = tmp_path / "cache"
    for version in ("16.15.1", "16.16.1"):  # 第二個版本給版本切換測試用
        (cache_root / version).mkdir(parents=True)
        for f in (FIXTURES / "16.15.1").iterdir():
            (cache_root / version / f.name).write_bytes(f.read_bytes())
        (cache_root / version / ".complete").write_text("", encoding="utf-8")

    context = build_application(cache_root=cache_root)
    return AppCoordinator(
        build=lambda version: build_use_cases(context, version),
        diagnostics=context.diagnostics,
        thread=FakeThread(),
        app=FakeApp(),
    )


def result(version="16.15.1", offline=False, downloaded=False) -> SyncResult:
    return SyncResult(version=version, offline=offline, downloaded=downloaded)


def test_first_finished_creates_the_window(coordinator):
    assert coordinator.window is None
    coordinator.on_finished(result())
    assert coordinator.window is not None
    assert coordinator.window._model.rowCount() > 0
    assert coordinator._thread.quit_calls == 1


def test_second_finished_reuses_the_window(coordinator):
    """回歸鎖：原始計畫每次 finished 都會再開一個新視窗。"""
    coordinator.on_finished(result())
    first = coordinator.window
    coordinator.on_finished(result(downloaded=False))
    assert coordinator.window is first


def test_progress_before_window_exists_does_not_crash(coordinator):
    coordinator.on_progress(50, 100)  # 首次同步時視窗還不存在
    assert coordinator.window is None


def test_progress_drives_the_window_progress_bar(coordinator):
    coordinator.on_finished(result())
    coordinator.on_progress(50, 100)
    assert coordinator.window._progress.isVisibleTo(coordinator.window)
    assert coordinator.window._progress.value() == 50


def test_refresh_click_restarts_the_thread(coordinator):
    coordinator.on_finished(result())
    coordinator._on_refresh_clicked()
    assert coordinator._thread.start_calls == 1


def test_failure_without_a_window_quits_the_app(coordinator, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    coordinator.on_failed("無快取")
    assert coordinator._app.quit_calls == 1


def test_failure_with_a_live_window_keeps_the_app_running(coordinator, monkeypatch):
    """更新失敗時不可把使用者正在看的視窗整個關掉。"""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    coordinator.on_finished(result())
    coordinator.on_failed("網路中斷")
    assert coordinator._app.quit_calls == 0


def test_version_change_on_refresh_rebuilds_use_cases(coordinator):
    """檢查更新帶回新版本時，set_use_cases 以 UseCaseBundle 重建注入 —— 這行
    只在版本切換時執行，沒測試的話 bundle 形狀不符只會在真實改版時爆。"""
    coordinator.on_finished(result("16.15.1"))
    first = coordinator.window._list_valuations
    coordinator.on_finished(result("16.16.1"))
    assert coordinator.window._list_valuations is not first
    assert coordinator.window._model.rowCount() > 0
