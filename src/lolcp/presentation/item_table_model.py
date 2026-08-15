"""裝備表格的 Qt model。

刻意只做「顯示」與「排序」，不做任何計算 —— CP值 全部由
application 層算好後以 ItemComparison 傳進來。這讓整個 model
可以在不開視窗的情況下測試。
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from lolcp.domain.valuation import ItemComparison


class ItemTableModel(QAbstractTableModel):
    COLUMNS: tuple[str, ...] = ("裝備", "售價", "權威", "平方", "差異")

    COL_NAME = 0
    COL_GOLD = 1
    COL_CANONICAL = 2
    COL_LEAST_SQUARES = 3
    COL_DELTA = 4

    _NUMERIC_COLUMNS = (COL_GOLD, COL_CANONICAL, COL_LEAST_SQUARES, COL_DELTA)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[ItemComparison] = []

    # ---- 資料設定 ----

    def set_comparisons(self, comparisons: Sequence[ItemComparison]) -> None:
        self.beginResetModel()
        self._rows = list(comparisons)
        self.endResetModel()

    def comparison_at(self, row: int) -> ItemComparison | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    # ---- QAbstractTableModel ----

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole
    ):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        if not 0 <= section < len(self.COLUMNS):  # 負值會被 Python 索引繞回，一併擋掉
            return None
        return self.COLUMNS[section]

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column in self._NUMERIC_COLUMNS:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return None

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        match column:
            case self.COL_NAME:
                return row.item.name
            case self.COL_GOLD:
                return str(row.item.total_gold)
            case self.COL_CANONICAL:
                return f"{row.canonical.ratio * 100:.1f}%"
            case self.COL_LEAST_SQUARES:
                return f"{row.least_squares.ratio * 100:.1f}%"
            case self.COL_DELTA:
                return f"{row.delta * 100:+.1f}"
        return None

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        keys = {
            self.COL_NAME: lambda c: c.item.name,
            self.COL_GOLD: lambda c: c.item.total_gold,
            self.COL_CANONICAL: lambda c: c.canonical.ratio,
            self.COL_LEAST_SQUARES: lambda c: c.least_squares.ratio,
            self.COL_DELTA: lambda c: c.delta,
        }
        key = keys.get(column)
        if key is None:
            return
        # 排序必須重映射 persistent index，否則 QTableView 的選取列
        # 在點表頭後會悄悄指到別件裝備（QItemSelectionModel 內部
        # 依賴 persistent index）。
        self.layoutAboutToBeChanged.emit()
        old_rows = self._rows
        self._rows = sorted(
            old_rows, key=key, reverse=order == Qt.SortOrder.DescendingOrder
        )
        new_row_of = {id(c): r for r, c in enumerate(self._rows)}
        stale = self.persistentIndexList()
        self.changePersistentIndexList(
            stale,
            [
                self.index(new_row_of[id(old_rows[p.row()])], p.column())
                for p in stale
            ],
        )
        self.layoutChanged.emit()
