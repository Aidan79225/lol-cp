"""出裝列：邊際效益的「脈絡」輸入 —— 已購裝備（最多 6 格）與英雄等級。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

from lolcp.domain.entities import Item

MAX_SLOTS = 6
DEFAULT_LEVEL = 11


class BuildBar(QWidget):
    build_changed = Signal()
    level_changed = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[Item] = []
        self._buttons: list[QPushButton] = []

        self._level_spin = QSpinBox(self)
        self._level_spin.setRange(1, 18)
        self._level_spin.setValue(DEFAULT_LEVEL)
        self._level_spin.valueChanged.connect(self.level_changed.emit)

        self._clear = QPushButton("清空出裝", self)
        self._clear.clicked.connect(self.clear)

        self._layout = QHBoxLayout(self)
        self._layout.addWidget(QLabel("等級", self))
        self._layout.addWidget(self._level_spin)
        self._layout.addWidget(QLabel("出裝（雙擊表格加入，點擊移除）:", self))
        self._slot_start = self._layout.count()
        self._layout.addStretch(1)
        self._layout.addWidget(self._clear)

    # ---- 查詢 ----

    @property
    def build_ids(self) -> tuple[int, ...]:
        return tuple(item.item_id for item in self._items)

    @property
    def level(self) -> int:
        return self._level_spin.value()

    # ---- 操作 ----

    def add_item(self, item: Item) -> None:
        """滿 6 格忽略（遊戲規則），重複加入允許（疊同件是使用者的判斷）。"""
        if len(self._items) >= MAX_SLOTS:
            return
        self._items.append(item)
        button = QPushButton(item.name, self)
        button.setToolTip(f"{item.total_gold}g，點擊移除")
        button.clicked.connect(lambda _checked=False, b=button: self._remove(b))
        self._buttons.append(button)
        self._layout.insertWidget(self._slot_start + len(self._buttons) - 1, button)
        self.build_changed.emit()

    def clear(self) -> None:
        if not self._items:
            return
        for button in self._buttons:
            self._layout.removeWidget(button)
            button.deleteLater()
        self._items.clear()
        self._buttons.clear()
        self.build_changed.emit()

    def _remove(self, button: QPushButton) -> None:
        index = self._buttons.index(button)
        del self._items[index]
        del self._buttons[index]
        self._layout.removeWidget(button)
        button.deleteLater()
        self.build_changed.emit()
