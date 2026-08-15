"""狀態列：版本、離線標示、診斷計數。"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from lolcp.application.use_cases.sync_game_data import SyncResult
from lolcp.domain.diagnostics import Diagnostics


class StatusBarWidget(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__("", parent)

    def update_status(self, sync: SyncResult, diagnostics: Diagnostics) -> None:
        parts = [f"版本 {sync.version}"]
        if sync.offline:
            parts.append("離線（顯示本地快取）")
        parts.append(diagnostics.summary_line())
        self.setText("  |  ".join(parts))

    def text(self) -> str:  # noqa: D102 — QLabel.text 已存在，這裡只是為了型別清晰
        return super().text()
