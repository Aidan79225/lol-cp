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
    _unknown_roles: list[str] = field(default_factory=list)
    _missing_locale_entries: list[str] = field(default_factory=list)
    _unresolved_item_groups: Counter[str] = field(default_factory=Counter)
    _unsupported_formula_parts: Counter[str] = field(default_factory=Counter)
    _unbound_item_effects: dict[int, tuple[str, ...]] = field(default_factory=dict)
    _missing_champion_spells: list[str] = field(default_factory=list)
    _unbound_champion_kits: dict[str, tuple[str, ...]] = field(default_factory=dict)

    # ---- 記錄 ----

    def unbound_champion_kit(self, champion_key: str, reasons: tuple[str, ...]) -> None:
        """英雄技能模型綁定失敗（缺名稱或公式不支援）—— 該英雄退回泛用基準技能。"""
        self._unbound_champion_kits[champion_key] = reasons

    def missing_champion_spell(self, champion_key: str) -> None:
        """有技能模型的英雄缺 bin（補抓失敗或離線）—— 該英雄退回泛用基準技能。"""
        if champion_key not in self._missing_champion_spells:
            self._missing_champion_spells.append(champion_key)

    def unbound_item_effect(self, item_id: int, reasons: tuple[str, ...]) -> None:
        """裝備被動綁定失敗（缺名稱或公式不支援）—— 該件效果已停用。"""
        self._unbound_item_effects[item_id] = reasons

    def unsupported_formula_part(self, reason: str) -> None:
        """公式樹含 V1 不認識的組件型別或屬性代碼（已轉為 Unsupported）。"""
        self._unsupported_formula_parts[reason] += 1

    def unresolved_item_group(self, group_ref: str, item_id: int) -> None:
        """裝備參照的 ItemGroup 不在 bin 最外層 —— 其持有上限無從得知。"""
        self._unresolved_item_groups[group_ref] += 1

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

    def unknown_role(self, tag: str) -> None:
        self._unknown_roles.append(tag)

    def missing_locale_entry(self, champion_key: str) -> None:
        """zh_TW 缺此英雄條目，顯示名以 en_US 頂替。"""
        self._missing_locale_entries.append(champion_key)

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

    @property
    def unknown_roles(self) -> tuple[str, ...]:
        return tuple(self._unknown_roles)

    @property
    def missing_locale_entries(self) -> tuple[str, ...]:
        return tuple(self._missing_locale_entries)

    @property
    def unresolved_item_groups(self) -> dict[str, int]:
        return dict(self._unresolved_item_groups)

    @property
    def unsupported_formula_parts(self) -> dict[str, int]:
        return dict(self._unsupported_formula_parts)

    @property
    def unbound_item_effects(self) -> dict[int, tuple[str, ...]]:
        return dict(self._unbound_item_effects)

    @property
    def missing_champion_spells(self) -> tuple[str, ...]:
        return tuple(self._missing_champion_spells)

    @property
    def unbound_champion_kits(self) -> dict[str, tuple[str, ...]]:
        return dict(self._unbound_champion_kits)

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
        if self._unknown_roles:
            parts.append(f"未知角色標籤 {len(set(self._unknown_roles))} 種")
        if self._missing_locale_entries:
            parts.append(f"在地化缺項 {len(set(self._missing_locale_entries))} 隻")
        if self._unresolved_item_groups:
            parts.append(f"未解析裝備群組 {len(self._unresolved_item_groups)} 個")
        if self._unbound_item_effects:
            parts.append(f"被動綁定失敗 {len(self._unbound_item_effects)} 件")
        if self._missing_champion_spells:
            parts.append(f"英雄技能資料缺漏 {len(self._missing_champion_spells)} 隻")
        if self._unbound_champion_kits:
            parts.append(f"技能模型綁定失敗 {len(self._unbound_champion_kits)} 隻")
        # 不支援的公式組件刻意不列入：真實資料本來就大量存在，只有被效果綁定
        # 時才有害，而那會以「被動綁定失敗」呈現（spec 2026-09-15 §6 註）。
        return "  |  ".join(parts) if parts else "無異常"
