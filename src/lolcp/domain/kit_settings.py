"""英雄技能模型的操作假設（spec 2026-09-15 champion-kits §6）。

技能傷害與操作高度相關 —— 每個假設都是 config/kits/<Key>.toml 裡一個具名旋鈕，
預設「熟練玩家」。合法鍵與範圍只在這張表；loader 據此大聲失敗，kit 不再重複驗證。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AssumptionBounds:
    low: float
    high: float


_RATIO = AssumptionBounds(0.0, 1.0)

KIT_ASSUMPTIONS: dict[str, dict[str, AssumptionBounds]] = {
    "Draven": {
        "q_empowered_attack_ratio": _RATIO,   # 帶旋轉飛斧的普攻比例（雙斧全接 = 1）
        "w_uptime": _RATIO,                   # 狂熱血性攻速持續率（接斧頭重置冷卻）
    },
    "Kayle": {},
    "Samira": {
        "melee_attack_ratio": _RATIO,                     # 近戰距離普攻占比
        "combo_seconds": AssumptionBounds(0.0, 60.0),     # 開場打到 S 級評分所需秒數
    },
}


@dataclass(frozen=True)
class KitSettings:
    champion_key: str
    skill_order: tuple[str, ...]
    assumptions: Mapping[str, float] = field(default_factory=dict)
