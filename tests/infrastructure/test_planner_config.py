from pathlib import Path

import pytest

from lolcp.infrastructure.repositories.toml_config import (
    ConfigError,
    load_planner_config,
)

CONFIG = Path(__file__).parent.parent.parent / "config" / "build_planner.toml"

VALID = (
    "levels = [9, 11, 13, 15, 16, 18]\n"
    "final_holding_gold = 3000\n"
    "beta = 0.25\n"
    "boots_slot = 2\n"
    "beam_width = 40\n"
)


def write(tmp_path, text: str) -> Path:
    path = tmp_path / "build_planner.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_real_config():
    settings = load_planner_config(CONFIG)
    assert settings.levels == (9, 11, 13, 15, 16, 18)
    assert settings.final_holding_gold == 3000.0
    assert settings.beta == 0.25
    assert settings.boots_slot == 2
    assert settings.beam_width == 40


def test_unknown_key_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="betta"):
        load_planner_config(write(tmp_path, VALID + "betta = 0.5\n"))


def test_missing_key_is_rejected(tmp_path):
    text = VALID.replace("beam_width = 40\n", "")
    with pytest.raises(ConfigError, match="beam_width"):
        load_planner_config(write(tmp_path, text))


def test_levels_must_have_six_entries(tmp_path):
    text = VALID.replace("[9, 11, 13, 15, 16, 18]", "[9, 11]")
    with pytest.raises(ConfigError, match="levels"):
        load_planner_config(write(tmp_path, text))


def test_levels_must_be_integers_within_1_to_18(tmp_path):
    for bad in ("[9, 11, 13, 15, 16, 19]", '[9, 11, 13, 15, 16, "18"]', "[9, 11, 13, 15, 16, 17.5]"):
        with pytest.raises(ConfigError, match="levels"):
            load_planner_config(write(tmp_path, VALID.replace("[9, 11, 13, 15, 16, 18]", bad)))


def test_boots_slot_out_of_range_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="boots_slot"):
        load_planner_config(write(tmp_path, VALID.replace("boots_slot = 2", "boots_slot = 7")))


def test_beta_outside_zero_to_one_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="beta"):
        load_planner_config(write(tmp_path, VALID.replace("beta = 0.25", "beta = 1.5")))


def test_boolean_is_not_a_number(tmp_path):
    """toml 的 true 在 Python 是 int 子類 —— 不可當成 beam_width = 1。"""
    with pytest.raises(ConfigError, match="beam_width"):
        load_planner_config(write(tmp_path, VALID.replace("beam_width = 40", "beam_width = true")))


def test_beam_width_must_be_positive(tmp_path):
    with pytest.raises(ConfigError, match="beam_width"):
        load_planner_config(write(tmp_path, VALID.replace("beam_width = 40", "beam_width = 0")))
