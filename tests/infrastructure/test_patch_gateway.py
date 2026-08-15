import json

import pytest

from lolcp.application.ports import NetworkUnavailableError
from lolcp.infrastructure.http.patch_gateway import DDRAGON_FILES, HttpPatchGateway


class FakeFetcher:
    def __init__(self, versions=None, fail_on=None):
        self._versions = versions or ["16.16.1", "16.15.1", "16.9.1"]
        self._fail_on = fail_on or set()
        self.downloaded: list[tuple[str, str]] = []
        self.progress_calls = 0

    def get_json(self, url):
        if "versions.json" in url:
            if "versions.json" in self._fail_on:
                raise NetworkUnavailableError(url)
            return self._versions
        raise AssertionError(f"未預期的 get_json：{url}")

    def download(self, url, dest, on_progress=None):
        if any(token in url for token in self._fail_on):
            raise NetworkUnavailableError(url)
        dest.write_text("{}", encoding="utf-8")
        self.downloaded.append((url, dest.name))
        if on_progress:
            on_progress(1, 1)
            self.progress_calls += 1


def test_latest_version_is_the_first_entry():
    assert HttpPatchGateway(FakeFetcher()).latest_version() == "16.16.1"


def test_latest_version_propagates_network_failure():
    gateway = HttpPatchGateway(FakeFetcher(fail_on={"versions.json"}))
    with pytest.raises(NetworkUnavailableError):
        gateway.latest_version()


def test_cdragon_version_strips_the_patch_component():
    """/16.15/ 有效，/16.15.1/ 回 404。"""
    assert HttpPatchGateway.cdragon_version("16.15.1") == "16.15"
    assert HttpPatchGateway.cdragon_version("16.9.1") == "16.9"


def test_download_patch_writes_all_four_files(tmp_path):
    fetcher = FakeFetcher()
    HttpPatchGateway(fetcher).download_patch("16.15.1", tmp_path, None)
    written = {name for _url, name in fetcher.downloaded}
    assert written == {dest for dest, _template in DDRAGON_FILES} | {"items_bin.json"}
    for dest, _template in DDRAGON_FILES:
        assert (tmp_path / dest).is_file()


def test_download_patch_never_uses_the_latest_alias(tmp_path):
    """latest 與釘住的版本內容不同，混用會跨改版。"""
    fetcher = FakeFetcher()
    HttpPatchGateway(fetcher).download_patch("16.15.1", tmp_path, None)
    urls = [url for url, _name in fetcher.downloaded]
    assert not any("/latest/" in url for url in urls)
    assert any("raw.communitydragon.org/16.15/" in url for url in urls)


def test_download_patch_requests_both_locales(tmp_path):
    fetcher = FakeFetcher()
    HttpPatchGateway(fetcher).download_patch("16.15.1", tmp_path, None)
    urls = " ".join(url for url, _ in fetcher.downloaded)
    assert "zh_TW" in urls and "en_US" in urls


def test_download_patch_reports_progress(tmp_path):
    fetcher = FakeFetcher()
    seen: list[tuple[int, int]] = []
    HttpPatchGateway(fetcher).download_patch(
        "16.15.1", tmp_path, lambda done, total: seen.append((done, total))
    )
    assert seen


def test_download_patch_propagates_failure(tmp_path):
    gateway = HttpPatchGateway(FakeFetcher(fail_on={"items.cdtb.bin.json"}))
    with pytest.raises(NetworkUnavailableError):
        gateway.download_patch("16.15.1", tmp_path, None)
