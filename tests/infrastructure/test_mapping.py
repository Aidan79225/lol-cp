import json
from pathlib import Path

import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import GroupLimit
from lolcp.domain.formulas import FormulaContext, FormulaStat, StatPart, Sum, evaluate, problems
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


def test_blue_crystal_mana_comes_from_bin_first(mapper, dd_data, bin_data):
    """藍水晶 bin 有 flatMPPoolMod=300（「bin 不存法力」是舊誤判），
    bin 優先；DD 值相同，一致性檢查零分歧。"""
    item = mapper.to_item(1027, dd_data["1027"], bin_data["Items/1027"])
    assert item.amount_of(StatKey.MANA) == 300.0


def test_ddragon_fills_mana_when_bin_lacks_it(mapper, dd_data):
    """合成情境：bin 條目無法力欄位時，DD 補缺（setdefault 分支）。"""
    raw_dd = dict(dd_data["1027"])
    item = mapper.to_item(1027, raw_dd, {"itemID": 1027})
    assert item.amount_of(StatKey.MANA) == 300.0


def test_bin_mana_wins_on_divergence_and_conflict_is_recorded(mapper, diagnostics, dd_data):
    """合成情境：bin 與 DD 法力分歧時 bin 勝出，且分歧記入診斷 ——
    一致性檢查不再跳過法力。"""
    raw_bin = {"itemID": 1027, "flatMPPoolMod": 280.0}
    item = mapper.to_item(1027, dd_data["1027"], raw_bin)
    assert item.amount_of(StatKey.MANA) == 280.0
    assert any(c.stat is StatKey.MANA for c in diagnostics.conflicts)


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


def test_serrated_dirk_lethality_is_read_as_flat_armor_pen(mapper, dd_data, bin_data):
    """殘暴之力 3134：PhysicalLethality 是裸名欄位（第三種命名慣例），
    曾被靜默丟棄 —— 整條穿甲屬性從未進過系統。"""
    items = mapper.map_all(dd_data, bin_data)
    dirk = next(i for i in items if i.item_id == 3134)
    assert dirk.amount_of(StatKey.ARMOR_PEN_FLAT) == 10.0


def test_dorans_blade_omnivamp_is_normalized_to_percent(mapper, dd_data, bin_data):
    """多蘭之劍 1055：PercentOmnivampMod 0.025 → 2.5（以 1% 為單位）。"""
    items = mapper.map_all(dd_data, bin_data)
    dorans = next(i for i in items if i.item_id == 1055)
    assert dorans.amount_of(StatKey.OMNIVAMP) == 2.5


def test_lowercase_base_mp_regen_is_read(mapper, dd_data, bin_data):
    """蘇瑞亞的戰歌 2065：percentBaseMPRegenMod 小寫開頭（第二種命名慣例）。"""
    items = mapper.map_all(dd_data, bin_data)
    songs = next(i for i in items if i.item_id == 2065)
    assert songs.amount_of(StatKey.BASE_MP_REGEN) == 125.0


def test_stat_field_predicate_accepts_all_three_naming_conventions():
    assert looks_like_bin_stat_field("PhysicalLethality", 10.0)
    assert looks_like_bin_stat_field("percentBaseMPRegenMod", 1.25)
    assert looks_like_bin_stat_field("flatMPPoolMod", 600.0)
    assert looks_like_bin_stat_field("PercentOmnivampMod", 0.025)


def test_stat_field_predicate_still_rejects_non_stats():
    assert not looks_like_bin_stat_field("sellBackModifier", 1.0)  # Modifier ≠ Mod
    assert not looks_like_bin_stat_field("maxStack", 40)
    assert not looks_like_bin_stat_field("LastMajorChangeMajorPatchVersion", 13)
    assert not looks_like_bin_stat_field("ShopOrderPriority", 2)
    assert not looks_like_bin_stat_field("mCanBeSold", True)


def _by_id(items, item_id):
    return next(i for i in items if i.item_id == item_id)


def test_epicness_and_upgrades_are_read(mapper, dd_data, bin_data):
    """出裝規劃器的候選池判準（spec 2026-09-14 §4.1）的原料。"""
    items = mapper.map_all(dd_data, bin_data)
    ie = _by_id(items, 3031)
    assert ie.epicness == 5
    assert ie.upgrades == ()
    assert 3031 in _by_id(items, 1038).upgrades  # 暴風之劍 → 無盡之刃


def test_item_group_limits_are_resolved_from_top_level_group_objects(
    mapper, dd_data, bin_data
):
    """mItemGroups 只存參照；上限在 bin 最外層的 ItemGroup 物件上。"""
    items = mapper.map_all(dd_data, bin_data)
    assert GroupLimit("LastWhisper", 1) in _by_id(items, 3036).group_limits
    assert GroupLimit("Boots", 1) in _by_id(items, 3006).group_limits


def test_groups_without_an_owned_cap_are_not_limits(mapper, dd_data, bin_data):
    """Default 群組沒有 mMaxGroupOwnable —— 不是限制，不得出現。"""
    items = mapper.map_all(dd_data, bin_data)
    assert all(g.group_id != "Default" for i in items for g in i.group_limits)


def test_real_data_has_no_unresolved_group_references(mapper, diagnostics, dd_data, bin_data):
    mapper.map_all(dd_data, bin_data)
    assert diagnostics.unresolved_item_groups == {}


def test_unresolved_group_reference_is_recorded_not_dropped(mapper, diagnostics, dd_data):
    raw_bin = {"Items/1036": {"mFlatPhysicalDamageMod": 10.0, "mItemGroups": ["{deadbeef}"]}}
    items = mapper.map_all({"1036": dd_data["1036"]}, raw_bin)
    assert items[0].group_limits == ()
    assert diagnostics.unresolved_item_groups == {"{deadbeef}": 1}


# ---- 被動資料：data values 與公式樹（spec 2026-09-15 §4.4）----


def _formula_ctx(item, level=18, ranged=False, stats=None):
    return FormulaContext(
        level=level,
        is_ranged=ranged,
        data_values=dict(item.data_values),
        calculations=dict(item.calculations),
        stats=stats or {},
    )


def _calc(item, name):
    return dict(item.calculations)[name]


def test_data_values_are_read(mapper, dd_data, bin_data):
    botrk = _by_id(mapper.map_all(dd_data, bin_data), 3153)
    values = dict(botrk.data_values)
    assert values["RangedValue"] == pytest.approx(0.06)
    assert values["MeleeValue"] == pytest.approx(0.09)


def test_kraken_damage_amount_formula_tree(mapper, dd_data, bin_data):
    """ByCharLevelBreakpoints（每級加）＋ mRangedMultiplier 引用 data value。"""
    kraken = _by_id(mapper.map_all(dd_data, bin_data), 6672)
    formula = _calc(kraken, "DamageAmount")
    assert [evaluate(formula, _formula_ctx(kraken, level=lv)) for lv in (8, 9, 18)] == [
        pytest.approx(150.0), pytest.approx(155.0), pytest.approx(200.0)
    ]
    assert evaluate(formula, _formula_ctx(kraken, level=18, ranged=True)) == pytest.approx(160.0)


def test_terminus_modified_calculation_chain(mapper, dd_data, bin_data):
    """GameCalculationModified：ARMRMaxScaling = ARMRPerHitScaling × 3。"""
    terminus = _by_id(mapper.map_all(dd_data, bin_data), 3302)
    formula = _calc(terminus, "ARMRMaxScaling")
    assert evaluate(formula, _formula_ctx(terminus, level=14)) == pytest.approx(24.0)


def test_nashors_on_hit_scales_with_total_ap(mapper, dd_data, bin_data):
    nashor = _by_id(mapper.map_all(dd_data, bin_data), 3115)
    stats = {(FormulaStat.AP, StatPart.TOTAL): 100.0}
    formula = _calc(nashor, "TotalOnHitDamage")
    assert evaluate(formula, _formula_ctx(nashor, stats=stats)) == pytest.approx(30.0)


def test_trinity_spellblade_scales_with_base_ad(mapper, dd_data, bin_data):
    trinity = _by_id(mapper.map_all(dd_data, bin_data), 3078)
    stats = {(FormulaStat.AD, StatPart.BASE): 62.0}
    formula = _calc(trinity, "SpellbladeDamage")
    assert evaluate(formula, _formula_ctx(trinity, stats=stats)) == pytest.approx(124.0)


def test_unknown_stat_code_becomes_unsupported_and_is_counted(mapper, diagnostics, dd_data, bin_data):
    """破敗的 {405deeb1} 用屬性代碼 13 —— V1 不認識，轉 Unsupported 並計數，不猜。"""
    botrk = _by_id(mapper.map_all(dd_data, bin_data), 3153)
    assert problems(_calc(botrk, "{405deeb1}"), dict(botrk.data_values), dict(botrk.calculations))
    assert diagnostics.unsupported_formula_parts.get("mStat=13", 0) >= 1


def test_unknown_part_type_becomes_unsupported(mapper, diagnostics, dd_data):
    raw_bin = {
        "Items/1036": {
            "mFlatPhysicalDamageMod": 10.0,
            "mItemCalculations": {
                "Weird": {"mFormulaParts": [{"__type": "BrandNewCalculationPart"}], "__type": "GameCalculation"}
            },
        }
    }
    item = mapper.map_all({"1036": dd_data["1036"]}, raw_bin)[0]
    assert isinstance(_calc(item, "Weird"), Sum)
    assert problems(_calc(item, "Weird"), {}, {}) == ("unsupported BrandNewCalculationPart",)
    assert diagnostics.unsupported_formula_parts == {"BrandNewCalculationPart": 1}


def test_bin_mana_agrees_with_ddragon_and_is_kept(mapper, dd_data, bin_data):
    """bin 其實有法力（小寫 flatMPPoolMod，15 件）——「bin 完全不存法力」
    是舊的錯誤結論。bin 值優先、DD 只補缺，一致性檢查涵蓋法力。"""
    items = mapper.map_all(dd_data, bin_data)
    lost_chapter = next(i for i in items if i.item_id == 6655)
    assert lost_chapter.amount_of(StatKey.MANA) == 600.0
