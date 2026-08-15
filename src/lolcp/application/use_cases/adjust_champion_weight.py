"""拉桿調整英雄權重：寫入覆寫層並讓 resolver 立即生效。"""

from __future__ import annotations

from lolcp.application.ports import OverridesStore
from lolcp.domain.entities import Champion
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import ChampionOverrides, WeightResolver

_EPS = 1e-9


class AdjustChampionWeight:
    def __init__(self, store: OverridesStore, resolver: WeightResolver) -> None:
        self._store = store
        self._resolver = resolver

    def execute(
        self, champion: Champion, stat: StatKey, value: float
    ) -> ChampionOverrides:
        """調到基準值即移除覆寫 —— 「有覆寫」恆等於「與基準不同」。

        無實質變化時不寫檔也不重載（回傳原覆寫物件，呼叫端可用
        相等性判斷跳過重算）。
        """
        default = self._resolver.resolve_defaults(champion).of(stat)
        target = None if abs(value - default) < _EPS else value

        current = self._resolver.overrides.by_champion.get(champion.key, {})
        if target is None and stat not in current:
            return self._resolver.overrides  # 本來就沒有覆寫
        if target is not None and stat in current and abs(current[stat] - target) < _EPS:
            return self._resolver.overrides  # 值沒變

        self._store.set_weight(champion.key, stat, target)
        overrides = self._store.load()
        self._resolver.replace_overrides(overrides)
        return overrides
