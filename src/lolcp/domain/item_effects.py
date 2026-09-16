"""裝備被動效果（spec 2026-09-15 §5）。

數字讀資料（data values／公式樹），觸發邏輯手寫在這裡。每個效果以
裝備 ID 註冊（主 spec §3.5：絕不以名稱查找），並宣告它需要的名稱；
ItemEffectBinder 在組裝時預檢一次，缺名或公式不支援 → 記入診斷、該件停用。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum

from lolcp.domain.combat import EffectContext
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Item
from lolcp.domain.formulas import problems as formula_problems

STAGE_CONVERSION = 0   # 屬性轉換
STAGE_MULTIPLIER = 1   # 死亡之帽：在所有 AP 加總與轉換之後
STAGE_DAMAGE = 2       # 讀最終屬性的傷害類

# 鬼索「滿層時，每三下普攻會附加命中效果兩次」—— 出自描述文字，資料無此數值。
GUINSOO_PHANTOM_EVERY = 3


class EffectCategory(Enum):
    STAT_CONVERSION = "屬性轉換"
    ON_HIT = "命中特效"
    ENERGIZED = "充能普攻"
    TARGET = "削弱目標"
    SPELLBLADE = "魔法彎刀"


@dataclass(frozen=True)
class ItemEffect:
    category: EffectCategory
    stage: int
    apply: Callable[[EffectContext], None]
    data_values: tuple[str, ...] = ()
    calculations: tuple[str, ...] = ()

    def problems(self, item: Item) -> tuple[str, ...]:
        dv, calcs = item.data_value_map, item.calculation_map
        found: list[str] = [f"data value {n}" for n in self.data_values if n not in dv]
        for name in self.calculations:
            if name not in calcs:
                found.append(f"calculation {name}")
            else:
                found.extend(formula_problems(calcs[name], dv, calcs))
        return tuple(dict.fromkeys(found))


@dataclass(frozen=True)
class PassiveStatus:
    """詳情面板的被動狀態：已建模、綁定失敗（已停用）、未建模 —— 三者不可混為一談。"""

    category: EffectCategory | None      # None = 本版本未建模
    missing: tuple[str, ...] = ()        # 非空 = 有建模但綁定失敗

    @property
    def modelled(self) -> bool:
        return self.category is not None and not self.missing


def passive_status(
    item_id: int,
    bound: Mapping[int, ItemEffect],
    unbound: Mapping[int, tuple[str, ...]],
) -> PassiveStatus:
    if item_id in bound:
        return PassiveStatus(bound[item_id].category)
    if item_id in unbound and item_id in EFFECTS:
        return PassiveStatus(EFFECTS[item_id].category, missing=unbound[item_id])
    return PassiveStatus(None)


class ItemEffectBinder:
    def __init__(self, diagnostics: Diagnostics) -> None:
        self._diagnostics = diagnostics

    def bind(self, items: Iterable[Item]) -> dict[int, ItemEffect]:
        bound: dict[int, ItemEffect] = {}
        for item in items:
            effect = EFFECTS.get(item.item_id)
            if effect is None:
                continue
            found = effect.problems(item)
            if found:
                self._diagnostics.unbound_item_effect(item.item_id, found)
                continue
            bound[item.item_id] = effect
        return bound


# ---- 屬性轉換（§5.1）----

def _steraks(ctx: EffectContext) -> None:
    ctx.stats.bonus_ad += ctx.calc("BonusAD")            # 基礎 AD × ADtoAD


def _overlords(ctx: EffectContext) -> None:
    # 「報應」吃自身已損失生命 —— 自身血量不在模型內，不計。
    ctx.stats.bonus_ad += ctx.dv("HPToADPercentage") * ctx.stats.bonus_hp


def _riftmaker(ctx: EffectContext) -> None:
    ctx.stats.ap += ctx.dv("HealthToAPConversionPercent") * ctx.stats.bonus_hp
    ctx.scale(damage_amp=1 + ctx.dv("EternityDamageIncreaseMax"))  # 視為疊滿


def flurry_uptime(
    *,
    cooldown: float,
    duration: float,
    per_attack: float,
    per_crit: float,
    attack_speed: float,
    crit_chance: float,
) -> float:
    """雲陶狂箭 Flurry 的持續率（spec 2026-09-16 §3.3）。

    每次命中減 per_attack 秒、暴擊改減 per_crit 秒 → 每秒縮減
    攻速 × (per_attack + 暴擊率 × (per_crit − per_attack))；
    就緒時間 = 冷卻 ÷ (1 + 每秒縮減)；持續率 = 持續 ÷ max(持續, 就緒)。
    """
    per_second = attack_speed * (per_attack + crit_chance * (per_crit - per_attack))
    ready_in = cooldown / (1 + per_second)
    return min(1.0, duration / max(duration, ready_in))


def _yun_tal(ctx: EffectContext) -> None:
    """暴擊先加（Flurry 冷卻縮減吃暴擊），再以當下攻速估持續率，最後才加攻速。

    近似：同階段的其他攻速（鬼索）與技能攻速（達瑞文 W 等，kit 在裝備之後）
    尚未計入估算 —— 會略為低估持續率。
    """
    ctx.stats.crit_chance += ctx.dv("CritMax")            # 百分點；視為疊滿
    uptime = flurry_uptime(
        cooldown=ctx.dv("Cooldown"),
        duration=ctx.dv("ASDuration"),
        per_attack=ctx.dv("AACDR"),
        per_crit=ctx.dv("CritCDR"),
        attack_speed=ctx.stats.attack_speed,
        crit_chance=min(100.0, ctx.stats.crit_chance) / 100,
    )
    ctx.stats.attack_speed_bonus += ctx.dv("ASMod") * 100 * uptime


def _rabadon(ctx: EffectContext) -> None:
    ctx.stats.ap *= 1 + ctx.dv("APAmp")


# ---- 命中特效（§5.2）----

def _botrk(ctx: EffectContext) -> None:
    ratio = ctx.dv("RangedValue") if ctx.is_ranged else ctx.dv("MeleeValue")
    ctx.add(on_hit_current_hp_ratio=ratio * ctx.fight.average_current_hp_ratio)


def _kraken(ctx: EffectContext) -> None:
    """增傷隨已損生命線性增加至 MaxAmpNumber —— 線性為假設。"""
    missing = 1 - ctx.fight.average_current_hp_ratio
    amp = 1 + (ctx.dv("MaxAmpNumber") - 1) * missing
    ctx.add(physical_on_hit=ctx.calc("DamageAmount") * amp / ctx.dv("AttackCount"))


def _nashors(ctx: EffectContext) -> None:
    ctx.add(magic_on_hit=ctx.calc("TotalOnHitDamage"))


def _wits_end(ctx: EffectContext) -> None:
    ctx.add(magic_on_hit=ctx.calc("OnHitDamage"))


def _terminus(ctx: EffectContext) -> None:
    """黑暗模式疊滿 30% 雙穿、光明模式疊滿雙抗 —— 整場平均視為兩者皆滿。"""
    ctx.add(magic_on_hit=ctx.calc("OnHitDamage"))
    pen = ctx.dv("PenMax")
    ctx.stats.add_percent_penetration(armor=pen, magic=pen)
    resist = ctx.calc("ARMRMaxScaling")
    ctx.stats.armor += resist
    ctx.stats.magic_resist += resist


def _guinsoo(ctx: EffectContext) -> None:
    ctx.stats.attack_speed_bonus += ctx.dv("AttackSpeedPerStack") * ctx.dv("MaxStacks") * 100
    ctx.add(magic_on_hit=ctx.dv("OnHitDamage"))
    ctx.scale(on_hit_multiplier=(GUINSOO_PHANTOM_EVERY + 1) / GUINSOO_PHANTOM_EVERY)


# ---- 充能普攻（§5.3）----

def _energized(
    ctx: EffectContext, *, physical: float = 0.0, magic: float = 0.0, current_hp: float = 0.0
) -> None:
    every = ctx.fight.energized_attacks
    ctx.add(
        energized_physical=physical / every,
        energized_magic=magic / every,
        energized_current_hp_ratio=current_hp * ctx.fight.average_current_hp_ratio / every,
    )


def _stormrazor(ctx: EffectContext) -> None:
    _energized(ctx, magic=ctx.calc("TotalProcDamage"))


def _firecannon(ctx: EffectContext) -> None:
    _energized(ctx, magic=ctx.dv("BonusDamage"))


def _statikk(ctx: EffectContext) -> None:
    # 只計主目標；「電擊」加速充能不計。
    _energized(ctx, magic=ctx.dv("ChainDamage"))


def _voltaic(ctx: EffectContext) -> None:
    # PercentCurrentHP* 是百分點（7 = 7%），不是比例。穿甲增益不計。
    points = ctx.dv("PercentCurrentHPRanged") if ctx.is_ranged else ctx.dv("PercentCurrentHPMelee")
    _energized(ctx, current_hp=points / 100)


# ---- 削弱目標（§5.4）----

def _black_cleaver(ctx: EffectContext) -> None:
    ctx.shred_armor(ctx.dv("ShredPerStack") * ctx.dv("MaxStacks"))  # 視為疊滿


def _dominik(ctx: EffectContext) -> None:
    ctx.set(bonus_hp_amp=ctx.dv("MaxBonusDamagePercent"), bonus_hp_amp_cap=ctx.dv("MaxBonusHealth"))


def _collector(ctx: EffectContext) -> None:
    ctx.raise_to(execute_threshold=ctx.dv("ExecuteThreshold"))


# ---- 魔法彎刀（§5.5）----

def _spellblade(*, magic: bool) -> Callable[[EffectContext], None]:
    def apply(ctx: EffectContext) -> None:
        damage = ctx.calc("SpellbladeDamage")
        ctx.set(
            spellblade_physical=0.0 if magic else damage,
            spellblade_magic=damage if magic else 0.0,
            spellblade_cooldown=ctx.dv("SpellbladeCooldown"),
        )

    return apply


_SPELLBLADE_NEEDS = {"calculations": ("SpellbladeDamage",), "data_values": ("SpellbladeCooldown",)}

EFFECTS: dict[int, ItemEffect] = {
    # 屬性轉換
    3053: ItemEffect(EffectCategory.STAT_CONVERSION, STAGE_CONVERSION, _steraks,
                     calculations=("BonusAD",)),
    2501: ItemEffect(EffectCategory.STAT_CONVERSION, STAGE_CONVERSION, _overlords,
                     data_values=("HPToADPercentage",)),
    4633: ItemEffect(EffectCategory.STAT_CONVERSION, STAGE_CONVERSION, _riftmaker,
                     data_values=("HealthToAPConversionPercent", "EternityDamageIncreaseMax")),
    # 傷害階段：Flurry 持續率要讀得到裝備提供的攻速（spec 2026-09-16 §3.3）
    3032: ItemEffect(EffectCategory.STAT_CONVERSION, STAGE_DAMAGE, _yun_tal,
                     data_values=("CritMax", "ASMod", "Cooldown", "ASDuration", "AACDR", "CritCDR")),
    3089: ItemEffect(EffectCategory.STAT_CONVERSION, STAGE_MULTIPLIER, _rabadon,
                     data_values=("APAmp",)),
    # 命中特效
    3153: ItemEffect(EffectCategory.ON_HIT, STAGE_DAMAGE, _botrk,
                     data_values=("RangedValue", "MeleeValue")),
    6672: ItemEffect(EffectCategory.ON_HIT, STAGE_DAMAGE, _kraken,
                     data_values=("MaxAmpNumber", "AttackCount"), calculations=("DamageAmount",)),
    3115: ItemEffect(EffectCategory.ON_HIT, STAGE_DAMAGE, _nashors,
                     calculations=("TotalOnHitDamage",)),
    3091: ItemEffect(EffectCategory.ON_HIT, STAGE_DAMAGE, _wits_end,
                     calculations=("OnHitDamage",)),
    3302: ItemEffect(EffectCategory.ON_HIT, STAGE_DAMAGE, _terminus,
                     data_values=("PenMax",), calculations=("OnHitDamage", "ARMRMaxScaling")),
    3124: ItemEffect(EffectCategory.ON_HIT, STAGE_DAMAGE, _guinsoo,
                     data_values=("OnHitDamage", "AttackSpeedPerStack", "MaxStacks")),
    # 充能普攻
    3097: ItemEffect(EffectCategory.ENERGIZED, STAGE_DAMAGE, _stormrazor,
                     calculations=("TotalProcDamage",)),
    3094: ItemEffect(EffectCategory.ENERGIZED, STAGE_DAMAGE, _firecannon,
                     data_values=("BonusDamage",)),
    3087: ItemEffect(EffectCategory.ENERGIZED, STAGE_DAMAGE, _statikk,
                     data_values=("ChainDamage",)),
    6699: ItemEffect(EffectCategory.ENERGIZED, STAGE_DAMAGE, _voltaic,
                     data_values=("PercentCurrentHPRanged", "PercentCurrentHPMelee")),
    # 削弱目標
    3071: ItemEffect(EffectCategory.TARGET, STAGE_DAMAGE, _black_cleaver,
                     data_values=("ShredPerStack", "MaxStacks")),
    3036: ItemEffect(EffectCategory.TARGET, STAGE_DAMAGE, _dominik,
                     data_values=("MaxBonusDamagePercent", "MaxBonusHealth")),
    6676: ItemEffect(EffectCategory.TARGET, STAGE_DAMAGE, _collector,
                     data_values=("ExecuteThreshold",)),
    # 魔法彎刀（bin 群組上限 1，同時最多一件）
    3078: ItemEffect(EffectCategory.SPELLBLADE, STAGE_DAMAGE, _spellblade(magic=False), **_SPELLBLADE_NEEDS),
    6662: ItemEffect(EffectCategory.SPELLBLADE, STAGE_DAMAGE, _spellblade(magic=False), **_SPELLBLADE_NEEDS),
    3100: ItemEffect(EffectCategory.SPELLBLADE, STAGE_DAMAGE, _spellblade(magic=True), **_SPELLBLADE_NEEDS),
    2510: ItemEffect(EffectCategory.SPELLBLADE, STAGE_DAMAGE, _spellblade(magic=True), **_SPELLBLADE_NEEDS),
}
