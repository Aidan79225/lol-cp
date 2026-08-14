"""診斷收集器 —— 實現「絕不靜默丟棄」原則。

本專案最危險的失效不是崩潰，是安靜地算錯。每一個「我不認識這個東西」的
分支都必須把痕跡丟進這裡，最後呈現在狀態列上。

這是 domain 內唯一刻意可變的物件：它是累積器，不是值物件。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from lolcp.domain.stats import StatKey


@dataclass(frozen=True)
class Conflict:
    """同一屬性在 bin 與 Data Dragon 給出不同數值。"""

    item_id: int
    stat: StatKey
    bin_value: float
    ddragon_value: float


@dataclass
class Diagnostics:
    _unknown_bin_fields: Counter[str] = field(default_factory=Counter)
    _conflicts: list[Conflict] = field(default_factory=list)
    _filtered_variants: list[int] = field(default_factory=list)
    _low_confidence: dict[StatKey, int] = field(default_factory=dict)
    _unknown_partypes: list[str] = field(default_factory=list)

    # ---- 記錄 ----

    def unknown_bin_field(self, field_name: str, item_id: int) -> None:
        self._unknown_bin_fields[field_name] += 1

    def source_conflict(
        self, item_id: int, stat: StatKey, bin_value: float, ddragon_value: float
    ) -> None:
        self._conflicts.append(Conflict(item_id, stat, bin_value, ddragon_value))

    def filtered_variant(self, item_id: int) -> None:
        self._filtered_variants.append(item_id)

    def low_confidence_price(self, stat: StatKey, item_count: int) -> None:
        self._low_confidence[stat] = item_count

    def unknown_partype(self, champion_key: str) -> None:
        self._unknown_partypes.append(champion_key)

    # ---- 查詢 ----

    @property
    def unknown_bin_fields(self) -> dict[str, int]:
        return dict(self._unknown_bin_fields)

    @property
    def conflicts(self) -> tuple[Conflict, ...]:
        return tuple(self._conflicts)

    @property
    def filtered_variant_count(self) -> int:
        return len(self._filtered_variants)

    @property
    def low_confidence_stats(self) -> dict[StatKey, int]:
        return dict(self._low_confidence)

    @property
    def unknown_partypes(self) -> tuple[str, ...]:
        return tuple(self._unknown_partypes)

    def summary_line(self) -> str:
        parts: list[str] = []
        if self._unknown_bin_fields:
            parts.append(f"{len(self._unknown_bin_fields)} 個未知屬性欄位")
        if self._conflicts:
            parts.append(f"衝突 {len(self._conflicts)} 筆")
        if self._filtered_variants:
            parts.append(f"過濾變體 {len(self._filtered_variants)} 件")
        if self._low_confidence:
            parts.append(f"低信賴單價 {len(self._low_confidence)} 種")
        if self._unknown_partypes:
            parts.append(f"未知資源類型 {len(self._unknown_partypes)} 隻")
        return "  |  ".join(parts) if parts else "無異常"
