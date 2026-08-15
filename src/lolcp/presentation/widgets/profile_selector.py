"""英雄視角切換。第一項固定為「全域」（客觀 CP值）。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox

from lolcp.domain.entities import Champion

GLOBAL_LABEL = "全域"


class ProfileSelector(QComboBox):
    profile_changed = Signal(object)  # Champion | None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.currentIndexChanged.connect(self._on_index_changed)

    def set_champions(self, champions: Sequence[Champion]) -> None:
        self.blockSignals(True)
        self.clear()
        self.addItem(GLOBAL_LABEL, userData=None)
        for champion in champions:
            self.addItem(champion.name, userData=champion)
        self.setCurrentIndex(0)
        self.blockSignals(False)

    def current_champion(self) -> Champion | None:
        return self.currentData()

    def _on_index_changed(self, _index: int) -> None:
        self.profile_changed.emit(self.currentData())
