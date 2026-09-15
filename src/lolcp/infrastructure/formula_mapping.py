"""bin GameCalculation 公式樹 → domain 公式型別（spec 2026-09-15 §4.4）。

不認識的組件型別與屬性代碼一律轉成 Unsupported 並記入診斷 —— 不猜。
未被任何效果綁定的 Unsupported 無害；被綁定時綁定器會停用該效果。
"""

from __future__ import annotations

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.formulas import (
    Breakpoint,
    CalcRef,
    Constant,
    DataValue,
    Formula,
    FormulaStat,
    LevelBreakpoints,
    LevelInterpolation,
    Product,
    RangedScaled,
    Scaled,
    StatPart,
    StatTerm,
    Sum,
    Unsupported,
)

_STAT_CODES = {s.value: s for s in FormulaStat}
_STAT_PARTS = {p.value: p for p in StatPart}
# 型別名為雜湊、以 mSpellCalculationKey 引用另一個 calculation 的組件。
_CALC_REF_KEY = "mSpellCalculationKey"


class FormulaMapper:
    def __init__(self, diagnostics: Diagnostics) -> None:
        self._diagnostics = diagnostics

    def parse_calculation(self, raw: object) -> Formula:
        """GameCalculation／GameCalculationModified／{e9a3c91d}（帶 mRangedMultiplier）。"""
        if not isinstance(raw, dict):
            return self._unsupported("非物件公式")
        kind = str(raw.get("__type", ""))
        if kind == "GameCalculationModified":
            if "mModifiedGameCalculation" not in raw:
                return self._unsupported(kind)
            formula: Formula = CalcRef(str(raw["mModifiedGameCalculation"]))
        elif isinstance(raw.get("mFormulaParts"), list):
            formula = Sum(tuple(self._part(p) for p in raw["mFormulaParts"]))
        else:
            return self._unsupported(kind or "未知公式")
        if "mMultiplier" in raw:
            formula = Scaled(formula, self._part(raw["mMultiplier"]))
        if "mRangedMultiplier" in raw:
            formula = RangedScaled(formula, self._part(raw["mRangedMultiplier"]))
        return formula

    def _part(self, raw: object) -> Formula:
        if not isinstance(raw, dict):
            return self._unsupported("非物件組件")
        kind = str(raw.get("__type", ""))
        # bin 省略值為 0 的欄位（mNumber、mStat 等缺省即 0）。
        match kind:
            case "NumberCalculationPart":
                return Constant(float(raw.get("mNumber", 0.0)))
            case "NamedDataValueCalculationPart":
                return DataValue(str(raw.get("mDataValue", "")))
            case "StatByNamedDataValueCalculationPart":
                return self._stat_term(raw, DataValue(str(raw.get("mDataValue", ""))))
            case "StatByCoefficientCalculationPart":
                return self._stat_term(raw, Constant(float(raw.get("mCoefficient", 0.0))))
            case "StatBySubPartCalculationPart":
                return self._stat_term(raw, self._part(raw.get("mSubpart")))
            case "ByCharLevelInterpolationCalculationPart":
                return LevelInterpolation(
                    float(raw.get("mStartValue", 0.0)), float(raw.get("mEndValue", 0.0))
                )
            case "ByCharLevelBreakpointsCalculationPart":
                return LevelBreakpoints(
                    float(raw.get("mLevel1Value", 0.0)),
                    tuple(
                        Breakpoint(
                            level=int(bp.get("mLevel", 0)),
                            per_level_at_and_after=float(bp.get("mBonusPerLevelAtAndAfter", 0.0)),
                            additional_at_level=float(bp.get("mAdditionalBonusAtThisLevel", 0.0)),
                        )
                        for bp in raw.get("mBreakpoints", ())
                        if isinstance(bp, dict)
                    ),
                    initial_per_level=float(raw.get("mInitialBonusPerLevel", 0.0)),
                )
            case "SumOfSubPartsCalculationPart":
                return Sum(tuple(self._part(p) for p in raw.get("mSubparts", ())))
            case "ProductOfSubPartsCalculationPart":
                return Product(self._part(raw.get("mPart1")), self._part(raw.get("mPart2")))
        if _CALC_REF_KEY in raw:
            return CalcRef(str(raw[_CALC_REF_KEY]))
        return self._unsupported(kind or "未知組件")

    def _stat_term(self, raw: dict, coefficient: Formula) -> Formula:
        code = raw.get("mStat", 0)
        part_code = raw.get("mStatFormula", 0)
        if code not in _STAT_CODES:
            return self._unsupported(f"mStat={code}")
        if part_code not in _STAT_PARTS:
            return self._unsupported(f"mStatFormula={part_code}")
        return StatTerm(_STAT_CODES[code], _STAT_PARTS[part_code], coefficient)

    def _unsupported(self, reason: str) -> Unsupported:
        self._diagnostics.unsupported_formula_part(reason)
        return Unsupported(reason)
