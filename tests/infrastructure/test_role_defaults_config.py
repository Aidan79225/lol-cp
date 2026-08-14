from pathlib import Path

import pytest

from lolcp.domain.stats import SR_STATS, StatKey, UnknownStatKeyError
from lolcp.domain.weights import KNOWN_ROLES
from lolcp.infrastructure.repositories.toml_config import (
    ConfigError,
    load_role_defaults,
)

ROLE_DEFAULTS = Path(__file__).parent.parent.parent / "config" / "role_defaults.toml"


@pytest.fixture(scope="module")
def defaults():
    return load_role_defaults(ROLE_DEFAULTS)


def test_all_six_roles_are_defined(defaults):
    assert set(defaults.by_role) == set(KNOWN_ROLES)


@pytest.mark.parametrize("role", KNOWN_ROLES)
def test_every_role_covers_all_summoners_rift_stats(defaults, role):
    """21 種 SR 屬性都要明確給值，不靠 of() 的預設 1.0 兜底。"""
    defined = set(defaults.by_role[role].weights)
    assert SR_STATS <= defined, f"{role} 缺少 {SR_STATS - defined}"


@pytest.mark.parametrize("role", KNOWN_ROLES)
def test_weights_are_within_zero_to_one(defaults, role):
    for stat, weight in defaults.by_role[role].weights.items():
        assert 0.0 <= weight <= 1.0, f"{role}.{stat.config_key} = {weight}"


def test_marksman_masks_ability_power(defaults):
    assert defaults.by_role["Marksman"].of(StatKey.AP) == 0.0


def test_mage_masks_attack_damage(defaults):
    assert defaults.by_role["Mage"].of(StatKey.AD) == 0.0


def test_mage_and_marksman_union_keeps_both_damage_types(defaults):
    """凱爾靠這個聯集才能同時吃 AD 與 AP。"""
    from lolcp.domain.diagnostics import Diagnostics

    merged = defaults.union_max(("Mage", "Marksman"), Diagnostics())
    assert merged.of(StatKey.AD) == 1.0
    assert merged.of(StatKey.AP) == 1.0
    assert merged.of(StatKey.ABILITY_HASTE) == 1.0
    assert merged.of(StatKey.ATTACK_SPEED) == 1.0


def test_unknown_stat_key_in_role_defaults_is_rejected(tmp_path):
    bad = tmp_path / "role_defaults.toml"
    bad.write_text("[Marksman]\nattak_speed = 1.0\n", encoding="utf-8")
    with pytest.raises(UnknownStatKeyError):
        load_role_defaults(bad)


def test_non_numeric_weight_is_rejected(tmp_path):
    bad = tmp_path / "role_defaults.toml"
    bad.write_text('[Marksman]\nad = "high"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="數值"):
        load_role_defaults(bad)
