"""config/kits/<Key>.toml（spec champion-kits §6）。"""

from pathlib import Path

import pytest

from lolcp.domain.kit_settings import KIT_ASSUMPTIONS
from lolcp.infrastructure.repositories.toml_config import (
    ConfigError,
    load_kit_config,
    load_kit_configs,
)

KITS_DIR = Path(__file__).parent.parent.parent / "config" / "kits"

DRAVEN = 'skill_order = ["Q", "W", "E"]\nq_empowered_attack_ratio = 1.0\nw_uptime = 1.0\n'


def write(tmp_path, text, key="Draven"):
    path = tmp_path / f"{key}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_real_configs_load_with_skilled_player_defaults():
    kits = load_kit_configs(KITS_DIR)
    assert set(kits) == set(KIT_ASSUMPTIONS)
    assert kits["Draven"].skill_order == ("Q", "W", "E")
    # 接斧比例預設 0.75：斧頭滯空時間固定，實戰約 70–80% 帶斧（spec 2026-09-16 §3.4）
    assert kits["Draven"].assumptions == {"q_empowered_attack_ratio": 0.75, "w_uptime": 1.0}
    assert kits["Kayle"].skill_order == ("E", "Q", "W")
    assert kits["Kayle"].assumptions == {}
    assert kits["Samira"].skill_order == ("Q", "E", "W")
    assert kits["Samira"].assumptions == {"melee_attack_ratio": 0.6, "combo_seconds": 3.0}


def test_unknown_assumption_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="axe_juggling"):
        load_kit_config(write(tmp_path, DRAVEN + "axe_juggling = 2\n"), "Draven")


def test_missing_assumption_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="w_uptime"):
        load_kit_config(write(tmp_path, DRAVEN.replace("w_uptime = 1.0\n", "")), "Draven")


def test_skill_order_must_be_a_permutation(tmp_path):
    text = DRAVEN.replace('["Q", "W", "E"]', '["Q", "Q", "E"]')
    with pytest.raises(ConfigError, match="skill_order"):
        load_kit_config(write(tmp_path, text), "Draven")


def test_ratio_assumptions_are_bounded(tmp_path):
    text = DRAVEN.replace("w_uptime = 1.0", "w_uptime = 1.5")
    with pytest.raises(ConfigError, match="w_uptime"):
        load_kit_config(write(tmp_path, text), "Draven")


def test_boolean_is_not_a_number(tmp_path):
    text = DRAVEN.replace("w_uptime = 1.0", "w_uptime = true")
    with pytest.raises(ConfigError, match="w_uptime"):
        load_kit_config(write(tmp_path, text), "Draven")


def test_missing_kit_file_is_rejected(tmp_path):
    """設定檔隨 repo 發佈；缺檔代表安裝壞了，不可默默退回泛用基準。"""
    with pytest.raises(ConfigError, match="Draven"):
        load_kit_configs(tmp_path)
