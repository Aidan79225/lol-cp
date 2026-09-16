"""英雄技能資料（spec 2026-09-15 champion-kits §8）。

數值陣列與冷卻陣列的索引即技能等級（實測：達瑞文 Q BaseDamage [35, 40, …]
1 級 = 40；索引 0 為佔位）。公式沿用 formulas.py，與裝備被動共用計算器。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from lolcp.domain.formulas import Formula

# 有技能模型的英雄（Data Dragon en_US key）。同步只下載這些英雄的 bin；
# champion_kits.KITS 的鍵必須與此一致（有測試守著）。
KIT_CHAMPION_KEYS: tuple[str, ...] = ("Draven", "Kayle", "Samira")


@dataclass(frozen=True)
class SpellData:
    name: str
    cooldowns: tuple[float, ...]
    data_values: tuple[tuple[str, tuple[float, ...]], ...]
    calculations: tuple[tuple[str, Formula], ...]

    @cached_property
    def calculation_map(self) -> dict[str, Formula]:
        return dict(self.calculations)

    def cooldown(self, rank: int) -> float:
        return self.cooldowns[rank]

    @cached_property
    def _values_by_rank(self) -> dict[int, dict[str, float]]:
        return {}

    def values_at(self, rank: int) -> dict[str, float]:
        """該技能等級下的 data values —— 直接作為 FormulaContext.data_values。

        每次 profile 都會查，依等級快取；回傳的 dict 為共用，呼叫端不得修改。
        """
        cache = self._values_by_rank
        if rank not in cache:
            cache[rank] = {
                name: values[rank] for name, values in self.data_values if rank < len(values)
            }
        return cache[rank]

    def has_value(self, name: str) -> bool:
        return any(n == name for n, _ in self.data_values)


@dataclass(frozen=True)
class ChampionSpells:
    key: str
    spells: tuple[tuple[str, SpellData], ...]
    # CharacterRecord 的攻速係數：裝備攻速加成乘的是它，不是基礎攻速
    # （凱爾 0.667 ≠ 基礎 0.625）。缺記錄時為 None → 呼叫端退回基礎攻速。
    attack_speed_ratio: float | None = None

    @cached_property
    def _by_name(self) -> dict[str, SpellData]:
        return dict(self.spells)

    def spell(self, name: str) -> SpellData | None:
        return self._by_name.get(name)
