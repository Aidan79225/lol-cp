"""從快取目錄讀取裝備。檔案佈局見 spec §6.1。"""

from __future__ import annotations

import json
from pathlib import Path

from lolcp.domain.entities import Item
from lolcp.infrastructure.mapping import ItemMapper

ITEMS_FILE = "ddragon_items.json"
BIN_FILE = "items_bin.json"


class FileItemRepository:
    def __init__(self, patch_dir: Path, mapper: ItemMapper) -> None:
        self._patch_dir = patch_dir
        self._mapper = mapper
        # 實例層級快取（與 FileChampionRepository 同型）。lru_cache 掛在
        # 方法上是類別層級、maxsize=1，兩個不同版本目錄的實例會互踢，
        # 且每次重算都對共用的 Diagnostics 重複累加。
        self._cache: tuple[Item, ...] | None = None

    def all_items(self) -> tuple[Item, ...]:
        if self._cache is None:
            dd = self._load(ITEMS_FILE)["data"]
            binn = self._load(BIN_FILE)
            self._cache = self._mapper.map_all(dd, binn)
        return self._cache

    def _load(self, filename: str) -> dict:
        path = self._patch_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"快取檔案不存在：{path}")
        return json.loads(path.read_text(encoding="utf-8"))
