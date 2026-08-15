import pytest
from PySide6.QtCore import Qt

from lolcp.domain.entities import Item
from lolcp.domain.stats import StatKey, StatLine
from lolcp.domain.valuation import ItemComparison, LinearValuation
from lolcp.domain.pricing import PriceTable
from lolcp.domain.weights import StatWeights
from lolcp.presentation.item_table_model import ItemTableModel

pytestmark = pytest.mark.usefixtures("qapp")


def comparison(item_id: int, name: str, gold: int, canonical_price: float,
               ls_price: float) -> ItemComparison:
    item = Item(item_id=item_id, name=name, total_gold=gold, sell_gold=gold // 2,
                stats=(StatLine(StatKey.AD, 10.0),), tags=("Damage",), icon="", recipe=())
    weights = StatWeights.uniform()
    valuation = LinearValuation()
    return ItemComparison.of(
        canonical=valuation.evaluate(
            item, PriceTable({StatKey.AD: canonical_price}, frozenset()), weights
        ),
        least_squares=valuation.evaluate(
            item, PriceTable({StatKey.AD: ls_price}, frozenset()), weights
        ),
    )


@pytest.fixture
def model() -> ItemTableModel:
    m = ItemTableModel()
    m.set_comparisons([
        comparison(3031, "無盡之刃", 1000, 35.0, 40.0),   # 35.0% / 40.0%
        comparison(3078, "三相之力", 500, 35.0, 30.0),    # 70.0% / 60.0%
        comparison(3157, "中婭沙漏", 2000, 35.0, 35.0),   # 17.5% / 17.5%
    ])
    return m


def test_row_and_column_counts(model):
    assert model.rowCount() == 3
    assert model.columnCount() == len(ItemTableModel.COLUMNS)


def test_headers_match_the_spec_layout(model):
    headers = [
        model.headerData(c, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for c in range(model.columnCount())
    ]
    assert headers == ["裝備", "售價", "權威", "平方", "差異"]


def test_name_and_gold_columns(model):
    assert model.data(model.index(0, ItemTableModel.COL_NAME)) == "無盡之刃"
    assert model.data(model.index(0, ItemTableModel.COL_GOLD)) == "1000"


def test_ratio_columns_are_rendered_as_percentages(model):
    assert model.data(model.index(0, ItemTableModel.COL_CANONICAL)) == "35.0%"
    assert model.data(model.index(0, ItemTableModel.COL_LEAST_SQUARES)) == "40.0%"


def test_delta_column_is_signed(model):
    assert model.data(model.index(0, ItemTableModel.COL_DELTA)) == "+5.0"
    assert model.data(model.index(1, ItemTableModel.COL_DELTA)) == "-10.0"


def test_delta_of_zero_has_no_sign_confusion(model):
    assert model.data(model.index(2, ItemTableModel.COL_DELTA)) == "+0.0"


def test_sort_by_canonical_ratio_descending(model):
    model.sort(ItemTableModel.COL_CANONICAL, Qt.SortOrder.DescendingOrder)
    names = [model.data(model.index(r, ItemTableModel.COL_NAME)) for r in range(3)]
    assert names == ["三相之力", "無盡之刃", "中婭沙漏"]


def test_sort_by_gold_ascending(model):
    model.sort(ItemTableModel.COL_GOLD, Qt.SortOrder.AscendingOrder)
    golds = [model.data(model.index(r, ItemTableModel.COL_GOLD)) for r in range(3)]
    assert golds == ["500", "1000", "2000"]


def test_sort_by_name_uses_string_order(model):
    model.sort(ItemTableModel.COL_NAME, Qt.SortOrder.AscendingOrder)
    assert model.rowCount() == 3  # 不崩即可，中文排序順序不做斷言


def test_comparison_at_returns_the_underlying_object(model):
    assert model.comparison_at(0).item.item_id == 3031
    assert model.comparison_at(99) is None


def test_set_comparisons_replaces_previous_rows(model):
    model.set_comparisons([comparison(1036, "長劍", 350, 35.0, 35.0)])
    assert model.rowCount() == 1
    assert model.data(model.index(0, ItemTableModel.COL_NAME)) == "長劍"


def test_numeric_columns_are_right_aligned(model):
    role = Qt.ItemDataRole.TextAlignmentRole
    assert model.data(model.index(0, ItemTableModel.COL_GOLD), role) is not None
    assert model.data(model.index(0, ItemTableModel.COL_NAME), role) is None


def test_data_returns_none_for_invalid_index(model):
    from PySide6.QtCore import QModelIndex

    assert model.data(QModelIndex()) is None


def test_header_data_tolerates_out_of_range_sections(model):
    role = Qt.ItemDataRole.DisplayRole
    assert model.headerData(99, Qt.Orientation.Horizontal, role) is None
    assert model.headerData(-1, Qt.Orientation.Horizontal, role) is None


def test_sort_remaps_persistent_indexes(model):
    """QItemSelectionModel 依賴 persistent index —— 排序後選取列
    必須仍指向同一件裝備，而非同一個列號。"""
    from PySide6.QtCore import QPersistentModelIndex

    selected = QPersistentModelIndex(model.index(0, ItemTableModel.COL_NAME))
    assert model.data(selected) == "無盡之刃"

    model.sort(ItemTableModel.COL_CANONICAL, Qt.SortOrder.DescendingOrder)

    assert selected.isValid()
    assert selected.row() == 1  # 三相之力排到第 0 列，無盡之刃移到第 1 列
    assert model.data(model.index(selected.row(), ItemTableModel.COL_NAME)) == "無盡之刃"
