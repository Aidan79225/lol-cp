"""把兩個 CDN 組成單一的版本下載閘道。

Data Dragon 用完整版本號（16.15.1）；CommunityDragon 只接受 major.minor
（/16.15/ 有效，/16.15.1/ 回 404）。絕不使用 /latest/ —— 實測其內容與
釘住的版本不同，混用會讓屬性與價格來自不同改版。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path

from lolcp.application.ports import NetworkUnavailableError
from lolcp.infrastructure.cache.layout import champion_bin_filename
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
# 英雄技能 bin（spec champion-kits §7）：16.15、16.16 版本路徑實測皆 200。
CHAMPION_BIN_TEMPLATE = "{base}/{version}/game/data/characters/{slug}/{slug}.bin.json"


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
        champion_keys: Sequence[str] = (),
    ) -> None:
        """下載一個版本的四個檔案（＋有技能模型的英雄 bin）到 dest（PatchCache 的 staging 目錄）。

        裝備 bin 最大（約 15.8 MB），放在 Data Dragon 之後，讓進度條的大部分時間
        反映真正耗時的那一步；英雄 bin 每隻約 70KB，殿後。
        """
        for filename, template in DDRAGON_FILES:
            url = template.format(base=DDRAGON_BASE, version=version)
            self._fetcher.download(url, dest / filename, on_progress)

        bin_url = BIN_TEMPLATE.format(
            base=CDRAGON_BASE, version=self.cdragon_version(version)
        )
        self._fetcher.download(bin_url, dest / BIN_FILE, on_progress)
        self.download_champion_bins(version, champion_keys, dest, on_progress)

    def download_champion_bins(
        self,
        version: str,
        keys: Sequence[str],
        dest: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """逐檔原子寫入：先寫 .part，成功才 os.replace。

        也用於補抓已完整快取中缺的英雄 bin —— 那時 dest 是正式版本目錄，
        截斷的檔案會被當成有效資料，所以不能直接寫入正式檔名。
        """
        for key in keys:
            final = dest / champion_bin_filename(key)
            part = dest / f".{final.name}.part"
            url = CHAMPION_BIN_TEMPLATE.format(
                base=CDRAGON_BASE, version=self.cdragon_version(version), slug=key.lower()
            )
            try:
                self._fetcher.download(url, part, on_progress)
            except NetworkUnavailableError:
                part.unlink(missing_ok=True)
                raise
            os.replace(part, final)
