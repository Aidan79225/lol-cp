"""指定英雄／目標／β 下，從已購出裝往下規劃 6 件成品與購買順序。

同步計算（fixture 規模約 0.3 秒），不需要 worker thread。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from lolcp.application.ports import ItemRepository
from lolcp.domain.build_planner import BuildPlan, BuildPlanner, PlannerSettings
from lolcp.domain.combat import ChampionKitView, TargetProfile
from lolcp.domain.entities import Champion


class PlanBuild:
    def __init__(
        self,
        items: ItemRepository,
        planner: BuildPlanner,
        targets: Sequence[TargetProfile],
        settings: PlannerSettings,
        kits: Mapping[str, ChampionKitView] | None = None,
    ) -> None:
        """kits：以英雄 key 索引的技能模型；沒有 kit 的英雄用泛用基準技能。"""
        self.items = items
        self._planner = planner
        self._targets = tuple(targets)
        self._settings = settings
        self._kits = dict(kits or {})

    @property
    def targets(self) -> tuple[TargetProfile, ...]:
        return self._targets

    @property
    def kits(self) -> Mapping[str, ChampionKitView]:
        return self._kits

    @property
    def settings(self) -> PlannerSettings:
        """設定檔預設值 —— UI 以此初始化 β。"""
        return self._settings

    def execute(
        self,
        champion: Champion | None,
        target_key: str,
        beta: float | None,
        prefix_ids: tuple[int, ...],
    ) -> BuildPlan | None:
        """champion 為 None（全域視角）或無基礎值時回 None。

        beta 為 None 時用設定檔預設；prefix_ids 中不存在的 ID 直接忽略
        （版本切換後舊出裝可能失效），部件由 planner 回報於 skipped。
        """
        if champion is None or champion.base_stats is None:
            return None
        target = next((t for t in self._targets if t.key == target_key), None)
        if target is None:
            valid = ", ".join(t.key for t in self._targets)
            raise ValueError(f"未知的目標 {target_key!r}。合法選項：{valid}")
        settings = self._settings if beta is None else replace(self._settings, beta=beta)
        all_items = self.items.all_items()
        by_id = {i.item_id: i for i in all_items}
        prefix = [by_id[i] for i in prefix_ids if i in by_id]
        planner = self._planner.for_champion(self._kits.get(champion.key))
        return planner.plan(champion.base_stats, target, all_items, prefix, settings)
