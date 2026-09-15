"""版本快取目錄內的檔名規則 —— 下載、快取完整性、repository 共用這一處。

英雄技能 bin 平放於版本目錄（不用子目錄）：整合測試以 iterdir() 逐檔複製
fixture，子目錄會打壞它（spec 2026-09-15 champion-kits §7 更正）。
"""

from __future__ import annotations


def champion_bin_filename(key: str) -> str:
    """英雄 key 為 Data Dragon en_US key（例：Draven）。"""
    return f"champion_{key}.bin.json"
