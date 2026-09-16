"""英雄技能模型（spec 2026-09-15 champion-kits §6）。

數字讀英雄 bin（每級數值、冷卻、公式樹），機制手寫在這裡；操作假設讀
config/kits/<Key>.toml（預設熟練玩家）。每個 kit 宣告它需要的技能與名稱，
ChampionKitBinder 在組裝時預檢一次：缺名或公式不支援 → 記入診斷、該英雄
退回泛用基準技能。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import floor

from lolcp.domain.combat import KitContext
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import ChampionBaseStats
from lolcp.domain.formulas import problems as formula_problems
from lolcp.domain.kit_settings import KitSettings
from lolcp.domain.spells import ChampionSpells

# 煞蜜拉 R：描述「shooting all enemies surrounding her 10 times over 2 seconds」——
# 發數與施放時間出自描述文字，bin 無此數值。
SAMIRA_R_SHOTS = 10
SAMIRA_R_CAST_SECONDS = 2.0


@dataclass(frozen=True)
class SpellNeeds:
    spell: str
    data_values: tuple[str, ...] = ()
    calculations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChampionKit:
    key: str
    needs: tuple[SpellNeeds, ...]
    apply: Callable[[KitContext], None]
    ranged_from: Callable[[ChampionSpells, int, ChampionBaseStats], bool] | None = None

    def problems(self, spells: ChampionSpells) -> tuple[str, ...]:
        found: list[str] = []
        for need in self.needs:
            spell = spells.spell(need.spell)
            if spell is None:
                found.append(f"spell {need.spell}")
                continue
            found += [f"data value {need.spell}.{n}" for n in need.data_values if not spell.has_value(n)]
            for name in need.calculations:
                calc = spell.calculation_map.get(name)
                if calc is None:
                    found.append(f"calculation {need.spell}.{name}")
                    continue
                found += [
                    f"{need.spell}.{name}: {p}"
                    for p in formula_problems(calc, spell.values_at(1), spell.calculation_map)
                ]
        return tuple(dict.fromkeys(found))


@dataclass(frozen=True)
class BoundKit:
    """已綁定的 kit：技能資料＋操作假設。滿足 combat.ChampionKitView。"""

    kit: ChampionKit
    spells: ChampionSpells
    settings: KitSettings

    @property
    def attack_speed_ratio(self) -> float | None:
        """裝備攻速加成的乘數（spec 2026-09-16 §3.1）；bin 無記錄時 None。"""
        return self.spells.attack_speed_ratio

    def is_ranged(self, level: int, base: ChampionBaseStats) -> bool:
        if self.kit.ranged_from is None:
            return base.is_ranged
        return self.kit.ranged_from(self.spells, level, base)

    def apply(self, ctx: KitContext) -> None:
        self.kit.apply(ctx)


class ChampionKitBinder:
    def __init__(self, diagnostics: Diagnostics) -> None:
        self._diagnostics = diagnostics

    def bind(
        self,
        spells_for: Callable[[str], ChampionSpells | None],
        settings: Mapping[str, KitSettings],
    ) -> dict[str, BoundKit]:
        """缺技能 bin 的英雄略過 —— repository 已留痕，此處不重複記錄。"""
        bound: dict[str, BoundKit] = {}
        for key, kit in KITS.items():
            spells = spells_for(key)
            if spells is None:
                continue
            found = kit.problems(spells)
            if found:
                self._diagnostics.unbound_champion_kit(key, found)
                continue
            bound[key] = BoundKit(kit, spells, settings[key])
        return bound


def _ranks(k: KitContext) -> tuple[int, int, int, int]:
    return k.rank("Q"), k.rank("W"), k.rank("E"), k.rank("R")


# ---- 達瑞文（§6.1）----

def _draven(k: KitContext) -> None:
    q, w, e, r = _ranks(k)
    # Q：強化普攻（不吃暴擊、非命中特效）；接住飛斧自動再準備，施放次數依冷卻計
    k.cast("DravenSpinning", q)
    if q:
        k.add(physical_per_attack=k.calc("DravenSpinning", "TotalDamage", q)
              * k.assume("q_empowered_attack_ratio"))
    # W：攻速（接斧頭重置冷卻 → 持續率為操作假設）
    k.cast("DravenFury", w)
    if w:
        k.stats.attack_speed_bonus += k.dv("DravenFury", "Temp_AS", w) * k.assume("w_uptime")
    if e:
        k.cast("DravenDoubleShot", e, physical=k.calc("DravenDoubleShot", "TotalDamage", e))
    if r:
        # 去程與回程各命中一次；單體不衰減
        k.cast("DravenRCast", r, physical=2 * k.calc("DravenRCast", "RCalculatedDamage", r))


# ---- 凱爾（§6.2）----

def _kayle_ranged(spells: ChampionSpells, level: int, base: ChampionBaseStats) -> bool:
    passive = spells.spell("KaylePassive")
    return passive is not None and level >= passive.values_at(0)["LevelForPassiveRank1"]


def _kayle(k: KitContext) -> None:
    passive = "KaylePassive"
    # 攻速疊層視為疊滿；11 級起普攻附劍氣（11–15 級需疊滿，整場平均視為滿）
    k.stats.attack_speed_bonus += k.dv(passive, "EnrageASPerStack", 0) * k.dv(passive, "EnrageMaxStacks", 0)
    if k.level >= k.dv(passive, "LevelForPassiveRank2", 0):
        k.add(magic_per_attack=k.calc(passive, "PassiveWaveDamage", 0))

    q, w, e, r = _ranks(k)
    if e:
        k.add(magic_on_hit=k.calc("KayleE", "EPassiveTotalDamage", e))
        missing = 1 - k.fight.average_current_hp_ratio
        k.cast("KayleE", e,
               missing_hp_magic_ratio=k.calc("KayleE", "ActiveTotalExecuteDamage", e) * missing)
    if q:
        casts = k.cast("KayleQ", q, magic=k.calc("KayleQ", "TotalDamage", q))
        shred = k.dv("KayleQ", "ShredPercent", q) / 100 * k.uptime(casts, k.dv("KayleQ", "ShredDuration", q))
        k.shred_armor(shred)
        k.shred_magic(shred)
    k.cast("KayleW", w)   # 補血加速，無輸出；施放次數供魔法彎刀
    if r:
        k.cast("KayleR", r, magic=k.calc("KayleR", "TotalDamage", r))


# ---- 煞蜜拉（§6.3）----

def _samira(k: KitContext) -> None:
    k.add(magic_per_attack=k.assume("melee_attack_ratio") * k.calc("SamiraPassive", "BonusMeleeDamage", 0))
    q, w, e, r = _ranks(k)
    crit, multiplier = k.crit_chance, k.crit_multiplier
    if q:
        q_crit = 1 + crit * k.dv("SamiraQ", "CritDamageMod", q) * (multiplier - 1)
        k.cast("SamiraQ", q, physical=k.calc("SamiraQ", "DamageCalc", q) * q_crit)
    if w:
        k.cast("SamiraW", w, physical=2 * k.calc("SamiraW", "DamageCalc", w))   # 兩段
    if e:
        casts = k.cast("SamiraE", e, magic=k.calc("SamiraE", "DashDamage", e))
        uptime = k.uptime(casts, k.dv("SamiraE", "AttackSpeedDuration", e))
        k.stats.attack_speed_bonus += k.dv("SamiraE", "BonusAttackSpeed", e) * 100 * uptime
    if r:
        # 評分 S 才能放、放完清空：開場 combo_seconds 打到 S，之後每輪連段＋施放時間再放一次
        combo = k.assume("combo_seconds")
        times = 0 if combo > k.window else 1 + floor((k.window - combo) / (combo + SAMIRA_R_CAST_SECONDS))
        per_cast = SAMIRA_R_SHOTS * k.calc("SamiraR", "DamageCalc", r) * (1 + crit * (multiplier - 1))
        k.record(times, physical=per_cast)


KITS: dict[str, ChampionKit] = {
    "Draven": ChampionKit(
        key="Draven",
        needs=(
            SpellNeeds("DravenSpinning", calculations=("TotalDamage",)),
            SpellNeeds("DravenFury", data_values=("Temp_AS",)),
            SpellNeeds("DravenDoubleShot", calculations=("TotalDamage",)),
            SpellNeeds("DravenRCast", calculations=("RCalculatedDamage",)),
        ),
        apply=_draven,
    ),
    "Kayle": ChampionKit(
        key="Kayle",
        needs=(
            SpellNeeds("KaylePassive",
                       data_values=("LevelForPassiveRank1", "LevelForPassiveRank2",
                                    "EnrageASPerStack", "EnrageMaxStacks"),
                       calculations=("PassiveWaveDamage",)),
            SpellNeeds("KayleE", calculations=("EPassiveTotalDamage", "ActiveTotalExecuteDamage")),
            SpellNeeds("KayleQ", data_values=("ShredPercent", "ShredDuration"), calculations=("TotalDamage",)),
            SpellNeeds("KayleW"),
            SpellNeeds("KayleR", calculations=("TotalDamage",)),
        ),
        apply=_kayle,
        ranged_from=_kayle_ranged,
    ),
    "Samira": ChampionKit(
        key="Samira",
        needs=(
            SpellNeeds("SamiraPassive", calculations=("BonusMeleeDamage",)),
            SpellNeeds("SamiraQ", data_values=("CritDamageMod",), calculations=("DamageCalc",)),
            SpellNeeds("SamiraW", calculations=("DamageCalc",)),
            SpellNeeds("SamiraE", data_values=("BonusAttackSpeed", "AttackSpeedDuration"),
                       calculations=("DashDamage",)),
            SpellNeeds("SamiraR", calculations=("DamageCalc",)),
        ),
        apply=_samira,
    ),
}
