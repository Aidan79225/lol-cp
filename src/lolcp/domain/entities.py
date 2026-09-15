"""領域實體。皆為不可變值物件。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from lolcp.domain.formulas import Formula
from lolcp.domain.stats import StatKey, StatLine

MANA_PARTYPE = "Mana"
# 實測：達瑞文 550、煞蜜拉 500（遠程），凱爾 175（近戰；6 級起靠被動變遠程，技能不在模型內）。
RANGED_ATTACK_RANGE_THRESHOLD = 300.0


@dataclass(frozen=True)
class GroupLimit:
    """bin ItemGroup 的持有上限，例如最後耳語系只能擁有 1 件。"""

    group_id: str   # bin mItemGroupID，例如 "LastWhisper"、"Boots"
    max_owned: int


@dataclass(frozen=True)
class Item:
    """一件裝備。stats 內的 amount 一律已正規化（見 stats.NORMALIZE_X100）。"""

    item_id: int
    name: str
    total_gold: int
    sell_gold: int
    stats: tuple[StatLine, ...]
    tags: tuple[str, ...]
    icon: str
    recipe: tuple[int, ...]
    # ---- 出裝規劃器用（spec 2026-09-14 §6.1）；預設值保持既有建構相容 ----
    epicness: int | None = None               # bin epicness：5 傳說、4 二階鞋與史詩部件
    upgrades: tuple[int, ...] = ()            # Data Dragon `into`
    group_limits: tuple[GroupLimit, ...] = () # 只含有上限的群組
    # ---- 裝備被動用（spec 2026-09-15 §4.4）；tuple of pairs 保持 Item 可雜湊 ----
    data_values: tuple[tuple[str, float], ...] = ()     # bin mDataValues
    calculations: tuple[tuple[str, Formula], ...] = ()  # bin mItemCalculations

    def amount_of(self, stat: StatKey) -> float | None:
        """回傳屬性數量；沒有這條屬性回 None。

        None 與 0.0 是不同的事，呼叫端必須區分。
        """
        for line in self.stats:
            if line.stat is stat:
                return line.amount
        return None

    @cached_property
    def stat_keys(self) -> frozenset[StatKey]:
        return frozenset(line.stat for line in self.stats)

    @cached_property
    def data_value_map(self) -> dict[str, float]:
        return dict(self.data_values)

    @cached_property
    def calculation_map(self) -> dict[str, Formula]:
        return dict(self.calculations)


@dataclass(frozen=True)
class ChampionBaseStats:
    """英雄基礎數值與每級成長（champion.json 的 stats 區塊，純資料驅動）。

    攻速成長與裝備攻速都是對基礎攻速的百分比加成，其餘為線性疊加；
    等級縮放一律走 combat.growth_factor 的非線性公式。
    """

    attack_damage: float
    attack_damage_growth: float
    attack_speed: float          # 次/秒
    attack_speed_growth: float   # %/級
    hp: float
    hp_growth: float
    armor: float
    armor_growth: float
    magic_resist: float
    magic_resist_growth: float
    # champion.json attackrange。預設值僅為建構相容 —— repository 一律提供。
    attack_range: float = 0.0

    @property
    def is_ranged(self) -> bool:
        """命中特效分遠近程數值（spec 2026-09-15 §3.2）。"""
        return self.attack_range >= RANGED_ATTACK_RANGE_THRESHOLD


@dataclass(frozen=True)
class Champion:
    """一隻英雄。partype 與 tags 一律取自 en_US（在地化字串不可用於邏輯判斷）。"""

    key: str
    numeric_id: int
    name: str          # 顯示用，取自 zh_TW
    tags: tuple[str, ...]
    partype: str       # en_US，例如 "Mana" / "Flow" / "None"
    base_stats: ChampionBaseStats | None = None  # 無資料時邊際欄退化為「—」

    @property
    def uses_mana(self) -> bool:
        return self.partype == MANA_PARTYPE

    @property
    def partype_unknown(self) -> bool:
        """partype 為空字串。視為未知，不可推論為無法力。"""
        return self.partype == ""
