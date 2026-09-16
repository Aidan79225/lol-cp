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

from lolcp.domain.build_planner import BuildPlan, PlanStep
from lolcp.domain.combat import TargetProfile
from lolcp.domain.entities import Champion

# 誠實邊界：已建模的被動件數由組裝根告知、技能狀態依視角英雄而定；其餘規劃器看不見。
BOUNDARY_TEMPLATE = "已計入 {count} 件裝備被動；{skills}；未計入：移速、吸血與護盾、群體效果"
GENERIC_SKILLS = "技能：泛用基準"


def _alternatives_text(step: PlanStep) -> str:
    """`鬼索 -0.7%（接近）、海妖殺手 -7.5%（可考慮）`；無替代顯示「—」。"""
    if not step.alternatives:
        return "—"
    return "、".join(
        f"{a.item.name} {(a.score_ratio - 1) * 100:+.1f}%（{a.tier.value}）"
        for a in step.alternatives
    )
_HEADERS = ("順序", "裝備", "等級", "DPS", "EHP", "評分", "替代選項")
_BETA_STEP = 0.05


class PlanPanel(QWidget):
    plan_requested = Signal(str, float)   # (target key, β)
    apply_requested = Signal()

    COL_ALTERNATIVES = 6

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
        # 替代選項是最長的一欄（三個「名稱 -x.x%（分級）」），讓它獨吃剩餘寬度；
        # 裝備名短，依內容縮放即可。仍可能截斷，故每格附 tooltip 存全文。
        header.setSectionResizeMode(self.COL_ALTERNATIVES, QHeaderView.ResizeMode.Stretch)

        self._skipped_label = QLabel("", self)
        self._skipped_label.setWordWrap(True)
        self._modelled_passives = 0
        self._skill_status = GENERIC_SKILLS
        self._boundary = QLabel("", self)
        self._boundary.setWordWrap(True)
        self._render_boundary()
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

    def set_modelled_passives(self, count: int) -> None:
        self._modelled_passives = count
        self._render_boundary()

    def set_skill_status(self, text: str) -> None:
        """「技能：已建模（…）」或 GENERIC_SKILLS —— 由主視窗依視角英雄決定。"""
        self._skill_status = text
        self._render_boundary()

    def _render_boundary(self) -> None:
        self._boundary.setText(
            BOUNDARY_TEMPLATE.format(count=self._modelled_passives, skills=self._skill_status)
        )

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
                _alternatives_text(step),
            )
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column == self.COL_ALTERNATIVES:
                    cell.setToolTip(text)   # 欄寬不足時滑鼠停留看全文
                self._table.setItem(row, column, cell)
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
