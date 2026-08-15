"""屬性種類與單位正規化。

單位正規化是本專案最容易靜默算錯的地方：bin 檔的百分比類屬性以分數儲存
（0.25 = 25%），而 `mFlatCritDamageMod` 帶 Flat 前綴卻也是分數。因此
NORMALIZE_X100 必須是明確列舉的常數集合，不得由欄位名前綴推導。
集合內容由 16.15.1 全裝備的實際值域掃描推定。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UnknownStatKeyError(ValueError):
    """設定檔出現無法辨識的屬性鍵名。"""

    def __init__(self, key: str) -> None:
        valid = ", ".join(sorted(s.config_key for s in StatKey))
        super().__init__(f"未知的屬性鍵名 {key!r}。合法選項：{valid}")
        self.key = key


class StatKey(Enum):
    # ---- 召喚峽谷可定價（11 種，有錨定基礎裝備）----
    AD = "AD"
    AP = "AP"
    HP = "HP"
    MANA = "MANA"
    ARMOR = "ARMOR"
    MAGIC_RESIST = "MAGIC_RESIST"
    CRIT_CHANCE = "CRIT_CHANCE"
    ATTACK_SPEED = "ATTACK_SPEED"
    ABILITY_HASTE = "ABILITY_HASTE"
    MOVE_SPEED_FLAT = "MOVE_SPEED_FLAT"
    BASE_HP_REGEN = "BASE_HP_REGEN"

    # ---- 召喚峽谷未定價 ----
    CRIT_DAMAGE = "CRIT_DAMAGE"
    HP_REGEN_FLAT = "HP_REGEN_FLAT"
    LIFE_STEAL = "LIFE_STEAL"
    MOVE_SPEED_PERCENT = "MOVE_SPEED_PERCENT"
    HEAL_SHIELD_POWER = "HEAL_SHIELD_POWER"
    TENACITY = "TENACITY"
    SLOW_RESIST = "SLOW_RESIST"
    MAGIC_PEN_FLAT = "MAGIC_PEN_FLAT"
    MAGIC_PEN_PERCENT = "MAGIC_PEN_PERCENT"
    ARMOR_PEN_PERCENT = "ARMOR_PEN_PERCENT"
    ARMOR_PEN_FLAT = "ARMOR_PEN_FLAT"    # 穿甲（PhysicalLethality），12 件
    OMNIVAMP = "OMNIVAMP"                # 全能吸血，6 件
    BASE_MP_REGEN = "BASE_MP_REGEN"      # 基礎魔力回復，19 件
    MP_REGEN_FLAT = "MP_REGEN_FLAT"      # 固定魔力回復，1 件

    # ---- 召喚峽谷未出現，但保留映射以偵測未知欄位（3 種）----
    COOLDOWN_REDUCTION = "COOLDOWN_REDUCTION"
    ATTACK_RANGE = "ATTACK_RANGE"
    ATTACK_SPEED_MULTIPLICATIVE = "ATTACK_SPEED_MULTIPLICATIVE"

    @property
    def config_key(self) -> str:
        return self.name.lower()

    @classmethod
    def from_config_key(cls, key: str) -> StatKey:
        try:
            return cls[key.upper()]
        except KeyError:
            raise UnknownStatKeyError(key) from None


# bin 欄位名 → StatKey。命名慣例有三種（見 2026-08-15 盲點修復 spec）：
#   mXxxMod（多數）、小寫開頭（flatMPPoolMod 等）、裸名（PhysicalLethality）。
BIN_FIELD_TO_STAT: dict[str, StatKey] = {
    "mFlatPhysicalDamageMod": StatKey.AD,
    "mFlatMagicDamageMod": StatKey.AP,
    "mFlatHPPoolMod": StatKey.HP,
    "mFlatArmorMod": StatKey.ARMOR,
    "mFlatSpellBlockMod": StatKey.MAGIC_RESIST,
    "mFlatCritChanceMod": StatKey.CRIT_CHANCE,
    "mPercentAttackSpeedMod": StatKey.ATTACK_SPEED,
    "mAbilityHasteMod": StatKey.ABILITY_HASTE,
    "mFlatMovementSpeedMod": StatKey.MOVE_SPEED_FLAT,
    "mPercentBaseHPRegenMod": StatKey.BASE_HP_REGEN,
    "mFlatCritDamageMod": StatKey.CRIT_DAMAGE,
    "mFlatHPRegenMod": StatKey.HP_REGEN_FLAT,
    "mPercentLifeStealMod": StatKey.LIFE_STEAL,
    "mPercentMovementSpeedMod": StatKey.MOVE_SPEED_PERCENT,
    "mPercentHealingAmountMod": StatKey.HEAL_SHIELD_POWER,
    "mPercentTenacityItemMod": StatKey.TENACITY,
    "mPercentSlowResistMod": StatKey.SLOW_RESIST,
    "mFlatMagicPenetrationMod": StatKey.MAGIC_PEN_FLAT,
    "mPercentMagicPenetrationMod": StatKey.MAGIC_PEN_PERCENT,
    "mPercentArmorPenetrationMod": StatKey.ARMOR_PEN_PERCENT,
    "mPercentCooldownMod": StatKey.COOLDOWN_REDUCTION,
    "mFlatArmorPenetrationMod": StatKey.ARMOR_PEN_FLAT,
    "mFlatAttackRangeMod": StatKey.ATTACK_RANGE,
    "mPercentMultiplicativeAttackSpeedMod": StatKey.ATTACK_SPEED_MULTIPLICATIVE,
    # ---- 第二、三種命名慣例（曾被靜默丟棄的盲點）----
    "PhysicalLethality": StatKey.ARMOR_PEN_FLAT,
    "PercentOmnivampMod": StatKey.OMNIVAMP,
    "percentBaseMPRegenMod": StatKey.BASE_MP_REGEN,
    "flatMPRegenMod": StatKey.MP_REGEN_FLAT,
    "flatMPPoolMod": StatKey.MANA,
}

# Data Dragon 的法力欄位。16.15.1 實測 bin（小寫 flatMPPoolMod）與 DD
# 各 15 件、完全重疊、零分歧；bin 優先、DD 補缺為防禦性分支。
DDRAGON_MANA_FIELD = "FlatMPPoolMod"

# 原始值為分數、需 ×100 轉為「以 1% 為單位」。
# 依 16.15.1 實際值域推定，非依欄位名前綴。
NORMALIZE_X100: frozenset[StatKey] = frozenset({
    StatKey.CRIT_CHANCE,
    StatKey.CRIT_DAMAGE,  # 帶 Flat 前綴卻是分數
    StatKey.ATTACK_SPEED,
    StatKey.ATTACK_SPEED_MULTIPLICATIVE,
    StatKey.BASE_HP_REGEN,
    StatKey.LIFE_STEAL,
    StatKey.MOVE_SPEED_PERCENT,
    StatKey.HEAL_SHIELD_POWER,
    StatKey.TENACITY,
    StatKey.SLOW_RESIST,
    StatKey.MAGIC_PEN_PERCENT,
    StatKey.ARMOR_PEN_PERCENT,
    StatKey.COOLDOWN_REDUCTION,
    StatKey.OMNIVAMP,        # 0.025 → 2.5%
    StatKey.BASE_MP_REGEN,   # 1.25 → 125%，與 BASE_HP_REGEN 同型
})

# 召喚峽谷標準 ID 裝備實際出現的 25 種屬性。
SR_STATS: frozenset[StatKey] = frozenset(
    set(StatKey) - {
        StatKey.COOLDOWN_REDUCTION,
        StatKey.ATTACK_RANGE,
        StatKey.ATTACK_SPEED_MULTIPLICATIVE,
    }
)


@dataclass(frozen=True, slots=True)
class StatLine:
    """一條已正規化的屬性。amount 一律為正規化後的數值。"""

    stat: StatKey
    amount: float


# Data Dragon 欄位名 → StatKey。用於補法力，以及與 bin 的一致性交叉檢查。
# Data Dragon 的 stats schema 只有 12 種欄位（缺技能加速、暴擊傷害、穿透等）。
DDRAGON_FIELD_TO_STAT: dict[str, StatKey] = {
    "FlatPhysicalDamageMod": StatKey.AD,
    "FlatMagicDamageMod": StatKey.AP,
    "FlatHPPoolMod": StatKey.HP,
    "FlatMPPoolMod": StatKey.MANA,
    "FlatArmorMod": StatKey.ARMOR,
    "FlatSpellBlockMod": StatKey.MAGIC_RESIST,
    "FlatCritChanceMod": StatKey.CRIT_CHANCE,
    "PercentAttackSpeedMod": StatKey.ATTACK_SPEED,
    "FlatMovementSpeedMod": StatKey.MOVE_SPEED_FLAT,
    "PercentMovementSpeedMod": StatKey.MOVE_SPEED_PERCENT,
    "PercentLifeStealMod": StatKey.LIFE_STEAL,
    "FlatHPRegenMod": StatKey.HP_REGEN_FLAT,
}

# bin 檔以 float32 儲存百分比（0.15 → 0.15000000596046448）。
# 乘 100 後殘留的表示誤差會讓單價變成 39.99999841 而非 40.0，
# 因此正規化後必須四捨五入。遊戲數值的真實精度遠低於 4 位小數。
NORMALIZED_PRECISION = 4


def normalize_amount(stat: StatKey, raw: float) -> float:
    """把原始值轉為正規化數值：百分比類以 1% 為單位，並消除 float32 雜訊。"""
    value = raw * 100.0 if stat in NORMALIZE_X100 else float(raw)
    return round(value, NORMALIZED_PRECISION)
