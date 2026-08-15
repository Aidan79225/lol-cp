import pytest

from lolcp.domain.stats import (
    BIN_FIELD_TO_STAT,
    NORMALIZE_X100,
    SR_STATS,
    StatKey,
    StatLine,
    UnknownStatKeyError,
)


def test_snake_case_config_keys():
    assert StatKey.AD.config_key == "ad"
    assert StatKey.ABILITY_HASTE.config_key == "ability_haste"
    assert StatKey.ARMOR_PEN_PERCENT.config_key == "armor_pen_percent"
    assert StatKey.CRIT_CHANCE.config_key == "crit_chance"


def test_config_key_round_trip_for_every_member():
    for stat in StatKey:
        assert StatKey.from_config_key(stat.config_key) is stat


def test_unknown_config_key_lists_valid_options():
    with pytest.raises(UnknownStatKeyError) as exc:
        StatKey.from_config_key("attak_speed")
    message = str(exc.value)
    assert "attak_speed" in message
    assert "attack_speed" in message  # 必須列出合法選項，讓打錯字的人看得到


def test_crit_damage_needs_x100_despite_flat_prefix():
    """mFlatCritDamageMod = 0.30 帶 Flat 前綴卻是分數。前綴不可用於判斷。"""
    assert BIN_FIELD_TO_STAT["mFlatCritDamageMod"] is StatKey.CRIT_DAMAGE
    assert StatKey.CRIT_DAMAGE in NORMALIZE_X100


def test_flat_magic_penetration_is_absolute_despite_being_a_penetration_stat():
    assert BIN_FIELD_TO_STAT["mFlatMagicPenetrationMod"] is StatKey.MAGIC_PEN_FLAT
    assert StatKey.MAGIC_PEN_FLAT not in NORMALIZE_X100


def test_normalize_set_has_exactly_the_fifteen_fraction_stats():
    assert NORMALIZE_X100 == frozenset({
        StatKey.CRIT_CHANCE,
        StatKey.CRIT_DAMAGE,
        StatKey.ATTACK_SPEED,
        StatKey.ATTACK_SPEED_MULTIPLICATIVE,
        StatKey.BASE_HP_REGEN,
        StatKey.LIFE_STEAL,
        StatKey.OMNIVAMP,        # 0.025 → 2.5%
        StatKey.BASE_MP_REGEN,   # 1.25 → 125%
        StatKey.MOVE_SPEED_PERCENT,
        StatKey.HEAL_SHIELD_POWER,
        StatKey.TENACITY,
        StatKey.SLOW_RESIST,
        StatKey.MAGIC_PEN_PERCENT,
        StatKey.ARMOR_PEN_PERCENT,
        StatKey.COOLDOWN_REDUCTION,
    })


def test_bin_field_map_covers_all_twentynine_bin_fields():
    assert len(BIN_FIELD_TO_STAT) == 29
    assert "mAbilityHasteMod" in BIN_FIELD_TO_STAT
    assert "PhysicalLethality" in BIN_FIELD_TO_STAT   # 裸名慣例
    assert "flatMPPoolMod" in BIN_FIELD_TO_STAT       # 小寫慣例


def test_mana_comes_from_both_sources():
    """「bin 完全不存法力」是舊的錯誤結論 —— bin 以小寫 flatMPPoolMod
    存法力；16.15.1 實測與 DD 各 15 件、完全重疊、零分歧。"""
    assert BIN_FIELD_TO_STAT["flatMPPoolMod"] is StatKey.MANA


def test_sr_stats_is_twentyfive():
    assert len(SR_STATS) == 25
    assert StatKey.MANA in SR_STATS
    assert StatKey.ARMOR_PEN_FLAT in SR_STATS  # 穿甲，盲點修復後現身（12 件）
    assert StatKey.COOLDOWN_REDUCTION not in SR_STATS  # 非 SR，但仍在 StatKey 內


def test_stat_line_is_frozen():
    line = StatLine(StatKey.AD, 75.0)
    assert line.amount == 75.0
    with pytest.raises(AttributeError):
        line.amount = 1.0  # type: ignore[misc]
