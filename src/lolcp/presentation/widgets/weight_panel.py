"""權重拉桿面板。拉桿 = 編輯覆寫層；基準值 = 前兩層解析結果。

sliderReleased 才發 weight_committed —— 每次重算會重跑 NNLS，
拖曳中不觸發。還原鈕發「基準值」，移除覆寫的語意由 use case 判定
（與基準相同即刪除），面板自己不做這個判斷。
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lolcp.domain.entities import Champion
from lolcp.domain.stats import SR_STATS, StatKey
from lolcp.domain.weights import StatWeights

_STEP = 0.05
_STEPS = 20  # 0.00～1.00


class WeightPanel(QWidget):
    weight_committed = Signal(object, float)  # (StatKey, 新值)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._defaults: StatWeights | None = None
        self._overrides: dict[StatKey, float] = {}
        self._positions: dict[StatKey, int] = {}  # set_context 時的基準格位
        self._sliders: dict[StatKey, QSlider] = {}
        self._values: dict[StatKey, QLabel] = {}
        self._names: dict[StatKey, QLabel] = {}

        self._hint = QLabel("全域視角為客觀基準，不可調整", self)
        self._reset_all = QPushButton("全部還原", self)
        self._reset_all.clicked.connect(self._on_reset_all)

        grid_host = QWidget(self)
        grid = QGridLayout(grid_host)
        # 只列 SR 屬性 —— 其餘 4 個 StatKey 不出現在召喚峽谷裝備上，
        # 調了也不影響任何價格，是死拉桿。
        for row, stat in enumerate(s for s in StatKey if s in SR_STATS):
            name = QLabel(stat.config_key, grid_host)
            slider = QSlider(Qt.Orientation.Horizontal, grid_host)
            slider.setRange(0, _STEPS)
            slider.valueChanged.connect(
                lambda position, s=stat: self._on_value_changed(s, position)
            )
            slider.sliderReleased.connect(lambda s=stat: self._commit(s))
            value = QLabel("", grid_host)
            reset = QPushButton("還原", grid_host)
            reset.clicked.connect(lambda _checked=False, s=stat: self._on_reset(s))
            grid.addWidget(name, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value, row, 2)
            grid.addWidget(reset, row, 3)
            self._sliders[stat] = slider
            self._values[stat] = value
            self._names[stat] = name
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)

        layout = QVBoxLayout(self)
        layout.addWidget(self._hint)
        layout.addWidget(self._reset_all)
        layout.addWidget(scroll, 1)

    # ---- 外部驅動 ----

    def set_context(
        self,
        champion: Champion | None,
        defaults: StatWeights | None,
        overrides: Mapping[StatKey, float],
    ) -> None:
        editable = champion is not None and defaults is not None
        self._defaults = defaults if editable else None
        self._overrides = dict(overrides) if editable else {}
        self._hint.setVisible(not editable)
        self._reset_all.setEnabled(editable)
        for stat, slider in self._sliders.items():
            slider.setEnabled(editable)
            current = self._current(stat) if editable else 0.0
            position = round(current / _STEP)
            self._positions[stat] = position
            slider.blockSignals(True)
            slider.setValue(position)
            slider.blockSignals(False)
            self._values[stat].setText(f"{current:.2f}" if editable else "—")
            self._set_overridden_style(stat, editable and stat in self._overrides)

    # ---- 內部 ----

    def _current(self, stat: StatKey) -> float:
        if stat in self._overrides:
            return self._overrides[stat]
        return self._defaults.of(stat) if self._defaults else 0.0

    def _set_overridden_style(self, stat: StatKey, overridden: bool) -> None:
        font = self._names[stat].font()
        font.setBold(overridden)
        self._names[stat].setFont(font)

    def _on_value_changed(self, stat: StatKey, position: int) -> None:
        if self._defaults is None:
            return
        self._values[stat].setText(f"{position * _STEP:.2f}")
        if not self._sliders[stat].isSliderDown():
            self._commit(stat)  # 鍵盤／PageUp 等非拖曳改值不會發 sliderReleased

    def _commit(self, stat: StatKey) -> None:
        if self._defaults is None:
            return
        position = self._sliders[stat].value()
        if position == self._positions.get(stat):
            # 格位沒變就不提交 —— 點一下不拖動不可把手調值（如 0.87）
            # 改寫成最近的 0.05 倍數。
            self._values[stat].setText(f"{self._current(stat):.2f}")
            return
        self._positions[stat] = position  # 樂觀更新，避免 release 對同格位重複提交
        self.weight_committed.emit(stat, position * _STEP)

    def _on_reset(self, stat: StatKey) -> None:
        if self._defaults is None:
            return
        self.weight_committed.emit(stat, self._defaults.of(stat))

    def _on_reset_all(self) -> None:
        if self._defaults is None:
            return
        for stat in list(self._overrides):
            self.weight_committed.emit(stat, self._defaults.of(stat))
