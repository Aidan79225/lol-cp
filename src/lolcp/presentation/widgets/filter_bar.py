"""依裝備 tag 篩選。「全部」為預設。"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

ALL_TAGS = "全部"


class FilterBar(QWidget):
    filter_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._combo = QComboBox(self)
        self._combo.currentIndexChanged.connect(lambda _i: self.filter_changed.emit())
        layout = QHBoxLayout(self)
        layout.addWidget(QLabel("篩選:", self))
        layout.addWidget(self._combo)
        layout.addStretch(1)

    def set_tags(self, tags: Iterable[str]) -> None:
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem(ALL_TAGS)
        for tag in sorted(set(tags)):
            self._combo.addItem(tag)
        self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)

    def select_tag(self, tag: str) -> None:
        index = self._combo.findText(tag)
        if index >= 0:
            self._combo.setCurrentIndex(index)

    def current_tag(self) -> str | None:
        tag = self._combo.currentText()
        return None if tag == ALL_TAGS else tag

    def matches(self, comparison) -> bool:
        tag = self.current_tag()
        return tag is None or tag in comparison.item.tags
