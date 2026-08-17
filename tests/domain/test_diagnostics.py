from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.stats import StatKey


def test_unknown_bin_fields_are_counted_not_dropped():
    d = Diagnostics()
    d.unknown_bin_field("mBrandNewStatMod", 3031)
    d.unknown_bin_field("mBrandNewStatMod", 3078)
    d.unknown_bin_field("mAnotherOneMod", 3157)
    assert d.unknown_bin_fields == {"mBrandNewStatMod": 2, "mAnotherOneMod": 1}


def test_source_conflicts_record_both_values():
    d = Diagnostics()
    d.source_conflict(3031, StatKey.AD, bin_value=75.0, ddragon_value=70.0)
    assert len(d.conflicts) == 1
    c = d.conflicts[0]
    assert (c.item_id, c.stat, c.bin_value, c.ddragon_value) == (3031, StatKey.AD, 75.0, 70.0)


def test_filtered_variants_are_counted():
    d = Diagnostics()
    for item_id in (323003, 663039, 771036):
        d.filtered_variant(item_id)
    assert d.filtered_variant_count == 3


def test_low_confidence_prices_record_item_count():
    d = Diagnostics()
    d.low_confidence_price(StatKey.CRIT_DAMAGE, item_count=3)
    assert d.low_confidence_stats == {StatKey.CRIT_DAMAGE: 3}


def test_unknown_partypes_are_recorded():
    d = Diagnostics()
    d.unknown_partype("Weird")
    assert d.unknown_partypes == ("Weird",)


def test_summary_line_reports_every_category():
    d = Diagnostics()
    d.unknown_bin_field("mNewMod", 1)
    d.source_conflict(2, StatKey.AD, 1.0, 2.0)
    d.filtered_variant(323003)
    d.low_confidence_price(StatKey.SLOW_RESIST, 3)
    line = d.summary_line()
    assert "1 個未知屬性欄位" in line
    assert "衝突 1 筆" in line
    assert "過濾變體 1 件" in line
    assert "低信賴單價 1 種" in line


def test_clean_run_summary_says_so():
    assert "無異常" in Diagnostics().summary_line()


def test_missing_locale_entry_is_recorded():
    """zh_TW 缺某英雄條目時以英文名頂替 —— 這個 fallback 必須留痕，
    不可靜默（絕不靜默丟棄原則）。"""
    diagnostics = Diagnostics()
    diagnostics.missing_locale_entry("Weird")
    assert diagnostics.missing_locale_entries == ("Weird",)
    assert "在地化缺項 1 隻" in diagnostics.summary_line()
