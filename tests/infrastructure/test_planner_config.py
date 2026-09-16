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
    "near_tolerance = 0.03\n"
    "consider_tolerance = 0.08\n"
    "max_alternatives = 3\n"
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
    assert settings.near_tolerance == 0.03
    assert settings.consider_tolerance == 0.08
    assert settings.max_alternatives == 3


def test_tolerances_must_be_within_zero_and_one(tmp_path):
    for key, good in (("near_tolerance", "0.03"), ("consider_tolerance", "0.08")):
        for bad in ("-0.1", "1.5"):
            text = VALID.replace(f"{key} = {good}", f"{key} = {bad}")
            with pytest.raises(ConfigError, match=key):
                load_planner_config(write(tmp_path, text))


def test_consider_tolerance_must_not_be_tighter_than_near(tmp_path):
    """「可考慮」是較寬的一級 —— 反過來設代表設定檔寫錯了。"""
    text = VALID.replace("consider_tolerance = 0.08", "consider_tolerance = 0.01")
    with pytest.raises(ConfigError, match="consider_tolerance"):
        load_planner_config(write(tmp_path, text))


def test_max_alternatives_must_be_a_non_negative_integer(tmp_path):
    for bad in ("-1", "2.5", "true"):
        text = VALID.replace("max_alternatives = 3", f"max_alternatives = {bad}")
        with pytest.raises(ConfigError, match="max_alternatives"):
            load_planner_config(write(tmp_path, text))


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
