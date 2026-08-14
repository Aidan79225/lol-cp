"""印出最小平方法在 fixture 上解出的實際單價。

用途：把結果填進 tests/golden/test_least_squares_prices.py 的 EXPECTED。
這是一次性的探查工具，不是測試 —— 測試必須有斷言。

執行：uv run python scripts/report_ls_prices.py
"""

from __future__ import annotations

import json
from pathlib import Path

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.pricing import LeastSquaresDeriver
from lolcp.infrastructure.mapping import ItemMapper

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "16.15.1"


def main() -> None:
    dd = json.loads((FIXTURES / "ddragon_items.json").read_text(encoding="utf-8"))["data"]
    binn = json.loads((FIXTURES / "items_bin.json").read_text(encoding="utf-8"))
    items = ItemMapper(Diagnostics()).map_all(dd, binn)

    deriver = LeastSquaresDeriver(Diagnostics())
    table = deriver.derive(items)

    rows = [i for i in items if i.stats]
    print(f"矩陣列數（有屬性的裝備）: {len(rows)}")
    print(f"矩陣欄數（出現的屬性）  : {len(table.priced_stats)}")
    print(f"condition number       : {deriver.last_condition_number:.1f}")
    print()
    print("EXPECTED = {")
    for stat in sorted(table.priced_stats, key=lambda s: s.name):
        flag = "  # 低信賴" if stat in table.low_confidence else ""
        # 用 repr 印出完整精度（可還原成相同的 float bits），
        # 這樣貼進黃金測試後才能用 rel=1e-6 精確比對，
        # 而不會被 .4f 這種展示用格式的四捨五入誤差絆倒。
        print(f"    StatKey.{stat.name}: {table.unit_price(stat)!r},{flag}")
    print("}")


if __name__ == "__main__":
    main()
