"""從快取目錄讀取裝備。檔案佈局見 spec §6.1。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from lolcp.domain.entities import Item
from lolcp.infrastructure.mapping import ItemMapper

ITEMS_FILE = "ddragon_items.json"
BIN_FILE = "items_bin.json"


class FileItemRepository:
    def __init__(self, patch_dir: Path, mapper: ItemMapper) -> None:
        self._patch_dir = patch_dir
        self._mapper = mapper

    @lru_cache(maxsize=1)  # noqa: B019 — 每個 repository 實例對應一個固定版本目錄
    def all_items(self) -> tuple[Item, ...]:
        dd = self._load(ITEMS_FILE)["data"]
        binn = self._load(BIN_FILE)
        return self._mapper.map_all(dd, binn)

    def _load(self, filename: str) -> dict:
        path = self._patch_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"快取檔案不存在：{path}")
        return json.loads(path.read_text(encoding="utf-8"))
