from pathlib import Path

import pytest

from lolcp.infrastructure.repositories.toml_config import (
    ConfigError,
    load_combat_config,
)

CONFIG = Path(__file__).parent.parent.parent / "config" / "combat_model.toml"


def test_loads_real_config():
    proxy, targets, fight = load_combat_config(CONFIG)
    assert proxy.base_damage == 300.0
    assert proxy.ap_ratio == 0.7
    assert proxy.base_cooldown == 8.0
    assert [t.key for t in targets] == ["squishy", "tank"]
    squishy = targets[0]
    assert squishy.name == "脆皮"
    assert squishy.armor == 60.0
    assert squishy.magic_resist == 50.0
    assert [t.bonus_hp for t in targets] == [300.0, 2000.0]
    assert fight.average_current_hp_ratio == 0.5
    assert fight.energized_attacks == 4
    assert fight.fight_duration_seconds == 10.0


# ---- 裝備被動的整場平均假設與目標額外生命（spec 2026-09-15 §3.3–§3.4）----

VALID = (
    "[spell_proxy]\nbase_damage = 300.0\nap_ratio = 0.7\nbase_cooldown = 8.0\n\n"
    '[targets.squishy]\nname = "x"\narmor = 60.0\nmagic_resist = 50.0\nhp = 1800.0\nbonus_hp = 300.0\n\n'
    "[fight]\naverage_current_hp_ratio = 0.5\nenergized_attacks = 4\nfight_duration_seconds = 10.0\n"
)


def write(tmp_path, text):
    path = tmp_path / "combat_model.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_text_loads(tmp_path):
    _proxy, targets, fight = load_combat_config(write(tmp_path, VALID))
    assert targets[0].bonus_hp == 300.0
    assert fight.energized_attacks == 4


def test_missing_fight_section_is_rejected(tmp_path):
    text = VALID.split("[fight]")[0]
    with pytest.raises(ConfigError, match="fight"):
        load_combat_config(write(tmp_path, text))


def test_missing_bonus_hp_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="bonus_hp"):
        load_combat_config(write(tmp_path, VALID.replace("bonus_hp = 300.0\n", "")))


def test_unknown_fight_key_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="stacks_full"):
        load_combat_config(write(tmp_path, VALID + "stacks_full = true\n"))


def test_current_hp_ratio_must_be_within_zero_and_one(tmp_path):
    text = VALID.replace("average_current_hp_ratio = 0.5", "average_current_hp_ratio = 1.5")
    with pytest.raises(ConfigError, match="average_current_hp_ratio"):
        load_combat_config(write(tmp_path, text))


def test_fight_duration_must_be_positive(tmp_path):
    """技能模型的固定戰鬥時長（spec champion-kits §3）。"""
    for bad in ("0.0", "-5.0", '"ten"'):
        text = VALID.replace("fight_duration_seconds = 10.0", f"fight_duration_seconds = {bad}")
        with pytest.raises(ConfigError, match="fight_duration_seconds"):
            load_combat_config(write(tmp_path, text))


def test_missing_fight_duration_is_rejected(tmp_path):
    text = VALID.replace("fight_duration_seconds = 10.0\n", "")
    with pytest.raises(ConfigError, match="fight_duration_seconds"):
        load_combat_config(write(tmp_path, text))


def test_energized_attacks_must_be_a_positive_integer(tmp_path):
    for bad in ("0", "2.5", "true"):
        text = VALID.replace("energized_attacks = 4", f"energized_attacks = {bad}")
        with pytest.raises(ConfigError, match="energized_attacks"):
            load_combat_config(write(tmp_path, text))


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
