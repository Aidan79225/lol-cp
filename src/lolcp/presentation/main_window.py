"""主視窗：表格 + 右側詳情面板。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from lolcp.application.use_cases.list_valuations import ListValuations
from lolcp.application.use_cases.sync_game_data import SyncResult
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion
from lolcp.presentation.item_table_model import ItemTableModel
from lolcp.presentation.widgets.detail_panel import DetailPanel
from lolcp.presentation.widgets.filter_bar import FilterBar
from lolcp.presentation.widgets.profile_selector import ProfileSelector
from lolcp.presentation.widgets.status_bar import StatusBarWidget


class MainWindow(QMainWindow):
    def __init__(
        self,
        list_valuations: ListValuations,
        champions: tuple[Champion, ...],
        diagnostics: Diagnostics,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("lol-cp — 召喚峽谷裝備 CP值")
        self.resize(1100, 700)

        self._list_valuations = list_valuations
        self._diagnostics = diagnostics
        self._sync_result: SyncResult | None = None
        self._all_comparisons: tuple = ()

        self._profile = ProfileSelector(self)
        self._profile.set_champions(champions)
        self._profile.profile_changed.connect(self._on_profile_changed)

        self._filter = FilterBar(self)
        self._filter.filter_changed.connect(self._apply_filter)

        self._refresh = QPushButton("檢查更新", self)
        self._progress = QProgressBar(self)
        self._progress.setVisible(False)

        top = QHBoxLayout()
        top.addWidget(self._profile)
        top.addWidget(self._filter, 1)
        top.addWidget(self._progress)
        top.addWidget(self._refresh)

        self._model = ItemTableModel(self)
        self._table = QTableView(self)
        self._table.setModel(self._model)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.selectionModel().currentRowChanged.connect(self._on_row_changed)

        self._detail = DetailPanel(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setSizes([700, 400])

        self._status = StatusBarWidget(self)
        self.statusBar().addPermanentWidget(self._status, 1)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

    # ---- 外部驅動 ----

    def on_sync_finished(self, result: SyncResult) -> None:
        self._sync_result = result
        self._progress.setVisible(False)
        self.reload()

    def on_sync_progress(self, done: int, total: int) -> None:
        self._progress.setVisible(True)
        self._progress.setMaximum(total or 0)
        self._progress.setValue(done)

    def set_use_cases(
        self, list_valuations: ListValuations, champions: tuple[Champion, ...]
    ) -> None:
        """換版本後注入新的 use case 與英雄清單。視角重設為全域。"""
        self._list_valuations = list_valuations
        self._profile.set_champions(champions)

    def reload(self) -> None:
        champion = self._profile.current_champion()
        self._all_comparisons = self._list_valuations.execute(champion)
        tags = {tag for c in self._all_comparisons for tag in c.item.tags}
        current_tag = self._filter.current_tag()
        self._filter.set_tags(tags)
        if current_tag:
            self._filter.select_tag(current_tag)
        self._apply_filter()
        if self._sync_result is not None:
            self._status.update_status(self._sync_result, self._diagnostics)

    # ---- 內部 ----

    def _on_profile_changed(self, _champion) -> None:
        self.reload()

    def _apply_filter(self) -> None:
        visible = [c for c in self._all_comparisons if self._filter.matches(c)]
        self._model.set_comparisons(visible)
        self._detail.show_comparison(None)

    def _on_row_changed(self, current, _previous) -> None:
        self._detail.show_comparison(self._model.comparison_at(current.row()))

    @property
    def refresh_button(self) -> QPushButton:
        return self._refresh
