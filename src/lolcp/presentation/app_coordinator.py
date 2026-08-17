"""組裝根與 Qt 主執行緒之間的協調者。

worker signal 的 slot 必須掛在活在主執行緒的 QObject 上：
plain closure 直接 connect 會在發訊號的 worker thread 執行，
視窗就會在非 GUI 執行緒被建立 —— Qt 未定義行為，macOS 上
通常直接崩潰。bound method 的接收者是本物件，Qt 的 Auto
connection 才會把呼叫 queue 回主執行緒。

視窗只建立一次並重用；「檢查更新」帶回新版本時重建 use case
注入既有視窗，而非再開一個視窗。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox

from lolcp.domain.diagnostics import Diagnostics
from lolcp.presentation.main_window import MainWindow


class AppCoordinator(QObject):
    def __init__(
        self,
        build,   # version -> UseCaseBundle
        diagnostics: Diagnostics,
        thread,   # QThread；只用到 start/quit
        app,      # QApplication；只用到 quit
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._build = build
        self._diagnostics = diagnostics
        self._thread = thread
        self._app = app
        self._window: MainWindow | None = None
        self._version: str | None = None

    @property
    def window(self) -> MainWindow | None:
        return self._window

    @Slot(object)
    def on_finished(self, result) -> None:
        if self._window is None:
            self._window = MainWindow(self._build(result.version), self._diagnostics)
            self._window.refresh_button.clicked.connect(self._on_refresh_clicked)
            self._window.show()
        elif result.version != self._version:
            self._window.set_use_cases(self._build(result.version))
        self._version = result.version
        self._window.on_sync_finished(result)
        self._thread.quit()

    @Slot(int, int)
    def on_progress(self, done: int, total: int) -> None:
        if self._window is not None:
            self._window.on_sync_progress(done, total)

    @Slot(str)
    def on_failed(self, message: str) -> None:
        QMessageBox.critical(self._window, "無法載入資料", message)
        self._thread.quit()
        if self._window is None:
            self._app.quit()  # 首次啟動就失敗，沒有視窗可以退回

    def _on_refresh_clicked(self) -> None:
        self._thread.start()
