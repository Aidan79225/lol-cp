"""技能等級推算（spec 2026-09-15 champion-kits §4）。

遊戲規則：
- 大絕在 6／11／16 級升級（最多 3 級）
- 一般技能等級 ≤ (英雄等級 + 1) // 2，最多 5 級
- 1–3 級依主升順序先學三招，之後每級投入主升順序中第一個還沒碰上限的技能
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

BASIC_SLOTS = ("Q", "W", "E")
ULTIMATE = "R"
ULTIMATE_LEVELS = (6, 11, 16)
MAX_BASIC_RANK = 5
MAX_LEVEL = 18


def validate_skill_order(order: Sequence[str]) -> tuple[str, ...]:
    """主升順序必須是 Q／W／E 的排列。"""
    order = tuple(order)
    if sorted(order) != sorted(BASIC_SLOTS):
        raise ValueError(f"skill_order 必須是 Q、W、E 的排列，得到 {list(order)}")
    return order


def skill_ranks(level: int, skill_order: Sequence[str]) -> dict[str, int]:
    return dict(_skill_ranks(level, validate_skill_order(skill_order)))


@lru_cache(maxsize=None)
def _skill_ranks(level: int, order: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    """每次 profile 都會呼叫 —— 輸入只有 18 × 6 種組合，快取。"""
    if not 1 <= level <= MAX_LEVEL:
        raise ValueError(f"英雄等級必須在 1～{MAX_LEVEL}，得到 {level}")
    ranks = {slot: 0 for slot in (*BASIC_SLOTS, ULTIMATE)}
    for lv in range(1, level + 1):
        if lv in ULTIMATE_LEVELS:
            ranks[ULTIMATE] += 1
            continue
        cap = min(MAX_BASIC_RANK, (lv + 1) // 2)
        unlearned = [s for s in order if ranks[s] == 0]
        if lv <= len(BASIC_SLOTS) and unlearned:
            pick = unlearned[0]
        else:
            pick = next(s for s in order if ranks[s] < cap)
        ranks[pick] += 1
    return tuple(ranks.items())
