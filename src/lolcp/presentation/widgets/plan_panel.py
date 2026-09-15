"""出裝規劃分頁（spec 2026-09-14 §7.3）：目標、β、規劃鈕、結果表、套用。

面板不呼叫 use case —— 只發 plan_requested／apply_requested，由 MainWindow
轉給 PlanBuild 與 BuildBar（與 WeightPanel 同型）。
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lolcp.domain.build_planner import BuildPlan
from lolcp.domain.combat import TargetProfile
from lolcp.domain.entities import Champion

# 誠實邊界：規劃器只看屬性物理三公式，這些東西它看不見。
BOUNDARY_NOTE = "未計入：裝備被動、移速、吸血；英雄差異僅來自基礎數值"
_HEADERS = ("順序", "裝備", "等級", "DPS", "EHP", "評分")
_BETA_STEP = 0.05


class PlanPanel(QWidget):
    plan_requested = Signal(str, float)   # (target key, β)
    apply_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._plan: BuildPlan | None = None

        self._target_combo = QComboBox(self)
        self._beta_spin = QDoubleSpinBox(self)
        self._beta_spin.setRange(0.0, 1.0)
        self._beta_spin.setSingleStep(_BETA_STEP)
        self._beta_spin.setDecimals(2)
        self._plan_button = QPushButton("規劃", self)
        self._plan_button.clicked.connect(self._on_plan_clicked)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("目標", self))
        controls.addWidget(self._target_combo)
        controls.addWidget(QLabel("生存重要度 β", self))
        controls.addWidget(self._beta_spin)
        controls.addStretch(1)
        controls.addWidget(self._plan_button)

        self._table = QTableWidget(0, len(_HEADERS), self)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 裝備名最長，吃剩餘寬度

        self._skipped_label = QLabel("", self)
        self._skipped_label.setWordWrap(True)
        self._boundary = QLabel(BOUNDARY_NOTE, self)
        self._boundary.setWordWrap(True)
        self._apply_button = QPushButton("套用到出裝列", self)
        self._apply_button.setEnabled(False)
        self._apply_button.clicked.connect(lambda _checked=False: self.apply_requested.emit())

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._skipped_label)
        layout.addWidget(self._boundary)
        layout.addWidget(self._apply_button)

        self.setEnabled(False)  # 啟動時為全域視角

    # ---- 查詢 ----

    @property
    def plan(self) -> BuildPlan | None:
        return self._plan

    @property
    def current_target_key(self) -> str | None:
        return self._target_combo.currentData()

    @property
    def beta(self) -> float:
        return self._beta_spin.value()

    # ---- 外部驅動 ----

    def set_targets(self, targets: Sequence[TargetProfile], default_beta: float) -> None:
        self._target_combo.clear()
        for target in targets:
            self._target_combo.addItem(target.name, userData=target.key)
        self._beta_spin.setValue(default_beta)

    def set_context(self, champion: Champion | None) -> None:
        """全域視角或無基礎值的英雄停用；換視角時舊結果失效，一律清空。"""
        self.setEnabled(champion is not None and champion.base_stats is not None)
        self.show_plan(None)

    def show_plan(self, plan: BuildPlan | None) -> None:
        self._plan = plan
        self._table.setRowCount(0)
        if plan is None:
            self._skipped_label.setText("")
            self._apply_button.setEnabled(False)
            return
        self._table.setRowCount(len(plan.steps))
        for row, step in enumerate(plan.steps):
            cells = (
                str(row + 1),
                step.item.name,
                str(step.level),
                f"{step.dps:.0f}",
                f"{step.ehp:.0f}",
                f"{step.score:.1f}",
            )
            for column, text in enumerate(cells):
                self._table.setItem(row, column, QTableWidgetItem(text))
        self._skipped_label.setText(
            "略過（非成品，不參與規劃）：" + "、".join(i.name for i in plan.skipped)
            if plan.skipped
            else ""
        )
        self._apply_button.setEnabled(bool(plan.steps))

    # ---- 內部 ----

    def _on_plan_clicked(self) -> None:
        key = self.current_target_key
        if key is not None:
            self.plan_requested.emit(key, self.beta)
