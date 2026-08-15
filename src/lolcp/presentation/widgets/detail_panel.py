"""屬性拆解面板。

render_lines 是純函式（staticmethod），把「顯示什麼文字」與
「怎麼塞進 widget」分開，因此遮罩／未定價／殘差正負三種措辭
可以直接用字串斷言測試，不需要截圖比對。
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from lolcp.domain.valuation import ItemComparison, ValuationResult


class DetailPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._label = QLabel("（選擇一件裝備）", self)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            self._label.textInteractionFlags().TextSelectableByMouse
        )
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addStretch(1)

    def show_comparison(self, comparison: ItemComparison | None) -> None:
        if comparison is None:
            self._label.setText("（選擇一件裝備）")
            return
        self._label.setText("\n".join(self.render_lines(comparison.canonical)))

    @staticmethod
    def _decimal(value: float) -> str:
        """:g 去除浮點雜訊，但整數值會掉小數點；補回 .0 讓「×0.0 遮罩」
        如實顯示，同時保留非整數權重（如 0.85）的完整位數。"""
        text = f"{value:g}"
        return text if "." in text or "e" in text else text + ".0"

    @staticmethod
    def render_lines(result: ValuationResult) -> list[str]:
        item = result.item
        lines = [f"{item.name}    {item.total_gold}g", "", "屬性拆解"]

        for contribution in result.contributions:
            marker = "  ⚠ 遮罩" if contribution.weight == 0.0 else ""
            lines.append(
                f"  {contribution.amount:g} {contribution.stat.config_key}"
                f"  ×{DetailPanel._decimal(contribution.unit_price)}"
                f" ×{DetailPanel._decimal(contribution.weight)}"
                f" = {contribution.gold:.0f}g{marker}"
            )

        for stat in result.unpriced:
            amount = item.amount_of(stat)
            lines.append(f"  {amount:g} {stat.config_key}  ⚠ 未定價")

        lines += [
            "",
            f"價值 {result.total_value:.0f} / {item.total_gold}"
            f" = {result.ratio * 100:.1f}%",
        ]

        residual = round(result.residual)  # 顯示取整；扣除錨的 ±1e-13 浮點雜訊歸零
        if residual > 0:
            lines.append(f"殘差 +{residual}g（至少這些金幣花在被動效果上）")
        elif residual < 0:
            lines.append(f"殘差 {residual}g（屬性本身已超值）")
        else:
            lines.append("殘差 0g（屬性恰好定價）")

        return lines
