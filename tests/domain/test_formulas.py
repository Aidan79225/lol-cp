"""通用公式計算器（spec 2026-09-15 §4）。手工建構的公式，全部可手算。"""

import pytest

from lolcp.domain.formulas import (
    Breakpoint,
    CalcRef,
    Constant,
    DataValue,
    FormulaContext,
    FormulaReferenceError,
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
    UnsupportedFormulaError,
    evaluate,
    problems,
)

STATS = {
    (FormulaStat.AD, StatPart.TOTAL): 150.0,
    (FormulaStat.AD, StatPart.BASE): 62.0,
    (FormulaStat.AD, StatPart.BONUS): 88.0,
    (FormulaStat.AP, StatPart.TOTAL): 100.0,
    (FormulaStat.AP, StatPart.BASE): 0.0,
    (FormulaStat.AP, StatPart.BONUS): 100.0,
    (FormulaStat.HP, StatPart.TOTAL): 2000.0,
    (FormulaStat.HP, StatPart.BASE): 1500.0,
    (FormulaStat.HP, StatPart.BONUS): 500.0,
}


def ctx(level=18, ranged=False, data_values=None, calculations=None) -> FormulaContext:
    return FormulaContext(
        level=level,
        is_ranged=ranged,
        data_values=data_values or {},
        calculations=calculations or {},
        stats=STATS,
    )


def test_constant_and_data_value():
    assert evaluate(Constant(45.0), ctx()) == 45.0
    assert evaluate(DataValue("OnHitDamage"), ctx(data_values={"OnHitDamage": 30.0})) == 30.0


def test_missing_data_value_is_a_loud_error():
    with pytest.raises(FormulaReferenceError, match="OnHitDamage"):
        evaluate(DataValue("OnHitDamage"), ctx())


def test_breakpoints_bonus_per_level_at_and_after():
    """海妖：150，9 級起每級 +5 → 8／9／18 級 = 150／155／200。"""
    kraken = LevelBreakpoints(150.0, (Breakpoint(level=9, per_level_at_and_after=5.0),))
    assert [evaluate(kraken, ctx(level=lv)) for lv in (8, 9, 18)] == [150.0, 155.0, 200.0]


def test_breakpoints_additional_bonus_at_level():
    """臨界點：6，11 級 +1、14 級 +1 → 10／11／14 級 = 6／7／8。"""
    terminus = LevelBreakpoints(6.0, (
        Breakpoint(level=11, additional_at_level=1.0),
        Breakpoint(level=14, additional_at_level=1.0),
    ))
    assert [evaluate(terminus, ctx(level=lv)) for lv in (10, 11, 14)] == [6.0, 7.0, 8.0]


def test_stat_term_reads_total_base_and_bonus():
    assert evaluate(StatTerm(FormulaStat.AD, StatPart.BASE, Constant(2.0)), ctx()) == 124.0
    assert evaluate(StatTerm(FormulaStat.AD, StatPart.BONUS, Constant(0.1)), ctx()) == pytest.approx(8.8)
    assert evaluate(
        StatTerm(FormulaStat.AP, StatPart.TOTAL, DataValue("NashorsAPValue")),
        ctx(data_values={"NashorsAPValue": 0.15}),
    ) == pytest.approx(15.0)


def test_sum_product_and_scaled():
    assert evaluate(Sum((Constant(30.0), Constant(15.0))), ctx()) == 45.0
    assert evaluate(Product(Constant(0.08), Constant(4.0)), ctx()) == pytest.approx(0.32)
    assert evaluate(Scaled(Constant(8.0), Constant(3.0)), ctx()) == 24.0


def test_ranged_scaled_only_applies_to_ranged():
    formula = RangedScaled(Constant(200.0), Constant(0.8))
    assert evaluate(formula, ctx(ranged=False)) == 200.0
    assert evaluate(formula, ctx(ranged=True)) == pytest.approx(160.0)


def test_calc_ref_resolves_through_the_item_calculations():
    """臨界點 ARMRMaxScaling = ARMRPerHitScaling × 3。"""
    per_hit = LevelBreakpoints(6.0, (
        Breakpoint(level=11, additional_at_level=1.0),
        Breakpoint(level=14, additional_at_level=1.0),
    ))
    calcs = {"ARMRPerHitScaling": per_hit}
    maximum = Scaled(CalcRef("ARMRPerHitScaling"), Constant(3.0))
    assert evaluate(maximum, ctx(level=14, calculations=calcs)) == 24.0


def test_missing_calc_ref_is_a_loud_error():
    with pytest.raises(FormulaReferenceError, match="Nope"):
        evaluate(CalcRef("Nope"), ctx())


def test_unsupported_raises():
    with pytest.raises(UnsupportedFormulaError, match="mStat=8"):
        evaluate(Sum((Constant(1.0), Unsupported("mStat=8"))), ctx())


def test_problems_lists_missing_names_and_unsupported_parts_through_refs():
    calcs = {"Inner": Sum((DataValue("Gone"), Unsupported("BuffCounterByCoefficientCalculationPart")))}
    formula = Sum((CalcRef("Inner"), DataValue("Here"), CalcRef("Missing")))
    found = problems(formula, data_values={"Here": 1.0}, calculations=calcs)
    assert set(found) == {
        "data value Gone",
        "unsupported BuffCounterByCoefficientCalculationPart",
        "calculation Missing",
    }


# ---- 英雄技能所需的擴充（spec champion-kits §5）----


def test_level_interpolation_is_linear_from_level_1_to_18():
    """煞蜜拉被動 AD 係數 3.5% → 10.5%。"""
    formula = LevelInterpolation(0.035, 0.105)
    assert evaluate(formula, ctx(level=1)) == pytest.approx(0.035)
    assert evaluate(formula, ctx(level=18)) == pytest.approx(0.105)
    assert evaluate(formula, ctx(level=10)) == pytest.approx(0.035 + 0.07 * 9 / 17)


def test_initial_bonus_per_level_adds_from_level_2():
    """煞蜜拉被動 2 + 1/級 → 1 級 2、18 級 19。"""
    formula = LevelBreakpoints(2.0, (), initial_per_level=1.0)
    assert evaluate(formula, ctx(level=1)) == 2.0
    assert evaluate(formula, ctx(level=18)) == 19.0


def test_crit_damage_stat_reads_the_total_multiplier():
    stats = {**STATS, (FormulaStat.CRIT_DAMAGE, StatPart.TOTAL): 2.05}
    formula = StatTerm(FormulaStat.CRIT_DAMAGE, StatPart.TOTAL, Constant(1.0))
    assert evaluate(formula, FormulaContext(18, False, {}, {}, stats)) == pytest.approx(2.05)


def test_problems_is_empty_for_a_healthy_formula():
    assert problems(Sum((Constant(1.0), DataValue("X"))), data_values={"X": 2.0}, calculations={}) == ()
