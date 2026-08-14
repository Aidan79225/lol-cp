from pathlib import Path

import pytest

from lolcp.domain.stats import StatKey, UnknownStatKeyError
from lolcp.infrastructure.repositories.toml_config import ConfigError, load_anchors

REPO_ROOT = Path(__file__).parent.parent.parent
ANCHORS = REPO_ROOT / "config" / "anchors.toml"


def test_real_anchors_file_has_eleven_entries():
    config = load_anchors(ANCHORS)
    assert len(config.entries) == 11


def test_real_anchors_cover_exactly_the_priceable_stats():
    config = load_anchors(ANCHORS)
    assert config.stats == frozenset({
        StatKey.AD, StatKey.AP, StatKey.HP, StatKey.MANA,
        StatKey.ARMOR, StatKey.MAGIC_RESIST, StatKey.CRIT_CHANCE,
        StatKey.ATTACK_SPEED, StatKey.ABILITY_HASTE,
        StatKey.MOVE_SPEED_FLAT, StatKey.BASE_HP_REGEN,
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
