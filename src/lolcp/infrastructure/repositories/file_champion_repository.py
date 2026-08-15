"""從快取目錄讀取英雄。

兩個 locale 的分工是硬規則：
  zh_TW → 顯示名稱
  en_US → tags 與 partype（邏輯判斷）
partype 是在地化字串，拿中文比對會在換語言時爆掉。
"""

from __future__ import annotations

import json
from pathlib import Path

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion

ZH_FILE = "ddragon_champions_zh_TW.json"
EN_FILE = "ddragon_champions_en_US.json"

# id >= 60000 是其他遊戲模式的 Jade_ 變體，233 條目中有 60 個。
MAX_STANDARD_CHAMPION_ID = 60_000


class DuplicateChampionNameError(RuntimeError):
    """英雄顯示名稱重複。可能是出現了新的變體前綴。"""


class FileChampionRepository:
    def __init__(self, patch_dir: Path, diagnostics: Diagnostics) -> None:
        self._patch_dir = patch_dir
        self._diagnostics = diagnostics
        self._cache: tuple[Champion, ...] | None = None

    def all_champions(self) -> tuple[Champion, ...]:
        if self._cache is None:
            self._cache = self._load_all()
        return self._cache

    def by_key(self, key: str) -> Champion | None:
        for champion in self.all_champions():
            if champion.key == key:
                return champion
        return None

    def _load_all(self) -> tuple[Champion, ...]:
        zh = self._load(ZH_FILE)["data"]
        en = self._load(EN_FILE)["data"]
        champions: list[Champion] = []
        for key, en_entry in en.items():
            numeric_id = int(en_entry["key"])
            if numeric_id >= MAX_STANDARD_CHAMPION_ID:
                continue
            zh_entry = zh.get(key, en_entry)
            champions.append(
                Champion(
                    key=key,
                    numeric_id=numeric_id,
                    name=zh_entry["name"],
                    tags=tuple(en_entry.get("tags", ())),
                    partype=en_entry.get("partype", ""),
                )
            )
        self._assert_unique_names(champions)
        return tuple(sorted(champions, key=lambda c: c.numeric_id))

    @staticmethod
    def _assert_unique_names(champions: list[Champion]) -> None:
        seen: dict[str, str] = {}
        for champion in champions:
            if champion.name in seen:
                raise DuplicateChampionNameError(
                    f"英雄名稱 {champion.name!r} 重複："
                    f"{seen[champion.name]} 與 {champion.key}。"
                    f"可能出現了新的變體前綴，需更新過濾規則。"
                )
            seen[champion.name] = champion.key

    def _load(self, filename: str) -> dict:
        path = self._patch_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"快取檔案不存在：{path}")
        return json.loads(path.read_text(encoding="utf-8"))
