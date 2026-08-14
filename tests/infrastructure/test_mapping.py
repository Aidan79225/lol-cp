import json
from pathlib import Path

import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.stats import StatKey
from lolcp.infrastructure.mapping import ItemMapper, looks_like_bin_stat_field

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"


@pytest.fixture(scope="module")
def dd_data() -> dict:
    return json.loads((FIXTURES / "ddragon_items.json").read_text(encoding="utf-8"))["data"]


@pytest.fixture(scope="module")
def bin_data() -> dict:
    return json.loads((FIXTURES / "items_bin.json").read_text(encoding="utf-8"))


@pytest.fixture
def diagnostics() -> Diagnostics:
    return Diagnostics()


@pytest.fixture
def mapper(diagnostics) -> ItemMapper:
    return ItemMapper(diagnostics)


def test_stat_field_predicate_accepts_real_stat_fields():
    assert looks_like_bin_stat_field("mFlatPhysicalDamageMod", 75.0)
    assert looks_like_bin_stat_field("mPercentAttackSpeedMod", 0.1)
    assert looks_like_bin_stat_field("mAbilityHasteMod", 15.0)


def test_stat_field_predicate_rejects_non_stat_fields():
    assert not looks_like_bin_stat_field("maxStack", 1)
    assert not looks_like_bin_stat_field("itemID", 3031)
    assert not looks_like_bin_stat_field("epicness", 5)
    assert not looks_like_bin_stat_field("mCanBeSold", True)  # bool 不是屬性
    assert not looks_like_bin_stat_field("mItemGroups", ["a"])


def test_infinity_edge_gets_all_three_stats_including_crit_damage(mapper, dd_data, bin_data):
    """Data Dragon 漏掉暴擊傷害，bin 有。這是選用 bin 的核心理由。"""
    item = mapper.to_item(3031, dd_data["3031"], bin_data["Items/3031"])
    assert item.name == "無盡之刃"
    assert item.total_gold == 3500
    assert item.amount_of(StatKey.AD) == 75.0
    assert item.amount_of(StatKey.CRIT_CHANCE) == 25.0
    assert item.amount_of(StatKey.CRIT_DAMAGE) == 30.0


def test_mana_comes_from_ddragon_because_bin_lacks_it(mapper, dd_data, bin_data):
    """藍水晶在 bin 裡沒有任何屬性欄位。"""
    item = mapper.to_item(1027, dd_data["1027"], bin_data["Items/1027"])
    assert item.amount_of(StatKey.MANA) == 300.0


def test_cloak_of_agility_crit_is_exactly_fifteen_after_rounding(mapper, dd_data, bin_data):
    """float32 的 0.15000000596 必須被正規化成 15.0，否則單價算不出 40.0。"""
    item = mapper.to_item(1018, dd_data["1018"], bin_data["Items/1018"])
    assert item.amount_of(StatKey.CRIT_CHANCE) == 15.0


def test_unknown_bin_field_is_recorded_not_dropped(mapper, diagnostics, dd_data):
    raw_bin = {"mFlatPhysicalDamageMod": 10.0, "mBrandNewStatMod": 7.0}
    item = mapper.to_item(1036, dd_data["1036"], raw_bin)
    assert item.amount_of(StatKey.AD) == 10.0
    assert diagnostics.unknown_bin_fields == {"mBrandNewStatMod": 1}


def test_source_conflict_is_recorded_and_bin_wins(mapper, diagnostics, dd_data):
    """bin 是 ground truth。不一致時採用 bin，但必須留下記錄。"""
    raw_dd = dict(dd_data["1036"])
    raw_dd["stats"] = {"FlatPhysicalDamageMod": 99}
    item = mapper.to_item(1036, raw_dd, {"mFlatPhysicalDamageMod": 10.0})
    assert item.amount_of(StatKey.AD) == 10.0
    assert len(diagnostics.conflicts) == 1
    assert diagnostics.conflicts[0].bin_value == 10.0
    assert diagnostics.conflicts[0].ddragon_value == 99.0


def test_variant_ids_are_rejected(mapper, dd_data):
    for item_id, raw in dd_data.items():
        if int(item_id) >= 10000:
            assert not mapper.is_summoners_rift_standard(item_id, raw)


def test_standard_summoners_rift_item_is_accepted(mapper, dd_data):
    assert mapper.is_summoners_rift_standard("3031", dd_data["3031"])


def test_map_all_filters_variants_and_records_the_count(mapper, diagnostics, dd_data, bin_data):
    items = mapper.map_all(dd_data, bin_data)
    assert all(i.item_id < 10000 for i in items)
    assert diagnostics.filtered_variant_count > 0


def test_map_all_finds_no_conflicts_in_real_data(mapper, diagnostics, dd_data, bin_data):
    """16.15.1 實測：bin 與 Data Dragon 重疊屬性零分歧。

    此斷言是 schema 漂移警報 —— 一旦失敗，代表某一來源改了。
    """
    mapper.map_all(dd_data, bin_data)
    assert diagnostics.conflicts == ()


def test_map_all_produces_no_unknown_fields_in_real_data(mapper, diagnostics, dd_data, bin_data):
    mapper.map_all(dd_data, bin_data)
    assert diagnostics.unknown_bin_fields == {}
