"""指定英雄／等級／出裝下，全裝備的邊際效益。

純算術（無 NNLS），毫秒級 —— 出裝、等級、視角一變即可重算。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from lolcp.application.ports import ItemRepository
from lolcp.domain.combat import (
    ChampionKitView,
    CombatModel,
    MarginalResult,
    MarginalValuation,
    TargetProfile,
)
from lolcp.domain.entities import Champion


class ComputeMarginals:
    def __init__(
        self,
        items: ItemRepository,
        model: CombatModel,
        targets: Sequence[TargetProfile],
        kits: Mapping[str, ChampionKitView] | None = None,
    ) -> None:
        """kits：以英雄 key 索引的技能模型；沒有 kit 的英雄用泛用基準技能。"""
        self.items = items
        self._model = model
        self._targets = tuple(targets)
        self._kits = dict(kits or {})

    @property
    def targets(self) -> tuple[TargetProfile, ...]:
        return self._targets

    def execute(
        self, champion: Champion | None, level: int, build_ids: tuple[int, ...]
    ) -> tuple[MarginalResult, ...]:
        """champion 為 None（全域視角）或無基礎值時回空 —— 邊際欄顯示「—」。

        build_ids 中不存在的 ID 直接忽略（版本切換後舊出裝可能失效）。
        """
        if champion is None or champion.base_stats is None:
            return ()
        all_items = self.items.all_items()
        by_id = {i.item_id: i for i in all_items}
        build = [by_id[i] for i in build_ids if i in by_id]
        model = self._model.for_champion(self._kits.get(champion.key))
        return MarginalValuation(model, self._targets).evaluate(
            champion.base_stats, level, build, all_items
        )
