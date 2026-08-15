"""把兩個 CDN 組成單一的版本下載閘道。

Data Dragon 用完整版本號（16.15.1）；CommunityDragon 只接受 major.minor
（/16.15/ 有效，/16.15.1/ 回 404）。絕不使用 /latest/ —— 實測其內容與
釘住的版本不同，混用會讓屬性與價格來自不同改版。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from lolcp.application.ports import NetworkUnavailableError
from lolcp.infrastructure.http.fetcher import HttpFetcher

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"
CDRAGON_BASE = "https://raw.communitydragon.org"

VERSIONS_URL = f"{DDRAGON_BASE}/api/versions.json"

# （快取內的目的檔名, URL 樣板）
DDRAGON_FILES: tuple[tuple[str, str], ...] = (
    ("ddragon_items.json", "{base}/cdn/{version}/data/zh_TW/item.json"),
    ("ddragon_champions_zh_TW.json", "{base}/cdn/{version}/data/zh_TW/champion.json"),
    ("ddragon_champions_en_US.json", "{base}/cdn/{version}/data/en_US/champion.json"),
)

BIN_FILE = "items_bin.json"
BIN_TEMPLATE = "{base}/{version}/game/items.cdtb.bin.json"


class HttpPatchGateway:
    def __init__(self, fetcher: HttpFetcher | None = None) -> None:
        self._fetcher = fetcher or HttpFetcher()

    @staticmethod
    def cdragon_version(ddragon_version: str) -> str:
        """16.15.1 → 16.15。CommunityDragon 的路徑不含 patch 分量。"""
        return ".".join(ddragon_version.split(".")[:2])

    def latest_version(self) -> str:
        versions = self._fetcher.get_json(VERSIONS_URL)
        if not versions:
            raise NetworkUnavailableError("versions.json 是空的")
        return str(versions[0])

    def download_patch(
        self,
        version: str,
        dest: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """下載一個版本的四個檔案到 dest（應為 PatchCache 的 staging 目錄）。

        bin 檔最大（約 15.8 MB），放最後下載，讓進度條的大部分時間
        反映真正耗時的那一步。
        """
        for filename, template in DDRAGON_FILES:
            url = template.format(base=DDRAGON_BASE, version=version)
            self._fetcher.download(url, dest / filename, on_progress)

        bin_url = BIN_TEMPLATE.format(
            base=CDRAGON_BASE, version=self.cdragon_version(version)
        )
        self._fetcher.download(bin_url, dest / BIN_FILE, on_progress)
