"""英雄技能 bin → SpellData（spec champion-kits §5、§7）。真 16.15 bin，手算。"""

import json
from pathlib import Path

import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.formulas import FormulaContext, FormulaStat, StatPart, evaluate, problems
from lolcp.infrastructure.champion_spell_mapper import ChampionSpellMapper

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"

# spec §6 綁定表：(英雄, 技能, calculation)
BOUND_CALCULATIONS = [
    ("Draven", "DravenSpinning", "TotalDamage"),
    ("Draven", "DravenDoubleShot", "TotalDamage"),
    ("Draven", "DravenRCast", "RCalculatedDamage"),
    ("Kayle", "KaylePassive", "PassiveWaveDamage"),
    ("Kayle", "KayleE", "EPassiveTotalDamage"),
    ("Kayle", "KayleE", "ActiveTotalExecuteDamage"),
    ("Kayle", "KayleQ", "TotalDamage"),
    ("Kayle", "KayleR", "TotalDamage"),
    ("Samira", "SamiraPassive", "BonusMeleeDamage"),
    ("Samira", "SamiraQ", "DamageCalc"),
    ("Samira", "SamiraW", "DamageCalc"),
    ("Samira", "SamiraE", "DashDamage"),
    ("Samira", "SamiraR", "DamageCalc"),
    ("Samira", "SamiraR", "CriticalDamageCalc"),
]


def stats(ad_base=100.0, ad_bonus=0.0, ap=0.0, crit_multiplier=1.75):
    return {
        (FormulaStat.AD, StatPart.TOTAL): ad_base + ad_bonus,
        (FormulaStat.AD, StatPart.BASE): ad_base,
        (FormulaStat.AD, StatPart.BONUS): ad_bonus,
        (FormulaStat.AP, StatPart.TOTAL): ap,
        (FormulaStat.AP, StatPart.BASE): 0.0,
        (FormulaStat.AP, StatPart.BONUS): ap,
        (FormulaStat.CRIT_DAMAGE, StatPart.TOTAL): crit_multiplier,
    }


@pytest.fixture(scope="module")
def champions():
    mapper = ChampionSpellMapper(Diagnostics())
    return {
        key: mapper.map(key, json.loads((FIXTURES / f"champion_{key}.bin.json").read_text(encoding="utf-8")))
        for key in ("Draven", "Kayle", "Samira")
    }


def value(champions, key, spell_name, calc, rank, level=18, **stat_kw):
    spell = champions[key].spell(spell_name)
    return evaluate(
        spell.calculation_map[calc],
        FormulaContext(
            level=level,
            is_ranged=True,
            data_values=spell.values_at(rank),
            calculations=spell.calculation_map,
            stats=stats(**stat_kw),
        ),
    )


def test_attack_speed_ratio_comes_from_the_character_record(champions):
    """裝備攻速加成乘的是攻速係數，不是基礎攻速（spec 2026-09-16 §3.1）。

    實測：凱爾 0.667 ≠ 基礎攻速 0.625；達瑞文與煞蜜拉兩者相同。"""
    assert champions["Kayle"].attack_speed_ratio == pytest.approx(0.667, abs=1e-3)
    assert champions["Draven"].attack_speed_ratio == pytest.approx(0.679, abs=1e-3)


def test_missing_character_record_yields_no_ratio():
    mapper = ChampionSpellMapper(Diagnostics())
    spells = mapper.map("Nobody", {"Characters/Nobody/Spells/X": {"mSpell": {}}})
    assert spells.attack_speed_ratio is None


def test_spells_are_indexed_by_short_name(champions):
    q = champions["Draven"].spell("DravenSpinning")
    assert q is not None and q.name == "DravenSpinning"
    assert champions["Draven"].spell("Nope") is None


def test_rank_indexes_cooldowns_and_data_values(champions):
    """陣列索引即技能等級：達瑞文 Q 1 級冷卻 12、5 級 8；BaseDamage 1 級 40。"""
    q = champions["Draven"].spell("DravenSpinning")
    assert q.cooldown(1) == 12.0
    assert q.cooldown(5) == 8.0
    assert q.values_at(1)["BaseDamage"] == 40.0


def test_draven_q_total_damage(champions):
    """1 級：40 + 75% × 額外 AD 100 = 115。"""
    assert value(champions, "Draven", "DravenSpinning", "TotalDamage", rank=1, ad_bonus=100.0) == pytest.approx(115.0)


def test_samira_passive_uses_interpolation_and_initial_bonus(champions):
    """1 級 AD 100：2 + 3.5% × 100 = 5.5；18 級 AD 200：19 + 10.5% × 200 = 40。"""
    assert value(champions, "Samira", "SamiraPassive", "BonusMeleeDamage", rank=0, level=1) == pytest.approx(5.5)
    assert value(champions, "Samira", "SamiraPassive", "BonusMeleeDamage", rank=0, level=18,
                 ad_bonus=100.0) == pytest.approx(40.0)


def test_samira_r_crit_reads_the_crit_damage_multiplier(champions):
    """1 級：(20 + 30% × AD 200) × 1.75 = 140。"""
    assert value(champions, "Samira", "SamiraR", "CriticalDamageCalc", rank=1,
                 ad_bonus=100.0) == pytest.approx(140.0)


def test_kayle_e_active_execute_percentage_scales_with_ap(champions):
    """1 級：(8 + 1.5 × AP/100) × 0.01 → AP 100 = 0.095。"""
    assert value(champions, "Kayle", "KayleE", "ActiveTotalExecuteDamage", rank=1, ap=100.0) == pytest.approx(0.095)


def test_kayle_wave_damage_grows_from_level_12(champions):
    at_11 = value(champions, "Kayle", "KaylePassive", "PassiveWaveDamage", rank=0, level=11)
    at_12 = value(champions, "Kayle", "KaylePassive", "PassiveWaveDamage", rank=0, level=12)
    assert (at_11, at_12) == (pytest.approx(20.0), pytest.approx(23.0))


@pytest.mark.parametrize(("key", "spell_name", "calc"), BOUND_CALCULATIONS)
def test_every_bound_calculation_is_fully_supported(champions, key, spell_name, calc):
    spell = champions[key].spell(spell_name)
    assert spell is not None
    assert problems(spell.calculation_map[calc], spell.values_at(1), spell.calculation_map) == ()
