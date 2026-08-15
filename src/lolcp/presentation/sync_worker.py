"""把 SyncGameData 的普通回呼轉成 Qt signal，並在 worker thread 執行。

這個 adapter 存在的唯一理由就是分層：SyncGameData 不認識 Qt，
15.8 MB 的下載又不能阻塞 UI 執行緒。轉換只發生在這裡。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from lolcp.application.use_cases.sync_game_data import SyncGameData


class SyncWorker(QObject):
    progress = Signal(int, int)      # 已下載, 總計
    finished = Signal(object)        # SyncResult
    failed = Signal(str)

    def __init__(self, sync: SyncGameData, parent=None) -> None:
        super().__init__(parent)
        self._sync = sync

    @Slot()
    def run(self) -> None:
        """在 worker thread 執行。絕不拋出 —— 失敗以 failed signal 回報。"""
        try:
            result = self._sync.execute(self._emit_progress)
        except Exception as exc:  # noqa: BLE001 — worker 邊界必須吞掉所有例外
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)

    def _emit_progress(self, done: int, total: int) -> None:
        self.progress.emit(done, total)
