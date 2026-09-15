"""按版本號分目錄的資料快取。

`.complete` 標記是必要機制：15.8 MB 的 bin 檔下到一半關掉 app，
下次啟動會讀到截斷的 JSON。標記寫在 staging 目錄內，
因此 os.replace 這一次 rename 就是原子的提交。

舊版本不刪，跨版本比較日後不需改結構。
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

from lolcp.infrastructure.cache.layout import champion_bin_filename

_STAGING_PREFIX = ".staging-"


def parse_version(version: str) -> tuple[int, ...]:
    """把版本字串轉為可比較的整數 tuple。

    字串排序會把 "16.9.1" 排在 "16.15.1" 之後，故必須數值化。
    非數字部分（如舊版的 "lolpatch_7.17"）忽略。
    """
    return tuple(int(part) for part in re.findall(r"\d+", version))


class PatchCache:
    COMPLETE_MARKER = ".complete"

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def dir_for(self, version: str) -> Path:
        return self._root / version

    def is_complete(self, version: str) -> bool:
        return (self.dir_for(version) / self.COMPLETE_MARKER).is_file()

    def complete_versions(self) -> tuple[str, ...]:
        if not self._root.is_dir():
            return ()
        versions = [
            d.name
            for d in self._root.iterdir()
            if d.is_dir()
            and not d.name.startswith(_STAGING_PREFIX)
            and self.is_complete(d.name)
        ]
        return tuple(sorted(versions, key=parse_version, reverse=True))

    def latest_complete(self) -> str | None:
        versions = self.complete_versions()
        return versions[0] if versions else None

    def open_staging(self, version: str) -> Path:
        """建立乾淨的暫存目錄。下載全部寫進這裡。"""
        staging = self._root / f"{_STAGING_PREFIX}{version}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        return staging

    def commit(self, version: str, staging: Path) -> Path:
        """寫入完整性標記後以單次 rename 原子提交。

        原子性只涵蓋 process crash；未 fsync，斷電時檔案系統仍可能
        留下有標記但內容截斷的目錄。可重新下載的快取不值得為此付出
        逐檔 fsync 的成本。
        """
        (staging / self.COMPLETE_MARKER).write_text("", encoding="utf-8")
        target = self.dir_for(version)
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
        return target

    def discard(self, staging: Path) -> None:
        if staging.exists():
            shutil.rmtree(staging)

    def missing_champion_bins(self, version: str, keys: Sequence[str]) -> tuple[str, ...]:
        """完整版本目錄中缺哪些英雄技能 bin（舊快取在技能模型上線前建立）。"""
        directory = self.dir_for(version)
        return tuple(k for k in keys if not (directory / champion_bin_filename(k)).is_file())
