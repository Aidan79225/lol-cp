"""邊際效益模型的戰鬥公式（spec 2026-08-17 §3）。

三條全英雄通用的公式：普攻 DPS、法術爆發 proxy、EHP。刻意不含任何
技能倍率或連招知識 —— 英雄差異只透過 ChampionBaseStats 進來，
「操作」以 TargetProfile 標準目標取代。每個數字都可手算驗證。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from lolcp.domain.entities import ChampionBaseStats, Item
from lolcp.domain.stats import StatKey

AS_CAP = 2.5
BASE_CRIT_BONUS = 0.75   # 基礎暴擊傷害 175% → 額外 0.75；裝備暴傷疊加其上
CRIT_CHANCE_CAP = 100.0


def growth_factor(level: int) -> float:
    """Riot 官方非線性等級成長：(lv−1) × (0.7025 + 0.0175 × (lv−1))。

    線性內插是常見錯誤 —— lv18 的因子是 17.0，不是 17 × 0.7025。
    """
    return (level - 1) * (0.7025 + 0.0175 * (level - 1))


@dataclass(frozen=True)
class TargetProfile:
    """標準假想目標 —— 取代「操作假設」的東西。數值在 combat_model.toml。"""

    key: str
    name: str
    armor: float
    magic_resist: float
    hp: float


@dataclass(frozen=True)
class SpellProxy:
    """泛用基準技能。三個常數是主觀擇定（可爭論），只存在於設定檔。"""

    base_damage: float
    ap_ratio: float
    base_cooldown: float


@dataclass(frozen=True)
class CombatProfile:
    """英雄在指定等級、指定出裝下的總戰鬥屬性（已聚合、已套上限）。"""

    attack_damage: float
    attack_speed: float
    crit_chance: float       # 0–100
    crit_damage_bonus: float # 裝備暴傷，％點數
    armor_pen_percent: float
    armor_pen_flat: float
    ap: float
    magic_pen_percent: float
    magic_pen_flat: float
    ability_haste: float
    hp: float
    armor: float
    magic_resist: float


class CombatModel:
    def __init__(self, spell_proxy: SpellProxy) -> None:
        self._proxy = spell_proxy

    def profile(
        self, base: ChampionBaseStats, level: int, items: Sequence[Item]
    ) -> CombatProfile:
        totals: dict[StatKey, float] = {}
        for it in items:
            for line in it.stats:
                totals[line.stat] = totals.get(line.stat, 0.0) + line.amount
        g = growth_factor(level)
        attack_speed = base.attack_speed * (
            1
            + (base.attack_speed_growth * g + totals.get(StatKey.ATTACK_SPEED, 0.0))
            / 100
        )
        return CombatProfile(
            attack_damage=base.attack_damage
            + base.attack_damage_growth * g
            + totals.get(StatKey.AD, 0.0),
            attack_speed=min(AS_CAP, attack_speed),
            crit_chance=min(CRIT_CHANCE_CAP, totals.get(StatKey.CRIT_CHANCE, 0.0)),
            crit_damage_bonus=totals.get(StatKey.CRIT_DAMAGE, 0.0),
            armor_pen_percent=totals.get(StatKey.ARMOR_PEN_PERCENT, 0.0),
            armor_pen_flat=totals.get(StatKey.ARMOR_PEN_FLAT, 0.0),
            ap=totals.get(StatKey.AP, 0.0),
            magic_pen_percent=totals.get(StatKey.MAGIC_PEN_PERCENT, 0.0),
            magic_pen_flat=totals.get(StatKey.MAGIC_PEN_FLAT, 0.0),
            ability_haste=totals.get(StatKey.ABILITY_HASTE, 0.0),
            hp=base.hp + base.hp_growth * g + totals.get(StatKey.HP, 0.0),
            armor=base.armor + base.armor_growth * g + totals.get(StatKey.ARMOR, 0.0),
            magic_resist=base.magic_resist
            + base.magic_resist_growth * g
            + totals.get(StatKey.MAGIC_RESIST, 0.0),
        )

    def total_dps(self, profile: CombatProfile, target: TargetProfile) -> float:
        """普攻 DPS + 法術 proxy。純防裝在此自然趨零，由 EHP 接手。"""
        crit_factor = 1 + (profile.crit_chance / 100) * (
            BASE_CRIT_BONUS + profile.crit_damage_bonus / 100
        )
        effective_armor = max(
            0.0,
            target.armor * (1 - profile.armor_pen_percent / 100)
            - profile.armor_pen_flat,
        )  # Riot 規則：% 先算、穿甲後扣，且不為負
        aa_dps = (
            profile.attack_damage
            * profile.attack_speed
            * crit_factor
            * 100
            / (100 + effective_armor)
        )
        return aa_dps + self._spell_dps(profile, target)

    def _spell_dps(self, profile: CombatProfile, target: TargetProfile) -> float:
        """只在 AP > 0 時計入 —— 否則基準傷會讓每隻英雄憑空多一段傷害。"""
        if profile.ap <= 0:
            return 0.0
        effective_mr = max(
            0.0,
            target.magic_resist * (1 - profile.magic_pen_percent / 100)
            - profile.magic_pen_flat,
        )
        cooldown = self._proxy.base_cooldown / (1 + profile.ability_haste / 100)
        burst = (self._proxy.base_damage + self._proxy.ap_ratio * profile.ap) * 100 / (
            100 + effective_mr
        )
        return burst / cooldown

    def mixed_ehp(self, profile: CombatProfile) -> float:
        """物理與魔法 EHP 的平均（V1 不做傷害型加權，見 spec §9）。"""
        physical = profile.hp * (1 + profile.armor / 100)
        magical = profile.hp * (1 + profile.magic_resist / 100)
        return (physical + magical) / 2


@dataclass(frozen=True)
class MarginalResult:
    """一件候選裝備的邊際效益（每千金）。"""

    item: Item
    dps_per_1k: Mapping[str, float]  # target key → ΔDPS/千金
    ehp_per_1k: float


class MarginalValuation:
    """Δ指標(裝備) = 指標(出裝+裝備) − 指標(出裝)，除以價格 ×1000。

    這捕捉的正是線性模型看不見的乘法協同：暴擊裝越多，
    無盡之刃的邊際值越高；目標護甲越高，穿透的邊際值越高。
    """

    def __init__(self, model: CombatModel, targets: Sequence[TargetProfile]) -> None:
        self._model = model
        self._targets = tuple(targets)

    def evaluate(
        self,
        base: ChampionBaseStats,
        level: int,
        build: Sequence[Item],
        candidates: Sequence[Item],
    ) -> tuple[MarginalResult, ...]:
        current = self._model.profile(base, level, build)
        current_dps = {t.key: self._model.total_dps(current, t) for t in self._targets}
        current_ehp = self._model.mixed_ehp(current)

        results: list[MarginalResult] = []
        for item in candidates:
            if item.total_gold <= 0:
                continue
            with_item = self._model.profile(base, level, [*build, item])
            per_gold = 1000 / item.total_gold
            results.append(
                MarginalResult(
                    item=item,
                    dps_per_1k={
                        t.key: (self._model.total_dps(with_item, t) - current_dps[t.key])
                        * per_gold
                        for t in self._targets
                    },
                    ehp_per_1k=(self._model.mixed_ehp(with_item) - current_ehp)
                    * per_gold,
                )
            )
        return tuple(results)
