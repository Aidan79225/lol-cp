import pytest

from lolcp.application.use_cases.sync_game_data import (
    NoDataAvailableError,
    SyncGameData,
)
from lolcp.application.ports import NetworkUnavailableError
from lolcp.infrastructure.cache.patch_cache import PatchCache


class FakeGateway:
    def __init__(self, latest="16.16.1", fail_version=False, fail_download=False):
        self._latest = latest
        self._fail_version = fail_version
        self._fail_download = fail_download
        self.download_calls = 0

    def latest_version(self):
        if self._fail_version:
            raise NetworkUnavailableError("offline")
        return self._latest

    def download_patch(self, version, dest, on_progress=None):
        self.download_calls += 1
        if self._fail_download:
            raise NetworkUnavailableError("truncated")
        (dest / "items_bin.json").write_text("{}", encoding="utf-8")
        if on_progress:
            on_progress(100, 100)


def seed(cache: PatchCache, version: str) -> None:
    staging = cache.open_staging(version)
    (staging / "items_bin.json").write_text("{}", encoding="utf-8")
    cache.commit(version, staging)


def test_downloads_when_cache_is_empty(tmp_path):
    cache = PatchCache(tmp_path)
    gateway = FakeGateway(latest="16.16.1")
    result = SyncGameData(gateway, cache).execute()
    assert result == type(result)(version="16.16.1", offline=False, downloaded=True)
    assert cache.is_complete("16.16.1")


def test_skips_download_when_latest_is_already_cached(tmp_path):
    cache = PatchCache(tmp_path)
    seed(cache, "16.16.1")
    gateway = FakeGateway(latest="16.16.1")
    result = SyncGameData(gateway, cache).execute()
    assert result.downloaded is False
    assert result.offline is False
    assert gateway.download_calls == 0


def test_downloads_when_a_newer_version_appears(tmp_path):
    cache = PatchCache(tmp_path)
    seed(cache, "16.15.1")
    result = SyncGameData(FakeGateway(latest="16.16.1"), cache).execute()
    assert result.version == "16.16.1"
    assert result.downloaded is True
    assert cache.is_complete("16.15.1")  # 舊版不刪


def test_falls_back_to_cache_when_version_check_fails(tmp_path):
    cache = PatchCache(tmp_path)
    seed(cache, "16.15.1")
    result = SyncGameData(FakeGateway(fail_version=True), cache).execute()
    assert result == type(result)(version="16.15.1", offline=True, downloaded=False)


def test_falls_back_to_cache_when_download_fails_midway(tmp_path):
    cache = PatchCache(tmp_path)
    seed(cache, "16.15.1")
    gateway = FakeGateway(latest="16.16.1", fail_download=True)
    result = SyncGameData(gateway, cache).execute()
    assert result.version == "16.15.1"
    assert result.offline is True
    assert not cache.is_complete("16.16.1")


def test_failed_download_leaves_no_staging_directory(tmp_path):
    cache = PatchCache(tmp_path)
    seed(cache, "16.15.1")
    SyncGameData(FakeGateway(latest="16.16.1", fail_download=True), cache).execute()
    leftovers = [d for d in tmp_path.iterdir() if d.name.startswith(".staging-")]
    assert leftovers == []


def test_raises_when_offline_and_cache_is_empty(tmp_path):
    with pytest.raises(NoDataAvailableError):
        SyncGameData(FakeGateway(fail_version=True), PatchCache(tmp_path)).execute()


def test_raises_when_first_ever_download_fails(tmp_path):
    gateway = FakeGateway(latest="16.16.1", fail_download=True)
    with pytest.raises(NoDataAvailableError):
        SyncGameData(gateway, PatchCache(tmp_path)).execute()


def test_progress_callback_is_forwarded(tmp_path):
    seen: list[tuple[int, int]] = []
    SyncGameData(FakeGateway(), PatchCache(tmp_path)).execute(
        lambda done, total: seen.append((done, total))
    )
    assert seen == [(100, 100)]


def test_use_case_does_not_import_qt():
    """15.8 MB 下載不可阻塞 UI 執行緒，但 use case 本身不該認識 Qt。"""
    import ast
    import pathlib

    source = pathlib.Path(
        "src/lolcp/application/use_cases/sync_game_data.py"
    ).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        mod = node.module if isinstance(node, ast.ImportFrom) else None
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
        for target in filter(None, [mod, *names]):
            assert "PySide6" not in target and "Qt" not in target


def test_patch_cache_satisfies_the_cache_store_port():
    """PatchCache 以結構型別滿足 CacheStore，無需 import application。"""
    import inspect

    from lolcp.application.ports import CacheStore
    from lolcp.infrastructure.cache.patch_cache import PatchCache

    for name in ("is_complete", "latest_complete", "open_staging", "commit", "discard"):
        assert hasattr(PatchCache, name), f"PatchCache 缺少 {name}"
        port_sig = inspect.signature(getattr(CacheStore, name))
        impl_sig = inspect.signature(getattr(PatchCache, name))
        assert list(port_sig.parameters) == list(impl_sig.parameters), (
            f"{name} 的參數名不一致：port {list(port_sig.parameters)} "
            f"vs impl {list(impl_sig.parameters)}"
        )


def test_use_case_does_not_import_infrastructure():
    """快取以 CacheStore Protocol 注入，故 application 不需認識 infrastructure。"""
    import ast
    import pathlib

    source = pathlib.Path(
        "src/lolcp/application/use_cases/sync_game_data.py"
    ).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        mod = node.module if isinstance(node, ast.ImportFrom) else None
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
        for target in filter(None, [mod, *names]):
            assert "infrastructure" not in target, target
