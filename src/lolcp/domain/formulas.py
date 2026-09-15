"""通用公式計算器（spec 2026-09-15 §4）。

bin 的 GameCalculation 公式樹由 mapping 轉成這裡的型別，domain 按等級、
遠近程與屬性求值。裝備被動先用；英雄技能 bin 用的是同一套組件，直接沿用。

大聲失敗：缺 data value／calculation 擲 FormulaReferenceError；遇到
Unsupported 擲 UnsupportedFormulaError。綁定時先用 problems() 檢查，
不會在計算中途才炸。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class FormulaStat(Enum):
    """bin mStat 代碼。只收有實例佐證的三種（spec §4.2），其餘一律 Unsupported。"""

    AP = 0            # 缺省值：巫妖之禍 LichBaneAPValue、納什之牙 NashorsAPValue
    AD = 2            # 達瑞文 Q ADScaling
    CRIT_DAMAGE = 9   # 總暴擊傷害倍率（1.75 + 裝備暴傷）：煞蜜拉 R CriticalDamageCalc
    HP = 12           # 史特拉克 HealthPercent


class StatPart(Enum):
    """bin mStatFormula 代碼。"""

    TOTAL = 0
    BASE = 1
    BONUS = 2


@dataclass(frozen=True)
class Constant:
    value: float


@dataclass(frozen=True)
class DataValue:
    name: str


@dataclass(frozen=True)
class StatTerm:
    stat: FormulaStat
    part: StatPart
    coefficient: Formula


@dataclass(frozen=True)
class Breakpoint:
    """兩種寫法（實測）：per_level_at_and_after 從該級起每級加；
    additional_at_level 到該級一次加。"""

    level: int
    per_level_at_and_after: float = 0.0
    additional_at_level: float = 0.0


@dataclass(frozen=True)
class LevelBreakpoints:
    level1: float
    breakpoints: tuple[Breakpoint, ...]
    initial_per_level: float = 0.0   # mInitialBonusPerLevel：2 級起每級加（煞蜜拉被動 2 + 1/級）


MAX_CHAMPION_LEVEL = 18


@dataclass(frozen=True)
class LevelInterpolation:
    """1 級 start 到 18 級 end 線性內插（煞蜜拉被動 AD 係數 3.5% → 10.5%）。"""

    start: float
    end: float


@dataclass(frozen=True)
class Sum:
    parts: tuple[Formula, ...]


@dataclass(frozen=True)
class Product:
    left: Formula
    right: Formula


@dataclass(frozen=True)
class Scaled:
    inner: Formula
    multiplier: Formula


@dataclass(frozen=True)
class RangedScaled:
    """只有遠程英雄乘上 ranged_multiplier。"""

    inner: Formula
    ranged_multiplier: Formula


@dataclass(frozen=True)
class CalcRef:
    """引用同一件裝備（或同一個技能）的另一個 calculation。"""

    name: str


@dataclass(frozen=True)
class Unsupported:
    reason: str


Formula = (
    Constant | DataValue | StatTerm | LevelBreakpoints | LevelInterpolation | Sum | Product
    | Scaled | RangedScaled | CalcRef | Unsupported
)


class FormulaReferenceError(KeyError):
    """公式引用的 data value、calculation 或屬性不存在。"""

    def __str__(self) -> str:  # KeyError 預設會把訊息包成 repr
        return str(self.args[0]) if self.args else ""


class UnsupportedFormulaError(ValueError):
    """公式含 V1 不支援的組件或屬性代碼。"""


@dataclass(frozen=True)
class FormulaContext:
    level: int
    is_ranged: bool
    data_values: Mapping[str, float]
    calculations: Mapping[str, Formula]
    stats: Mapping[tuple[FormulaStat, StatPart], float] = field(default_factory=dict)


def evaluate(formula: Formula, ctx: FormulaContext) -> float:
    match formula:
        case Constant(value):
            return value
        case DataValue(name):
            if name not in ctx.data_values:
                raise FormulaReferenceError(f"data value {name!r} 不存在")
            return ctx.data_values[name]
        case StatTerm(stat, part, coefficient):
            key = (stat, part)
            if key not in ctx.stats:
                raise FormulaReferenceError(f"屬性 {stat.name}/{part.name} 未提供")
            return ctx.stats[key] * evaluate(coefficient, ctx)
        case LevelInterpolation(start, end):
            return start + (end - start) * (ctx.level - 1) / (MAX_CHAMPION_LEVEL - 1)
        case LevelBreakpoints(level1, breakpoints, initial_per_level):
            value = level1 + initial_per_level * (ctx.level - 1)
            for bp in breakpoints:
                if ctx.level >= bp.level:
                    value += bp.additional_at_level
                    value += bp.per_level_at_and_after * (ctx.level - bp.level + 1)
            return value
        case Sum(parts):
            return sum(evaluate(p, ctx) for p in parts)
        case Product(left, right):
            return evaluate(left, ctx) * evaluate(right, ctx)
        case Scaled(inner, multiplier):
            return evaluate(inner, ctx) * evaluate(multiplier, ctx)
        case RangedScaled(inner, ranged_multiplier):
            value = evaluate(inner, ctx)
            return value * evaluate(ranged_multiplier, ctx) if ctx.is_ranged else value
        case CalcRef(name):
            if name not in ctx.calculations:
                raise FormulaReferenceError(f"calculation {name!r} 不存在")
            return evaluate(ctx.calculations[name], ctx)
        case Unsupported(reason):
            raise UnsupportedFormulaError(f"不支援的公式組件：{reason}")
    raise TypeError(f"不是公式：{formula!r}")


def problems(
    formula: Formula,
    data_values: Mapping[str, float],
    calculations: Mapping[str, Formula],
) -> tuple[str, ...]:
    """列出這個公式（含透過 CalcRef 引用的）求值時會失敗的原因；健康時為空。

    綁定器用它在組裝時檢查一次。屬性由 CombatModel 保證提供，不在此檢查。
    """
    found: list[str] = []
    visited: set[str] = set()

    def visit(node: Formula) -> None:
        match node:
            case DataValue(name):
                if name not in data_values:
                    found.append(f"data value {name}")
            case StatTerm(_, _, coefficient):
                visit(coefficient)
            case Sum(parts):
                for p in parts:
                    visit(p)
            case Product(left, right):
                visit(left)
                visit(right)
            case Scaled(inner, multiplier) | RangedScaled(inner, multiplier):
                visit(inner)
                visit(multiplier)
            case CalcRef(name):
                if name in visited:
                    return
                visited.add(name)
                if name not in calculations:
                    found.append(f"calculation {name}")
                else:
                    visit(calculations[name])
            case Unsupported(reason):
                found.append(f"unsupported {reason}")

    visit(formula)
    return tuple(dict.fromkeys(found))
