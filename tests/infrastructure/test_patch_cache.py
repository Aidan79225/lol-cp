import pytest

from lolcp.infrastructure.cache.layout import champion_bin_filename
from lolcp.infrastructure.cache.patch_cache import PatchCache, parse_version


def test_parse_version_orders_numerically_not_lexically():
    """字串排序會把 16.9.1 排在 16.15.1 之後。"""
    assert parse_version("16.15.1") > parse_version("16.9.1")
    assert parse_version("16.16.1") > parse_version("16.15.1")


def test_parse_version_tolerates_non_numeric_parts():
    assert parse_version("lolpatch_7.17") == (7, 17)
    assert parse_version("") == ()


def test_missing_version_is_not_complete(tmp_path):
    assert PatchCache(tmp_path).is_complete("16.15.1") is False


def test_directory_without_marker_is_not_complete(tmp_path):
    """模擬 15.8 MB 下到一半就關掉 app。"""
    cache = PatchCache(tmp_path)
    partial = cache.dir_for("16.15.1")
    partial.mkdir(parents=True)
    (partial / "items_bin.json").write_text('{"truncated', encoding="utf-8")
    assert cache.is_complete("16.15.1") is False


def test_commit_makes_the_version_complete(tmp_path):
    cache = PatchCache(tmp_path)
    staging = cache.open_staging("16.15.1")
    (staging / "items_bin.json").write_text("{}", encoding="utf-8")
    target = cache.commit("16.15.1", staging)
    assert cache.is_complete("16.15.1") is True
    assert (target / "items_bin.json").read_text(encoding="utf-8") == "{}"
    assert not staging.exists()


def test_marker_lives_inside_staging_before_the_rename(tmp_path):
    """標記必須在 rename 前就寫進 staging，否則會有無標記的空窗。"""
    cache = PatchCache(tmp_path)
    staging = cache.open_staging("16.15.1")
    (staging / "a.json").write_text("{}", encoding="utf-8")
    cache.commit("16.15.1", staging)
    assert (cache.dir_for("16.15.1") / PatchCache.COMPLETE_MARKER).is_file()


def test_commit_replaces_an_existing_incomplete_directory(tmp_path):
    cache = PatchCache(tmp_path)
    stale = cache.dir_for("16.15.1")
    stale.mkdir(parents=True)
    (stale / "old.json").write_text("stale", encoding="utf-8")

    staging = cache.open_staging("16.15.1")
    (staging / "new.json").write_text("fresh", encoding="utf-8")
    target = cache.commit("16.15.1", staging)

    assert (target / "new.json").is_file()
    assert not (target / "old.json").exists()


def test_discard_removes_staging(tmp_path):
    cache = PatchCache(tmp_path)
    staging = cache.open_staging("16.15.1")
    cache.discard(staging)
    assert not staging.exists()


def test_complete_versions_are_newest_first(tmp_path):
    cache = PatchCache(tmp_path)
    for version in ("16.9.1", "16.15.1", "16.16.1"):
        staging = cache.open_staging(version)
        cache.commit(version, staging)
    assert cache.complete_versions() == ("16.16.1", "16.15.1", "16.9.1")


def test_latest_complete_ignores_incomplete_directories(tmp_path):
    cache = PatchCache(tmp_path)
    cache.commit("16.15.1", cache.open_staging("16.15.1"))
    newer = cache.dir_for("16.16.1")
    newer.mkdir(parents=True)  # 無標記
    assert cache.latest_complete() == "16.15.1"


def test_latest_complete_is_none_when_cache_is_empty(tmp_path):
    assert PatchCache(tmp_path).latest_complete() is None


def test_missing_champion_bins_lists_absent_files_in_a_complete_version(tmp_path):
    """舊快取已標記完整、但沒有英雄 bin → 同步時補抓（spec champion-kits §7）。"""
    cache = PatchCache(tmp_path)
    staging = cache.open_staging("16.16.1")
    (staging / champion_bin_filename("Draven")).write_text("{}", encoding="utf-8")
    cache.commit("16.16.1", staging)
    assert cache.missing_champion_bins("16.16.1", ("Draven", "Kayle", "Samira")) == ("Kayle", "Samira")


def test_staging_directory_is_not_mistaken_for_a_version(tmp_path):
    cache = PatchCache(tmp_path)
    cache.open_staging("16.15.1")  # 留著不 commit
    assert cache.complete_versions() == ()
    assert cache.latest_complete() is None
