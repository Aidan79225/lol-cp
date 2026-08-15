from pathlib import Path

import pytest

from lolcp.domain.stats import StatKey, UnknownStatKeyError
from lolcp.infrastructure.repositories.toml_config import ConfigError, load_anchors

REPO_ROOT = Path(__file__).parent.parent.parent
ANCHORS = REPO_ROOT / "config" / "anchors.toml"


def test_real_anchors_file_has_fourteen_entries():
    config = load_anchors(ANCHORS)
    assert len(config.entries) == 14


def test_real_anchors_cover_exactly_the_priceable_stats():
    config = load_anchors(ANCHORS)
    assert config.stats == frozenset({
        StatKey.AD, StatKey.AP, StatKey.HP, StatKey.MANA,
        StatKey.ARMOR, StatKey.MAGIC_RESIST, StatKey.CRIT_CHANCE,
        StatKey.ATTACK_SPEED, StatKey.ABILITY_HASTE,
        StatKey.MOVE_SPEED_FLAT, StatKey.BASE_HP_REGEN,
        StatKey.LIFE_STEAL,          # 扣除錨（吸血鬼權杖）
        StatKey.ARMOR_PEN_PERCENT,   # 扣除錨（最後耳語）
        StatKey.ARMOR_PEN_FLAT,      # 扣除錨（殘暴之力）
    })


def test_anchors_use_standard_item_ids_not_variants():
    """變體 ID(>=10000) 出現在錨定表就是錯的：771036 長劍是 400g 而非 350g。"""
    for entry in load_anchors(ANCHORS).entries:
        assert entry.item_id < 10000, f"{entry.stat} 用了變體 ID {entry.item_id}"


def test_every_anchor_records_a_reason():
    for entry in load_anchors(ANCHORS).entries:
        assert entry.reason.strip(), f"{entry.stat} 缺少理由說明"


def test_for_stat_lookup():
    config = load_anchors(ANCHORS)
    entry = config.for_stat(StatKey.AD)
    assert entry is not None and entry.item_id == 1036
    assert config.for_stat(StatKey.TENACITY) is None


def test_unknown_stat_key_is_rejected_with_valid_options(tmp_path):
    bad = tmp_path / "anchors.toml"
    bad.write_text('[attak_speed]\nitem_id = 1042\nreason = "typo"\n', encoding="utf-8")
    with pytest.raises(UnknownStatKeyError) as exc:
        load_anchors(bad)
    assert "attack_speed" in str(exc.value)


def test_missing_item_id_is_rejected(tmp_path):
    bad = tmp_path / "anchors.toml"
    bad.write_text('[ad]\nreason = "no id"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="item_id"):
        load_anchors(bad)


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="不存在"):
        load_anchors(tmp_path / "nope.toml")


def test_deduct_list_is_parsed_into_stat_keys(tmp_path):
    toml = tmp_path / "anchors.toml"
    toml.write_text(
        '[ad]\nitem_id = 1036\nreason = "純錨"\n\n'
        '[life_steal]\nitem_id = 1053\ndeduct = ["ad"]\nreason = "扣除錨"\n',
        encoding="utf-8",
    )
    entry = load_anchors(toml).for_stat(StatKey.LIFE_STEAL)
    assert entry is not None
    assert entry.deduct == (StatKey.AD,)


def test_omitted_deduct_defaults_to_empty(tmp_path):
    toml = tmp_path / "anchors.toml"
    toml.write_text('[ad]\nitem_id = 1036\nreason = "純錨"\n', encoding="utf-8")
    entry = load_anchors(toml).for_stat(StatKey.AD)
    assert entry.deduct == ()


def test_unknown_deduct_key_is_rejected_with_valid_options(tmp_path):
    toml = tmp_path / "anchors.toml"
    toml.write_text(
        '[life_steal]\nitem_id = 1053\ndeduct = ["attak_speed"]\nreason = "typo"\n',
        encoding="utf-8",
    )
    with pytest.raises(UnknownStatKeyError) as exc:
        load_anchors(toml)
    assert "attack_speed" in str(exc.value)


def test_non_list_deduct_is_rejected(tmp_path):
    toml = tmp_path / "anchors.toml"
    toml.write_text(
        '[life_steal]\nitem_id = 1053\ndeduct = "ad"\nreason = "非陣列"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="陣列"):
        load_anchors(toml)


def test_non_string_deduct_element_is_rejected(tmp_path):
    """TOML 允許異質陣列，deduct = [1] 不可炸出裸 AttributeError。"""
    toml = tmp_path / "anchors.toml"
    toml.write_text(
        '[life_steal]\nitem_id = 1053\ndeduct = [1]\nreason = "非字串"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="字串"):
        load_anchors(toml)
