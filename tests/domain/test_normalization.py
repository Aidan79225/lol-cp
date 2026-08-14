import pytest

from lolcp.domain.stats import (
    DDRAGON_FIELD_TO_STAT,
    NORMALIZED_PRECISION,
    StatKey,
    normalize_amount,
)


def test_absolute_stats_pass_through_unchanged():
    assert normalize_amount(StatKey.AD, 75.0) == 75.0
    assert normalize_amount(StatKey.HP, 333.0) == 333.0
    assert normalize_amount(StatKey.ABILITY_HASTE, 15.0) == 15.0


def test_fraction_stats_are_multiplied_by_one_hundred():
    assert normalize_amount(StatKey.CRIT_CHANCE, 0.25) == 25.0
    assert normalize_amount(StatKey.ATTACK_SPEED, 0.10) == 10.0
    assert normalize_amount(StatKey.BASE_HP_REGEN, 1.0) == 100.0


def test_float32_noise_is_rounded_away():
    """bin 以 float32 儲存，0.15 存成 0.15000000596046448。

    若不四捨五入，靈巧披風的單價會是 600/15.000000596 = 39.99999841，
    黃金測試斷言 40.0 會失敗。正規化層必須把雜訊消在邊界上。
    """
    assert normalize_amount(StatKey.CRIT_CHANCE, 0.15000000596046448) == 15.0
    assert normalize_amount(StatKey.ATTACK_SPEED, 0.10000000149011612) == 10.0
    assert normalize_amount(StatKey.CRIT_DAMAGE, 0.30000001192092896) == 30.0


def test_rounding_precision_is_four_places():
    assert NORMALIZED_PRECISION == 4
    # 4 位以內的真實精度必須保留，不可被四捨五入吃掉
    assert normalize_amount(StatKey.LIFE_STEAL, 0.075) == 7.5


def test_ddragon_field_map_covers_mana():
    assert DDRAGON_FIELD_TO_STAT["FlatMPPoolMod"] is StatKey.MANA
    assert DDRAGON_FIELD_TO_STAT["FlatPhysicalDamageMod"] is StatKey.AD
    assert DDRAGON_FIELD_TO_STAT["FlatCritChanceMod"] is StatKey.CRIT_CHANCE
