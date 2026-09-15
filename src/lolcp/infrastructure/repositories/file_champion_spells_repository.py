"""從快取目錄讀英雄技能 bin（spec 2026-09-15 champion-kits §7）。"""

from __future__ import annotations

import json
from pathlib import Path

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.spells import ChampionSpells
from lolcp.infrastructure.cache.layout import champion_bin_filename
from lolcp.infrastructure.champion_spell_mapper import ChampionSpellMapper


class FileChampionSpellsRepository:
    def __init__(
        self, patch_dir: Path, mapper: ChampionSpellMapper, diagnostics: Diagnostics
    ) -> None:
        self._patch_dir = patch_dir
        self._mapper = mapper
        self._diagnostics = diagnostics
        self._cache: dict[str, ChampionSpells | None] = {}  # 實例快取（與其他 repository 同型）

    def spells_for(self, key: str) -> ChampionSpells | None:
        """缺檔回 None 並留痕 —— 補抓失敗或離線時該英雄退回泛用基準技能，不炸。"""
        if key not in self._cache:
            path = self._patch_dir / champion_bin_filename(key)
            if not path.is_file():
                self._diagnostics.missing_champion_spell(key)
                self._cache[key] = None
            else:
                raw = json.loads(path.read_text(encoding="utf-8"))
                self._cache[key] = self._mapper.map(key, raw)
        return self._cache[key]
