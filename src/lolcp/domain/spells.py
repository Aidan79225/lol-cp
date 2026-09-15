"""英雄技能資料（spec 2026-09-15 champion-kits §8）。

數值陣列與冷卻陣列的索引即技能等級（實測：達瑞文 Q BaseDamage [35, 40, …]
1 級 = 40；索引 0 為佔位）。公式沿用 formulas.py，與裝備被動共用計算器。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from lolcp.domain.formulas import Formula


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

    def values_at(self, rank: int) -> dict[str, float]:
        """該技能等級下的 data values —— 直接作為 FormulaContext.data_values。"""
        return {name: values[rank] for name, values in self.data_values if rank < len(values)}

    def has_value(self, name: str) -> bool:
        return any(n == name for n, _ in self.data_values)


@dataclass(frozen=True)
class ChampionSpells:
    key: str
    spells: tuple[tuple[str, SpellData], ...]

    @cached_property
    def _by_name(self) -> dict[str, SpellData]:
        return dict(self.spells)

    def spell(self, name: str) -> SpellData | None:
        return self._by_name.get(name)
