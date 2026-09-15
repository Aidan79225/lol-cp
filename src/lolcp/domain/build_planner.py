"""出裝規劃器（spec 2026-09-14 §3–§5）。

沿用 CombatModel，不改任何公式。評分：
    score_k = DPS × (EHP / 同等級裸裝EHP)^β
    V(序列) = Σ score_k × gold(第 k+1 件) + score_最後 × final_holding_gold
持有權重 ∝ 下一件的價格（金幣收入近似等速）—— 購買順序因此有意義。

搜尋兩階段：beam search 選組合（每個集合只留最佳序列），再對每個
留下的集合窮舉合法排列。集合數 ≤ beam 寬度時為全域最佳；否則是
啟發式，不保證最佳 —— 誠實邊界。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import permutations

from lolcp.domain.combat import ChampionKitView, CombatModel, TargetProfile
from lolcp.domain.entities import ChampionBaseStats, Item

MAX_SLOTS = 6
LEGENDARY_EPICNESS = 5
BOOTS_EPICNESS = 4
LEGENDARY_MIN_GOLD = 2000   # 排除 400g 任務裝與 1500g 靈魂竊取者
BOOTS_GROUP_ID = "Boots"


def is_legendary(item: Item) -> bool:
    """spec §4.1：epicness 5 ∧ 不會再升級 ∧ 至少 2000g。"""
    return (
        item.epicness == LEGENDARY_EPICNESS
        and not item.upgrades
        and item.total_gold >= LEGENDARY_MIN_GOLD
    )


def is_boots(item: Item) -> bool:
    """spec §4.1：二階鞋 = epicness 4 ∧ 屬於 Boots 群組（排除同為 4 的史詩部件）。"""
    return item.epicness == BOOTS_EPICNESS and any(
        g.group_id == BOOTS_GROUP_ID for g in item.group_limits
    )


def is_plannable(item: Item) -> bool:
    return is_legendary(item) or is_boots(item)


@dataclass(frozen=True)
class PlannerSettings:
    """常數只在 config/build_planner.toml；此處只守結構不變量。"""

    levels: tuple[int, ...]      # 持有第 1..6 件成品時的等級
    final_holding_gold: float
    beta: float
    boots_slot: int              # 1..6；0 = 不出鞋
    beam_width: int

    def __post_init__(self) -> None:
        if len(self.levels) != MAX_SLOTS:
            raise ValueError(f"levels 必須恰有 {MAX_SLOTS} 個，得到 {len(self.levels)}")
        if not 0 <= self.boots_slot <= MAX_SLOTS:
            raise ValueError(f"boots_slot 必須在 0..{MAX_SLOTS}，得到 {self.boots_slot}")
        if self.beam_width < 1:
            raise ValueError(f"beam_width 必須 ≥ 1，得到 {self.beam_width}")


@dataclass(frozen=True)
class PlanStep:
    item: Item
    level: int
    dps: float
    ehp: float
    score: float


@dataclass(frozen=True)
class BuildPlan:
    steps: tuple[PlanStep, ...]
    value: float
    skipped: tuple[Item, ...]    # 已購前綴中不參與規劃的件（部件等），絕不靜默丟棄


# 搜尋狀態：(序列, 已結算的持有價值, 最後一個前綴的 score)
_State = tuple[tuple[Item, ...], float, float]


class BuildPlanner:
    def __init__(self, model: CombatModel) -> None:
        self._model = model

    def for_champion(self, kit: ChampionKitView | None) -> BuildPlanner:
        """帶英雄技能模型的規劃器；None 時回傳自身（泛用基準技能）。"""
        return self if kit is None else BuildPlanner(self._model.for_champion(kit))

    def sequence_value(
        self,
        base: ChampionBaseStats,
        target: TargetProfile,
        sequence: Sequence[Item],
        settings: PlannerSettings,
    ) -> float:
        return _Evaluator(self._model, base, target, settings).value(tuple(sequence))

    def plan(
        self,
        base: ChampionBaseStats,
        target: TargetProfile,
        pool: Sequence[Item],
        prefix: Sequence[Item],
        settings: PlannerSettings,
    ) -> BuildPlan:
        """pool 可直接給全部裝備 —— 非傳說裝、非二階鞋在此濾除。

        prefix 為已購出裝（保序）；其中不可規劃的件進 skipped。
        """
        evaluator = _Evaluator(self._model, base, target, settings)
        kept = tuple(i for i in prefix if is_plannable(i))[:MAX_SLOTS]
        skipped = tuple(i for i in prefix if not is_plannable(i))
        candidates = tuple(
            sorted({i.item_id: i for i in pool if is_plannable(i)}.values(),
                   key=lambda i: i.item_id)
        )
        rules = _Rules(
            boots_slot=settings.boots_slot,
            prefix_length=len(kept),
            pool_has_boots=any(is_boots(i) for i in candidates),
        )

        best: tuple[tuple[Item, ...], float] | None = None
        for sequence in self._beam_search(evaluator, kept, candidates, rules, settings.beam_width):
            ordered, value = self._best_order(evaluator, kept, sequence, rules)
            if best is None or (len(ordered), value) > (len(best[0]), best[1]):
                best = (ordered, value)
        assert best is not None  # beam 至少含起始前綴

        sequence, value = best
        steps = tuple(
            PlanStep(sequence[k], settings.levels[k], *evaluator.score(sequence[: k + 1]))
            for k in range(len(sequence))
        )
        return BuildPlan(steps=steps, value=value, skipped=skipped)

    # ---- 第 1 階段：選組合 ----

    def _beam_search(
        self,
        evaluator: _Evaluator,
        prefix: tuple[Item, ...],
        candidates: tuple[Item, ...],
        rules: _Rules,
        width: int,
    ) -> list[tuple[Item, ...]]:
        beams: list[_State] = [evaluator.start(prefix)]
        finished: list[_State] = []
        while beams:
            frontier: dict[tuple[int, ...], _State] = {}
            for state in beams:
                sequence = state[0]
                if len(sequence) == MAX_SLOTS:
                    finished.append(state)
                    continue
                grew = False
                for candidate in candidates:
                    if not rules.legal(sequence, candidate):
                        continue
                    grew = True
                    child = evaluator.extend(state, candidate)
                    key = tuple(sorted(i.item_id for i in child[0]))
                    incumbent = frontier.get(key)
                    if incumbent is None or evaluator.partial_value(child) > evaluator.partial_value(incumbent):
                        frontier[key] = child
                if not grew:
                    finished.append(state)  # 池子耗盡：以較短序列收尾
            beams = sorted(
                frontier.values(),
                key=lambda s: (-evaluator.partial_value(s), tuple(i.item_id for i in s[0])),
            )[:width]
        return [state[0] for state in finished]

    # ---- 第 2 階段：排順序 ----

    def _best_order(
        self,
        evaluator: _Evaluator,
        prefix: tuple[Item, ...],
        sequence: tuple[Item, ...],
        rules: _Rules,
    ) -> tuple[tuple[Item, ...], float]:
        """前綴不動，其餘窮舉。permutations 先產出原順序，嚴格 > 使平手保留原順序。"""
        tail = sequence[len(prefix):]
        best_sequence, best_value = sequence, evaluator.value(sequence)
        for order in permutations(tail):
            candidate = prefix + order
            if not all(rules.legal(candidate[:k], candidate[k])
                       for k in range(len(prefix), len(candidate))):
                continue
            value = evaluator.value(candidate)
            if value > best_value:
                best_sequence, best_value = candidate, value
        return best_sequence, best_value


@dataclass(frozen=True)
class _Rules:
    boots_slot: int
    prefix_length: int
    pool_has_boots: bool

    def legal(self, sequence: tuple[Item, ...], candidate: Item) -> bool:
        if any(i.item_id == candidate.item_id for i in sequence):
            return False
        for limit in candidate.group_limits:
            held = sum(
                1 for i in sequence if any(g.group_id == limit.group_id for g in i.group_limits)
            )
            if held + 1 > limit.max_owned:
                return False
        return self._boots_legal(sequence, candidate)

    def _boots_legal(self, sequence: tuple[Item, ...], candidate: Item) -> bool:
        """恰一雙鞋、位於 boots_slot。前綴已含鞋即滿足；前綴已越過鞋位
        而無鞋時，鞋放在下一格。池中無鞋時規則不適用。"""
        if self.boots_slot == 0:
            return not is_boots(candidate)
        if not self.pool_has_boots:
            return True
        if any(is_boots(i) for i in sequence):
            return not is_boots(candidate)
        slot = max(self.boots_slot, self.prefix_length + 1)
        return (len(sequence) + 1 == slot) == is_boots(candidate)


class _Evaluator:
    def __init__(
        self,
        model: CombatModel,
        base: ChampionBaseStats,
        target: TargetProfile,
        settings: PlannerSettings,
    ) -> None:
        self._model = model
        self._base = base
        self._target = target
        self._settings = settings
        self._naked_ehp: dict[int, float] = {}
        self._memo: dict[tuple[int, ...], tuple[float, float, float]] = {}

    def score(self, build: tuple[Item, ...]) -> tuple[float, float, float]:
        """(dps, ehp, score)；等級取 levels[件數 − 1]。

        評分只取決於「哪些件」與件數，與順序無關 —— 以排序後的 ID 快取。
        第 2 階段窮舉 5 件的 120 種排列只會出現 32 種不同前綴集合。
        """
        key = tuple(sorted(i.item_id for i in build))
        cached = self._memo.get(key)
        if cached is not None:
            return cached
        level = self._settings.levels[len(build) - 1]
        profile = self._model.profile(self._base, level, build)
        dps = self._model.total_dps(profile, self._target)
        ehp = self._model.mixed_ehp(profile)
        if level not in self._naked_ehp:
            self._naked_ehp[level] = self._model.mixed_ehp(
                self._model.profile(self._base, level, ())
            )
        result = (dps, ehp, dps * (ehp / self._naked_ehp[level]) ** self._settings.beta)
        self._memo[key] = result
        return result

    def start(self, prefix: tuple[Item, ...]) -> _State:
        state: _State = ((), 0.0, 0.0)
        for item in prefix:
            state = self.extend(state, item)
        return state

    def extend(self, state: _State, item: Item) -> _State:
        sequence, settled, last_score = state
        if sequence:
            settled += last_score * item.total_gold
        extended = (*sequence, item)
        return extended, settled, self.score(extended)[2]

    def partial_value(self, state: _State) -> float:
        """最後一個前綴的持有權重暫以 final_holding_gold 計；滿 6 件時即為 V。"""
        sequence, settled, last_score = state
        if not sequence:
            return 0.0
        return settled + last_score * self._settings.final_holding_gold

    def value(self, sequence: tuple[Item, ...]) -> float:
        return self.partial_value(self.start(sequence))
