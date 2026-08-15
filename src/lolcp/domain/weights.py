"""英雄視角的屬性權重。

權重取值 0.0～1.0 的 float 而非布林開關，因此 Level 1（適用性遮罩）與
Level 2（可調權重）在 domain 層完全同型 —— 日後加滑桿 UI 是純 presentation 工作。

兩個地方刻意「寧可多算也不隱藏」，理由相同：把英雄實際會用的屬性設為 0
會直接把資訊藏起來，比多算一個邊緣屬性糟得多。
  1. of() 對未定義屬性回傳 1.0
  2. union_max 取 max 而非平均
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion
from lolcp.domain.stats import StatKey

KNOWN_ROLES: tuple[str, ...] = (
    "Assassin", "Fighter", "Mage", "Marksman", "Support", "Tank",
)

DEFAULT_WEIGHT = 1.0


@dataclass(frozen=True)
class StatWeights:
    weights: Mapping[StatKey, float]

    @classmethod
    def uniform(cls, value: float = DEFAULT_WEIGHT) -> StatWeights:
        return cls({stat: value for stat in StatKey})

    def of(self, stat: StatKey) -> float:
        """未定義的屬性回傳 1.0，不是 0.0 —— 隱藏資訊的代價更高。"""
        return self.weights.get(stat, DEFAULT_WEIGHT)

    @property
    def masked_stats(self) -> frozenset[StatKey]:
        return frozenset(s for s, w in self.weights.items() if w == 0.0)

    def union_max(self, other: StatWeights) -> StatWeights:
        keys = set(self.weights) | set(other.weights)
        return StatWeights({k: max(self.of(k), other.of(k)) for k in keys})

    def merged_with(self, overrides: Mapping[StatKey, float]) -> StatWeights:
        return StatWeights({**self.weights, **overrides})

    def with_stat(self, stat: StatKey, value: float) -> StatWeights:
        return StatWeights({**self.weights, stat: value})


@dataclass(frozen=True)
class RoleDefaults:
    by_role: Mapping[str, StatWeights]

    def union_max(self, tags: Sequence[str], diagnostics: Diagnostics) -> StatWeights:
        """取英雄所有 tag 的聯集（逐屬性取 max）。

        沒有可用 tag 時回傳 uniform(1.0)，而非全零 —— 否則整張表會被清空。
        """
        merged: StatWeights | None = None
        for tag in tags:
            weights = self.by_role.get(tag)
            if weights is None:
                diagnostics.unknown_role(tag)
                continue
            merged = weights if merged is None else merged.union_max(weights)
        return merged if merged is not None else StatWeights.uniform()


class ResourceRule:
    """非法力英雄的法力權重歸零。

    判斷依據是 en_US 的 partype 而非 stats.mp —— 犽宿 mp=100 但資源是
    Flow，法力裝備對他完全無用。partype 判斷涵蓋 33 隻，mp==0 只涵蓋 11 隻。
    """

    def __init__(self, diagnostics: Diagnostics) -> None:
        self._diagnostics = diagnostics

    def apply(self, weights: StatWeights, champion: Champion) -> StatWeights:
        if champion.partype_unknown:
            self._diagnostics.unknown_partype(champion.key)
            return weights
        if champion.uses_mana:
            return weights
        return weights.with_stat(StatKey.MANA, 0.0)


@dataclass(frozen=True)
class ChampionOverrides:
    by_champion: Mapping[str, Mapping[StatKey, float]]

    def apply(self, weights: StatWeights, champion_key: str) -> StatWeights:
        overrides = self.by_champion.get(champion_key)
        return weights if not overrides else weights.merged_with(overrides)


class WeightResolver:
    """三層解析。新增英雄成本為零 —— tags 自動給出預設。

    順序固定：角色預設 → 資源規則 → 手動覆寫。
    覆寫在最後，因此可以蓋掉資源規則的歸零。
    """

    def __init__(
        self,
        role_defaults: RoleDefaults,
        resource_rule: ResourceRule,
        overrides: ChampionOverrides,
        diagnostics: Diagnostics,
    ) -> None:
        self._role_defaults = role_defaults
        self._resource_rule = resource_rule
        self._overrides = overrides
        self._diagnostics = diagnostics

    def resolve(self, champion: Champion | None) -> StatWeights:
        if champion is None:
            return StatWeights.uniform()  # 全域客觀視角
        weights = self.resolve_defaults(champion)
        return self._overrides.apply(weights, champion.key)

    def resolve_defaults(self, champion: Champion | None) -> StatWeights:
        """前兩層（角色預設 → 資源規則），即零覆寫時的值。拉桿的基準。"""
        if champion is None:
            return StatWeights.uniform()
        weights = self._role_defaults.union_max(champion.tags, self._diagnostics)
        return self._resource_rule.apply(weights, champion)

    def replace_overrides(self, overrides: ChampionOverrides) -> None:
        """拉桿寫檔後換掉覆寫層。domain 第二個刻意可變處（第一個是 Diagnostics）。"""
        self._overrides = overrides

    @property
    def overrides(self) -> ChampionOverrides:
        return self._overrides
