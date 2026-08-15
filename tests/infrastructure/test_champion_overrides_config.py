from pathlib import Path

import pytest

from lolcp.domain.stats import StatKey, UnknownStatKeyError
from lolcp.infrastructure.repositories.toml_config import (
    ConfigError,
    load_champion_overrides,
)

CHAMPIONS_DIR = Path(__file__).parent.parent.parent / "config" / "champions"


def test_loads_kayle_override():
    overrides = load_champion_overrides(CHAMPIONS_DIR)
    assert overrides.by_champion["Kayle"][StatKey.ARMOR_PEN_PERCENT] == 0.4


def test_champions_without_files_are_absent_not_error():
    """達瑞文與煞蜜拉沒有覆寫檔，這是正常狀態。"""
    overrides = load_champion_overrides(CHAMPIONS_DIR)
    assert "Draven" not in overrides.by_champion
    assert "Samira" not in overrides.by_champion


def test_filename_stem_becomes_the_champion_key():
    overrides = load_champion_overrides(CHAMPIONS_DIR)
    assert set(overrides.by_champion) == {"Kayle"}


def test_missing_directory_yields_empty_overrides(tmp_path):
    overrides = load_champion_overrides(tmp_path / "nope")
    assert overrides.by_champion == {}


def test_unknown_stat_key_is_rejected_with_valid_options(tmp_path):
    (tmp_path / "Draven.toml").write_text("attak_speed = 0.5\n", encoding="utf-8")
    with pytest.raises(UnknownStatKeyError) as exc:
        load_champion_overrides(tmp_path)
    assert "attack_speed" in str(exc.value)


def test_non_numeric_override_is_rejected(tmp_path):
    (tmp_path / "Draven.toml").write_text('ad = "max"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="數值"):
        load_champion_overrides(tmp_path)
