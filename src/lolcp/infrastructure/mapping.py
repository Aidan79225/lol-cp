"""原始 JSON → domain 實體。所有單位轉換與資料清理都只發生在這一層。

三個職責，刻意放在一起因為它們共用同一份原始資料的知識：
1. 過濾（召喚峽谷 ∧ 可購買 ∧ 標準 ID）
2. 正規化（百分比轉 1% 單位、消除 float32 雜訊）
3. 合併（bin 為基底，Data Dragon 補法力）並交叉檢查一致性
"""

from __future__ import annotations

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Item
from lolcp.domain.stats import (
    BIN_FIELD_TO_STAT,
    DDRAGON_FIELD_TO_STAT,
    DDRAGON_MANA_FIELD,
    StatKey,
    StatLine,
    normalize_amount,
)

SUMMONERS_RIFT_MAP_ID = "11"
MAX_STANDARD_ITEM_ID = 10_000
_STAT_FIELD_SUFFIX = "Mod"


def looks_like_bin_stat_field(name: str, value: object) -> bool:
    """這個 bin 欄位看起來是不是屬性欄位。

    用於偵測「看起來是屬性但我不認識」的欄位，好記錄進診斷而非靜默丟棄。
    bool 必須排除：Python 的 bool 是 int 的子類，`mCanBeSold: true` 會誤判。

    命名慣例有三種（原版只認第一種，導致穿甲／全能吸血／魔回被靜默
    丟棄多年 —— 見 2026-08-15 盲點修復 spec）：
      1. mXxxMod（mFlatPhysicalDamageMod）
      2. 小寫開頭 Mod 結尾（flatMPPoolMod、percentBaseMPRegenMod）
      3. 裸名 Lethality 結尾（PhysicalLethality）
    統一判準：`Mod` 或 `Lethality` 結尾。以 16.15.1 全裝備驗證無誤判：
    sellBackModifier 以 Modifier 結尾不中；maxStack、mRequiredLevel、
    LastMajorChange*、ShopOrderPriority 皆無此二字尾。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return name.endswith(_STAT_FIELD_SUFFIX) or name.endswith("Lethality")


class ItemMapper:
    def __init__(self, diagnostics: Diagnostics) -> None:
        self._diagnostics = diagnostics

    def is_summoners_rift_standard(self, item_id: str, raw_dd: dict) -> bool:
        gold = raw_dd.get("gold", {})
        return (
            raw_dd.get("maps", {}).get(SUMMONERS_RIFT_MAP_ID) is True
            and gold.get("purchasable") is True
            and gold.get("total", 0) > 0
            and int(item_id) < MAX_STANDARD_ITEM_ID
        )

    def to_item(self, item_id: int, raw_dd: dict, raw_bin: dict | None) -> Item:
        stats = self._map_bin_stats(item_id, raw_bin or {})
        self._merge_mana(stats, raw_dd)
        self._check_consistency(item_id, stats, raw_dd)
        gold = raw_dd.get("gold", {})
        return Item(
            item_id=item_id,
            name=raw_dd["name"],
            total_gold=int(gold.get("total", 0)),
            sell_gold=int(gold.get("sell", 0)),
            stats=tuple(StatLine(s, a) for s, a in sorted(stats.items(), key=lambda kv: kv[0].name)),
            tags=tuple(raw_dd.get("tags", ())),
            icon=raw_dd.get("image", {}).get("full", ""),
            recipe=tuple(int(x) for x in raw_dd.get("from", ())),
        )

    def map_all(self, dd_data: dict[str, dict], bin_data: dict[str, dict]) -> tuple[Item, ...]:
        items: list[Item] = []
        for item_id, raw_dd in dd_data.items():
            if not self.is_summoners_rift_standard(item_id, raw_dd):
                if int(item_id) >= MAX_STANDARD_ITEM_ID:
                    self._diagnostics.filtered_variant(int(item_id))
                continue
            raw_bin = bin_data.get(f"Items/{item_id}")
            items.append(self.to_item(int(item_id), raw_dd, raw_bin))
        return tuple(sorted(items, key=lambda i: i.item_id))

    # ---- 內部 ----

    def _map_bin_stats(self, item_id: int, raw_bin: dict) -> dict[StatKey, float]:
        stats: dict[StatKey, float] = {}
        for field_name, value in raw_bin.items():
            if not looks_like_bin_stat_field(field_name, value):
                continue
            stat = BIN_FIELD_TO_STAT.get(field_name)
            if stat is None:
                self._diagnostics.unknown_bin_field(field_name, item_id)
                continue
            stats[stat] = normalize_amount(stat, float(value))
        return stats

    def _merge_mana(self, stats: dict[StatKey, float], raw_dd: dict) -> None:
        """法力以 bin（flatMPPoolMod，15 件）優先，DD（23 件）只補缺。

        兩來源重疊值實測零分歧；若日後分歧，一致性檢查會記錄。
        """
        raw_mana = (raw_dd.get("stats") or {}).get(DDRAGON_MANA_FIELD)
        if raw_mana:
            stats.setdefault(StatKey.MANA, normalize_amount(StatKey.MANA, float(raw_mana)))

    def _check_consistency(
        self, item_id: int, stats: dict[StatKey, float], raw_dd: dict
    ) -> None:
        """重疊屬性交叉檢查（含法力）。bin 勝出，但分歧必須留下記錄。"""
        for field_name, raw_value in (raw_dd.get("stats") or {}).items():
            stat = DDRAGON_FIELD_TO_STAT.get(field_name)
            if stat is None or stat not in stats or not raw_value:
                continue
            ddragon_amount = normalize_amount(stat, float(raw_value))
            if abs(stats[stat] - ddragon_amount) > 1e-6:
                self._diagnostics.source_conflict(
                    item_id, stat, bin_value=stats[stat], ddragon_value=ddragon_amount
                )
