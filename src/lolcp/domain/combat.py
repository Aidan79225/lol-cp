"""戰鬥公式（spec 2026-08-17 §3；傷害模型 V2：spec 2026-09-15 §3；技能窗口：champion-kits §3）。

三條全英雄通用的公式：普攻 DPS、法術爆發 proxy、EHP。英雄差異透過
ChampionBaseStats 進來，「操作」以 TargetProfile 標準目標取代。每個數字都可手算驗證。

V2：一次普攻拆成物理／魔法兩種傷害分別吃抗性；裝備被動（item_effects）
在 profile() 依階段套用，產生 AttackModifiers。與目標無關的量在 profile()
算好，與目標有關的只存參數，total_dps() 才代入目標。

技能模型（champion_kits）：for_champion() 回傳帶 kit 的視圖。技能在固定戰鬥
時長內依冷卻施放，窗口總傷 ÷ 時長取代泛用基準技能；沒有 kit 的英雄行為不變。
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from math import floor
from typing import Protocol

from lolcp.domain.entities import ChampionBaseStats, Item
from lolcp.domain.formulas import FormulaContext, FormulaStat, StatPart, evaluate
from lolcp.domain.kit_settings import KitSettings
from lolcp.domain.skill_ranks import skill_ranks
from lolcp.domain.spells import ChampionSpells, SpellData
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
    bonus_hp: float = 0.0  # 多明尼克吃額外生命；設定檔必填，預設值僅為建構相容


@dataclass(frozen=True)
class FightAssumptions:
    """整場平均假設（spec 2026-09-15 §3.3）。數值只在 combat_model.toml。

    未設旋鈕的假設：疊層型被動視為已疊滿、增益視為常駐 —— 整場平均即穩態。
    """

    average_current_hp_ratio: float  # 目標平均剩餘生命比；已損失 = 1 − 此值
    energized_attacks: int           # 充能普攻每幾下普攻觸發一次
    # 技能模型的固定戰鬥時長（spec champion-kits §3）；設定檔必填，預設值僅為建構相容
    fight_duration_seconds: float = 10.0


@dataclass(frozen=True)
class SpellProxy:
    """泛用基準技能。三個常數是主觀擇定（可爭論），只存在於設定檔。"""

    base_damage: float
    ap_ratio: float
    base_cooldown: float


@dataclass(frozen=True)
class AttackModifiers:
    """被動與技能對傷害的修飾量。預設值 = 無被動、無技能模型。

    *_current_hp_ratio／missing_hp 已乘上整場平均生命比，total_dps() 只需乘目標最大生命；
    energized_* 已攤平到每下普攻；spell_window_* 是整個戰鬥窗口的總量。
    """

    physical_on_hit: float = 0.0
    magic_on_hit: float = 0.0
    on_hit_current_hp_ratio: float = 0.0     # 物理
    on_hit_multiplier: float = 1.0           # 鬼索：命中特效 × 4/3
    physical_per_attack: float = 0.0         # 普攻附加、非命中特效（達瑞文 Q）
    magic_per_attack: float = 0.0            # 普攻附加、非命中特效（凱爾劍氣、煞蜜拉被動）
    energized_physical: float = 0.0
    energized_magic: float = 0.0
    energized_current_hp_ratio: float = 0.0  # 物理
    spellblade_physical: float = 0.0
    spellblade_magic: float = 0.0
    spellblade_cooldown: float = 0.0         # 0 = 無魔法彎刀
    armor_shred: float = 0.0                 # 目標護甲削減比例，先於穿透
    magic_shred: float = 0.0                 # 目標魔抗削減比例，先於穿透（凱爾 Q）
    bonus_hp_amp: float = 0.0                # 多明尼克：最大增傷
    bonus_hp_amp_cap: float = 0.0            # 達到最大增傷所需的目標額外生命
    damage_amp: float = 1.0
    execute_threshold: float = 0.0
    spell_window_physical: float = 0.0
    spell_window_magic: float = 0.0
    spell_window_missing_hp_magic_ratio: float = 0.0  # 凱爾 E 主動：× 目標最大生命
    window_casts: float = 0.0                # 窗口內技能施放總次數（魔法彎刀觸發）
    window_seconds: float = 0.0              # 0 = 無技能模型，使用泛用基準技能


NO_MODIFIERS = AttackModifiers()
_MODIFIER_DEFAULTS = {f.name: f.default for f in fields(AttackModifiers)}


@dataclass(frozen=True)
class CombatProfile:
    """英雄在指定等級、指定出裝下的總戰鬥屬性（已聚合、已套上限、已套被動與技能）。"""

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
    modifiers: AttackModifiers = field(default=NO_MODIFIERS)


@dataclass
class StatSheet:
    """profile() 計算中途的可變屬性表 —— 被動與技能在這上面做屬性轉換。"""

    base_ad: float
    bonus_ad: float
    ap: float
    attack_speed_bonus: float   # ％：等級成長 + 裝備 + 被動 + 技能
    crit_chance: float
    crit_damage_bonus: float
    armor_pen_percent: float
    armor_pen_flat: float
    magic_pen_percent: float
    magic_pen_flat: float
    ability_haste: float
    base_hp: float
    bonus_hp: float
    armor: float
    magic_resist: float

    def add_percent_penetration(self, armor: float = 0.0, magic: float = 0.0) -> None:
        """多個 % 穿透相乘疊加：(1−a)(1−b)。參數為比例（0.3 = 30%）。"""
        self.armor_pen_percent = 100 * (1 - (1 - self.armor_pen_percent / 100) * (1 - armor))
        self.magic_pen_percent = 100 * (1 - (1 - self.magic_pen_percent / 100) * (1 - magic))

    @property
    def crit_multiplier(self) -> float:
        """總暴擊傷害倍率（基礎 1.75 + 裝備暴傷）—— 公式屬性代碼 9。"""
        return 1 + BASE_CRIT_BONUS + self.crit_damage_bonus / 100

    def formula_stats(self) -> dict[tuple[FormulaStat, StatPart], float]:
        return {
            (FormulaStat.AD, StatPart.TOTAL): self.base_ad + self.bonus_ad,
            (FormulaStat.AD, StatPart.BASE): self.base_ad,
            (FormulaStat.AD, StatPart.BONUS): self.bonus_ad,
            (FormulaStat.AP, StatPart.TOTAL): self.ap,
            (FormulaStat.AP, StatPart.BASE): 0.0,
            (FormulaStat.AP, StatPart.BONUS): self.ap,
            (FormulaStat.HP, StatPart.TOTAL): self.base_hp + self.bonus_hp,
            (FormulaStat.HP, StatPart.BASE): self.base_hp,
            (FormulaStat.HP, StatPart.BONUS): self.bonus_hp,
            (FormulaStat.CRIT_DAMAGE, StatPart.TOTAL): self.crit_multiplier,
        }


class _ModifierWriter:
    """修飾量以具名欄位寫入，拼錯即 KeyError。子類提供 self.modifiers。"""

    modifiers: dict[str, float]

    def add(self, **amounts: float) -> None:
        for name, amount in amounts.items():
            self.modifiers[_modifier_key(name)] += amount

    def scale(self, **factors: float) -> None:
        for name, factor in factors.items():
            self.modifiers[_modifier_key(name)] *= factor

    def set(self, **values: float) -> None:
        for name, value in values.items():
            self.modifiers[_modifier_key(name)] = value

    def raise_to(self, **values: float) -> None:
        for name, value in values.items():
            key = _modifier_key(name)
            self.modifiers[key] = max(self.modifiers[key], value)

    def shred_armor(self, fraction: float) -> None:
        current = self.modifiers["armor_shred"]
        self.modifiers["armor_shred"] = 1 - (1 - current) * (1 - fraction)

    def shred_magic(self, fraction: float) -> None:
        current = self.modifiers["magic_shred"]
        self.modifiers["magic_shred"] = 1 - (1 - current) * (1 - fraction)


def _modifier_key(name: str) -> str:
    if name not in _MODIFIER_DEFAULTS:
        raise KeyError(f"AttackModifiers 沒有欄位 {name!r}")
    return name


@dataclass
class EffectContext(_ModifierWriter):
    """一件裝備的被動套用時看到的一切。"""

    item: Item
    level: int
    is_ranged: bool
    fight: FightAssumptions
    stats: StatSheet
    modifiers: dict[str, float]

    def dv(self, name: str) -> float:
        return self.item.data_value_map[name]

    def calc(self, name: str) -> float:
        return evaluate(
            self.item.calculation_map[name],
            FormulaContext(
                level=self.level,
                is_ranged=self.is_ranged,
                data_values=self.item.data_value_map,
                calculations=self.item.calculation_map,
                stats=self.stats.formula_stats(),
            ),
        )


@dataclass
class KitContext(_ModifierWriter):
    """英雄技能模型套用時看到的一切（spec champion-kits §3、§8）。"""

    spells: ChampionSpells
    settings: KitSettings
    ranks: Mapping[str, int]
    level: int
    is_ranged: bool
    fight: FightAssumptions
    stats: StatSheet
    modifiers: dict[str, float]

    @property
    def window(self) -> float:
        return self.fight.fight_duration_seconds

    @property
    def crit_chance(self) -> float:
        """0–1，已套上限。"""
        return min(CRIT_CHANCE_CAP, self.stats.crit_chance) / 100

    @property
    def crit_multiplier(self) -> float:
        return self.stats.crit_multiplier

    def rank(self, slot: str) -> int:
        return self.ranks[slot]

    def assume(self, name: str) -> float:
        return self.settings.assumptions[name]

    def spell(self, name: str) -> SpellData:
        spell = self.spells.spell(name)
        if spell is None:  # binder 已保證存在；到這裡代表註冊表與綁定宣告不一致
            raise KeyError(f"{self.spells.key} 沒有技能 {name!r}")
        return spell

    def dv(self, spell: str, name: str, rank: int) -> float:
        return self.spell(spell).values_at(rank)[name]

    def calc(self, spell: str, name: str, rank: int) -> float:
        data = self.spell(spell)
        return evaluate(
            data.calculation_map[name],
            FormulaContext(
                level=self.level,
                is_ranged=self.is_ranged,
                data_values=data.values_at(rank),
                calculations=data.calculation_map,
                stats=self.stats.formula_stats(),
            ),
        )

    def casts(self, spell: str, rank: int) -> int:
        """窗口內施放次數 = 1 + floor(時長 ÷ 實際冷卻)；未學（等級 0）不施放。"""
        if rank <= 0:
            return 0
        cooldown = self.spell(spell).cooldown(rank)
        if cooldown <= 0:
            return 1
        effective = cooldown / (1 + self.stats.ability_haste / 100)
        return 1 + floor(self.window / effective)

    def record(
        self,
        times: int,
        *,
        physical: float = 0.0,
        magic: float = 0.0,
        missing_hp_magic_ratio: float = 0.0,
    ) -> int:
        """登記 times 次施放：每次的傷害累加進窗口總量，次數供魔法彎刀觸發。"""
        self.add(
            spell_window_physical=times * physical,
            spell_window_magic=times * magic,
            spell_window_missing_hp_magic_ratio=times * missing_hp_magic_ratio,
            window_casts=times,
        )
        return times

    def cast(self, spell: str, rank: int, **damage: float) -> int:
        return self.record(self.casts(spell, rank), **damage)

    def uptime(self, casts: int, duration: float) -> float:
        """增益持續率 = min(1, 施放次數 × 持續秒數 ÷ 時長) —— 線性加權的近似。"""
        return min(1.0, casts * duration / self.window)


class ItemEffect(Protocol):
    """裝備被動。stage 小的先套用：屬性轉換 → 乘算 → 讀最終屬性的傷害類。"""

    @property
    def stage(self) -> int: ...

    def apply(self, ctx: EffectContext) -> None: ...


class ChampionKitView(Protocol):
    """已綁定的英雄技能模型（實作在 champion_kits.BoundKit）。"""

    @property
    def spells(self) -> ChampionSpells: ...

    @property
    def settings(self) -> KitSettings: ...

    def is_ranged(self, level: int, base: ChampionBaseStats) -> bool: ...

    def apply(self, ctx: KitContext) -> None: ...


class CombatModel:
    def __init__(
        self,
        spell_proxy: SpellProxy,
        fight: FightAssumptions | None = None,
        effects: Mapping[int, ItemEffect] | None = None,
    ) -> None:
        self._proxy = spell_proxy
        self._fight = fight
        self._effects = dict(effects or {})
        self._kit: ChampionKitView | None = None
        if self._effects and fight is None:
            raise ValueError("帶被動效果的 CombatModel 必須提供 FightAssumptions")

    @property
    def effect_ids(self) -> frozenset[int]:
        return frozenset(self._effects)

    @property
    def kit(self) -> ChampionKitView | None:
        return self._kit

    def for_champion(self, kit: ChampionKitView | None) -> CombatModel:
        """帶英雄技能模型的視圖；None 時回傳自身（泛用基準技能）。"""
        if kit is None:
            return self
        if self._fight is None:
            raise ValueError("帶技能模型的 CombatModel 必須提供 FightAssumptions")
        view = copy.copy(self)
        view._kit = kit
        return view

    def profile(
        self, base: ChampionBaseStats, level: int, items: Sequence[Item]
    ) -> CombatProfile:
        totals: dict[StatKey, float] = {}
        for it in items:
            for line in it.stats:
                totals[line.stat] = totals.get(line.stat, 0.0) + line.amount
        g = growth_factor(level)
        sheet = StatSheet(
            base_ad=base.attack_damage + base.attack_damage_growth * g,
            bonus_ad=totals.get(StatKey.AD, 0.0),
            ap=totals.get(StatKey.AP, 0.0),
            attack_speed_bonus=base.attack_speed_growth * g + totals.get(StatKey.ATTACK_SPEED, 0.0),
            crit_chance=totals.get(StatKey.CRIT_CHANCE, 0.0),
            crit_damage_bonus=totals.get(StatKey.CRIT_DAMAGE, 0.0),
            armor_pen_percent=totals.get(StatKey.ARMOR_PEN_PERCENT, 0.0),
            armor_pen_flat=totals.get(StatKey.ARMOR_PEN_FLAT, 0.0),
            magic_pen_percent=totals.get(StatKey.MAGIC_PEN_PERCENT, 0.0),
            magic_pen_flat=totals.get(StatKey.MAGIC_PEN_FLAT, 0.0),
            ability_haste=totals.get(StatKey.ABILITY_HASTE, 0.0),
            base_hp=base.hp + base.hp_growth * g,
            bonus_hp=totals.get(StatKey.HP, 0.0),
            armor=base.armor + base.armor_growth * g + totals.get(StatKey.ARMOR, 0.0),
            magic_resist=base.magic_resist
            + base.magic_resist_growth * g
            + totals.get(StatKey.MAGIC_RESIST, 0.0),
        )

        kit = self._kit
        # 遠近程先決定：裝備被動（破敗等）的數值依此切換；凱爾 6 級起靠被動變遠程。
        is_ranged = kit.is_ranged(level, base) if kit is not None else base.is_ranged
        modifiers = NO_MODIFIERS
        active = self._active_effects(items)
        if active or kit is not None:
            assert self._fight is not None  # 建構子與 for_champion 已保證
            values = dict(_MODIFIER_DEFAULTS)
            for effect, item in active:
                effect.apply(EffectContext(item, level, is_ranged, self._fight, sheet, values))
            if kit is not None:
                values["window_seconds"] = self._fight.fight_duration_seconds
                kit.apply(
                    KitContext(
                        spells=kit.spells,
                        settings=kit.settings,
                        ranks=skill_ranks(level, kit.settings.skill_order),
                        level=level,
                        is_ranged=is_ranged,
                        fight=self._fight,
                        stats=sheet,
                        modifiers=values,
                    )
                )
            modifiers = AttackModifiers(**values)

        attack_speed = base.attack_speed * (1 + sheet.attack_speed_bonus / 100)
        return CombatProfile(
            attack_damage=sheet.base_ad + sheet.bonus_ad,
            attack_speed=min(AS_CAP, attack_speed),
            crit_chance=min(CRIT_CHANCE_CAP, sheet.crit_chance),
            crit_damage_bonus=sheet.crit_damage_bonus,
            armor_pen_percent=sheet.armor_pen_percent,
            armor_pen_flat=sheet.armor_pen_flat,
            ap=sheet.ap,
            magic_pen_percent=sheet.magic_pen_percent,
            magic_pen_flat=sheet.magic_pen_flat,
            ability_haste=sheet.ability_haste,
            hp=sheet.base_hp + sheet.bonus_hp,
            armor=sheet.armor,
            magic_resist=sheet.magic_resist,
            modifiers=modifiers,
        )

    def _active_effects(self, items: Sequence[Item]) -> list[tuple[ItemEffect, Item]]:
        """唯一被動：同一件裝備重複出現只套用一次。依 stage 穩定排序。"""
        seen: set[int] = set()
        active: list[tuple[ItemEffect, Item]] = []
        for item in items:
            effect = self._effects.get(item.item_id)
            if effect is None or item.item_id in seen:
                continue
            seen.add(item.item_id)
            active.append((effect, item))
        active.sort(key=lambda pair: pair[0].stage)
        return active

    def total_dps(self, profile: CombatProfile, target: TargetProfile) -> float:
        """(普攻 + 魔法彎刀 + 技能) × 增傷 × 斬殺係數。純防裝在此自然趨零。"""
        m = profile.modifiers
        crit_factor = 1 + (profile.crit_chance / 100) * (
            BASE_CRIT_BONUS + profile.crit_damage_bonus / 100
        )
        effective_armor = max(
            0.0,
            target.armor * (1 - m.armor_shred) * (1 - profile.armor_pen_percent / 100)
            - profile.armor_pen_flat,
        )  # Riot 規則：削甲 → % 穿透 → 穿甲，且不為負
        physical = 100 / (100 + effective_armor)
        magical = 100 / (100 + self._effective_mr(profile, target))

        per_attack_physical = (
            profile.attack_damage * crit_factor   # 命中特效與普攻附加不吃暴擊
            + (m.physical_on_hit + m.on_hit_current_hp_ratio * target.hp) * m.on_hit_multiplier
            + m.physical_per_attack
            + m.energized_physical
            + m.energized_current_hp_ratio * target.hp
        )
        per_attack_magic = (
            m.magic_on_hit * m.on_hit_multiplier + m.magic_per_attack + m.energized_magic
        )
        aa_dps = profile.attack_speed * (
            per_attack_physical * physical + per_attack_magic * magical
        )

        if m.window_seconds > 0:
            spell_dps = (
                m.spell_window_physical * physical
                + (m.spell_window_magic + m.spell_window_missing_hp_magic_ratio * target.hp) * magical
            ) / m.window_seconds
        else:
            spell_dps = self._spell_dps(profile, target)

        spellblade_dps = 0.0
        if m.spellblade_cooldown > 0:
            if m.window_seconds > 0:
                # 真實施放：窗口內施放次數，受彎刀冷卻上限約束（spec champion-kits §3）
                procs = min(m.window_casts, m.window_seconds / m.spellblade_cooldown)
                rate = procs / m.window_seconds
            else:
                rate = 1 / max(m.spellblade_cooldown, self._cast_cooldown(profile))
            spellblade_dps = rate * (m.spellblade_physical * physical + m.spellblade_magic * magical)

        amp = m.damage_amp
        if m.bonus_hp_amp_cap > 0:
            amp *= 1 + m.bonus_hp_amp * min(1.0, target.bonus_hp / m.bonus_hp_amp_cap)
        execute = 1 / (1 - m.execute_threshold)
        return (aa_dps + spellblade_dps + spell_dps) * amp * execute

    def _effective_mr(self, profile: CombatProfile, target: TargetProfile) -> float:
        return max(
            0.0,
            target.magic_resist
            * (1 - profile.modifiers.magic_shred)
            * (1 - profile.magic_pen_percent / 100)
            - profile.magic_pen_flat,
        )

    def _cast_cooldown(self, profile: CombatProfile) -> float:
        return self._proxy.base_cooldown / (1 + profile.ability_haste / 100)

    def _spell_dps(self, profile: CombatProfile, target: TargetProfile) -> float:
        """泛用基準技能：代表「每隻英雄都有的泛用技能循環」，恆計入（無 kit 的英雄）。

        常數在邊際比較中自然抵銷 —— AP 件只得到自己的倍率份額
        （曾有過 AP>0 閘門，讓 435g 增幅典籍繼承整段基準傷而霸榜）；
        魔穿與技能加速則合理作用於基準傷（AD 英雄的技能也有基礎傷）。
        """
        burst = (self._proxy.base_damage + self._proxy.ap_ratio * profile.ap) * 100 / (
            100 + self._effective_mr(profile, target)
        )
        return burst / self._cast_cooldown(profile)

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
