from pathlib import Path

import pytest

from lolcp.infrastructure.repositories.toml_config import (
    ConfigError,
    load_combat_config,
)

CONFIG = Path(__file__).parent.parent.parent / "config" / "combat_model.toml"


def test_loads_real_config():
    proxy, targets = load_combat_config(CONFIG)
    assert proxy.base_damage == 300.0
    assert proxy.ap_ratio == 0.7
    assert proxy.base_cooldown == 8.0
    assert [t.key for t in targets] == ["squishy", "tank"]
    squishy = targets[0]
    assert squishy.name == "脆皮"
    assert squishy.armor == 60.0
    assert squishy.magic_resist == 50.0


def test_missing_spell_proxy_is_rejected(tmp_path):
    bad = tmp_path / "combat_model.toml"
    bad.write_text('[targets.squishy]\nname = "x"\narmor = 1.0\nmagic_resist = 1.0\nhp = 1.0\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="spell_proxy"):
        load_combat_config(bad)


def test_missing_target_field_is_rejected(tmp_path):
    bad = tmp_path / "combat_model.toml"
    bad.write_text(
        "[spell_proxy]\nbase_damage = 300.0\nap_ratio = 0.7\nbase_cooldown = 8.0\n\n"
        '[targets.squishy]\nname = "x"\narmor = 60.0\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="magic_resist"):
        load_combat_config(bad)


def test_no_targets_is_rejected(tmp_path):
    bad = tmp_path / "combat_model.toml"
    bad.write_text(
        "[spell_proxy]\nbase_damage = 300.0\nap_ratio = 0.7\nbase_cooldown = 8.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="targets"):
        load_combat_config(bad)


def test_unknown_key_in_spell_proxy_is_rejected(tmp_path):
    bad = tmp_path / "combat_model.toml"
    bad.write_text(
        "[spell_proxy]\nbase_damage = 300.0\nap_ratio = 0.7\nbase_cooldown = 8.0\nbonus = 1.0\n\n"
        '[targets.squishy]\nname = "x"\narmor = 60.0\nmagic_resist = 50.0\nhp = 1800.0\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="未知欄位"):
        load_combat_config(bad)


def test_typo_next_to_correct_target_field_is_rejected(tmp_path):
    """armour 拼錯字不可默默變成死設定。"""
    bad = tmp_path / "combat_model.toml"
    bad.write_text(
        "[spell_proxy]\nbase_damage = 300.0\nap_ratio = 0.7\nbase_cooldown = 8.0\n\n"
        '[targets.squishy]\nname = "x"\narmor = 60.0\narmour = 61.0\nmagic_resist = 50.0\nhp = 1800.0\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="armour"):
        load_combat_config(bad)


def test_non_numeric_value_is_rejected(tmp_path):
    bad = tmp_path / "combat_model.toml"
    bad.write_text(
        '[spell_proxy]\nbase_damage = "many"\nap_ratio = 0.7\nbase_cooldown = 8.0\n\n'
        '[targets.squishy]\nname = "x"\narmor = 60.0\nmagic_resist = 50.0\nhp = 1800.0\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="數值"):
        load_combat_config(bad)
