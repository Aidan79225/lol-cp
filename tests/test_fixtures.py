"""fixture 完整性。若這些測試失敗，重跑 scripts/build_fixtures.py。"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "16.15.1"

ANCHOR_IDS = [1036, 1052, 1028, 1027, 1029, 1033, 1018, 1042, 2022, 1001, 1006]
GOLDEN_IDS = [3031, 3078, 3157, 3153]


@pytest.fixture(scope="session")
def ddragon_items() -> dict:
    return json.loads((FIXTURES / "ddragon_items.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def items_bin() -> dict:
    return json.loads((FIXTURES / "items_bin.json").read_text(encoding="utf-8"))


def test_fixture_total_size_stays_small():
    total = sum(f.stat().st_size for f in FIXTURES.iterdir())
    assert total < 600 * 1024, f"fixture 膨脹到 {total / 1024:.0f} KB，應裁剪"


def test_version_is_pinned(ddragon_items):
    assert ddragon_items["version"] == "16.15.1"


@pytest.mark.parametrize("item_id", ANCHOR_IDS)
def test_every_anchor_item_present(ddragon_items, item_id):
    assert str(item_id) in ddragon_items["data"]


@pytest.mark.parametrize("item_id", GOLDEN_IDS)
def test_every_golden_item_present(ddragon_items, item_id):
    assert str(item_id) in ddragon_items["data"]


def test_variant_ids_kept_so_filtering_can_be_tested(ddragon_items):
    variants = [i for i in ddragon_items["data"] if int(i) >= 10000]
    assert variants, "需保留變體 ID 才能測試過濾邏輯"


def test_bin_has_crit_damage_that_ddragon_lacks(ddragon_items, items_bin):
    """無盡之刃：bin 有暴擊傷害，Data Dragon 沒有。這是選用 bin 的核心理由。"""
    assert items_bin["Items/3031"]["mFlatCritDamageMod"] == pytest.approx(0.30, abs=1e-6)
    assert "FlatCritDamageMod" not in ddragon_items["data"]["3031"].get("stats", {})


def test_bin_lacks_mana_that_ddragon_has(ddragon_items, items_bin):
    """藍水晶：bin 無任何屬性欄位，法力只能來自 Data Dragon。"""
    assert ddragon_items["data"]["1027"]["stats"]["FlatMPPoolMod"] == 300
    bin_entry = items_bin["Items/1027"]
    assert not [k for k in bin_entry if k.startswith(("mFlat", "mPercent", "mAbility"))]


def test_champion_fixtures_have_both_locales():
    zh = json.loads((FIXTURES / "ddragon_champions_zh_TW.json").read_text(encoding="utf-8"))
    en = json.loads((FIXTURES / "ddragon_champions_en_US.json").read_text(encoding="utf-8"))
    assert zh["data"]["Draven"]["name"] == "達瑞文"
    assert en["data"]["Draven"]["partype"] == "Mana"
    assert en["data"]["Yasuo"]["partype"] == "Flow"
    assert en["data"]["Garen"]["partype"] == "None"
