import json
from pathlib import Path

import pytest

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.stats import StatKey
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.file_champion_repository import (
    DuplicateChampionNameError,
    FileChampionRepository,
)
from lolcp.infrastructure.repositories.file_item_repository import FileItemRepository

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"


@pytest.fixture
def diagnostics() -> Diagnostics:
    return Diagnostics()


def test_all_items_excludes_variant_ids(diagnostics):
    items = FileItemRepository(FIXTURES, ItemMapper(diagnostics)).all_items()
    assert items
    assert all(i.item_id < 10000 for i in items)
    assert diagnostics.filtered_variant_count > 0


def test_all_items_are_sorted_by_id(diagnostics):
    items = FileItemRepository(FIXTURES, ItemMapper(diagnostics)).all_items()
    assert [i.item_id for i in items] == sorted(i.item_id for i in items)


def test_infinity_edge_has_crit_damage_from_bin(diagnostics):
    items = FileItemRepository(FIXTURES, ItemMapper(diagnostics)).all_items()
    ie = next(i for i in items if i.item_id == 3031)
    assert ie.amount_of(StatKey.CRIT_DAMAGE) == 30.0


def test_no_conflicts_in_real_fixture_data(diagnostics):
    """schema 漂移警報。"""
    FileItemRepository(FIXTURES, ItemMapper(diagnostics)).all_items()
    assert diagnostics.conflicts == ()


def test_fixture_actually_contains_jade_variants_to_filter():
    """守住上一個測試不變成空轉。

    若有人縮小 fixture 的 CHAMPION_KEYS 導致沒有 Jade_ 條目，
    過濾測試會「通過」但什麼都沒驗到。先斷言待過濾的東西真的存在。
    """
    raw = json.loads(
        (FIXTURES / "ddragon_champions_en_US.json").read_text(encoding="utf-8")
    )["data"]
    jade = [k for k in raw if k.startswith("Jade_")]
    assert jade, "fixture 沒有 Jade_ 英雄，過濾測試會空轉"
    assert all(int(raw[k]["key"]) >= 60000 for k in jade)


def test_champions_exclude_jade_variants(diagnostics):
    champions = FileChampionRepository(FIXTURES, diagnostics).all_champions()
    assert champions
    assert all(c.numeric_id < 60000 for c in champions)
    assert not any(c.key.startswith("Jade_") for c in champions)


def test_champion_display_name_is_chinese_and_partype_is_english(diagnostics):
    repo = FileChampionRepository(FIXTURES, diagnostics)
    draven = repo.by_key("Draven")
    assert draven is not None
    assert draven.name == "達瑞文"      # zh_TW 顯示
    assert draven.partype == "Mana"     # en_US 邏輯
    assert draven.tags == ("Marksman",)


def test_yasuo_partype_is_flow_not_mana(diagnostics):
    repo = FileChampionRepository(FIXTURES, diagnostics)
    yasuo = repo.by_key("Yasuo")
    assert yasuo is not None and yasuo.uses_mana is False


def test_by_key_returns_none_for_unknown_champion(diagnostics):
    assert FileChampionRepository(FIXTURES, diagnostics).by_key("Nobody") is None


def test_duplicate_champion_names_raise(tmp_path, diagnostics):
    """英雄名稱必須唯一。新的變體前綴出現時要炸掉而非默默多一隻。

    （裝備名稱不唯一 —— 叢林寵物有 3 組同名 —— 故不做此斷言。）
    """
    for locale in ("zh_TW", "en_US"):
        (tmp_path / f"ddragon_champions_{locale}.json").write_text(
            json.dumps({"data": {
                "A": {"key": "1", "name": "同名", "tags": ["Mage"], "partype": "Mana"},
                "B": {"key": "2", "name": "同名", "tags": ["Mage"], "partype": "Mana"},
            }}),
            encoding="utf-8",
        )
    with pytest.raises(DuplicateChampionNameError, match="同名"):
        FileChampionRepository(tmp_path, diagnostics).all_champions()
