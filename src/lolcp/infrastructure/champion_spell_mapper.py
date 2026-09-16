"""英雄 bin → ChampionSpells（spec 2026-09-15 champion-kits §7）。

bin 的技能物件 key 形如 Characters/Draven/Spells/DravenSpinningAbility/DravenSpinning，
以最後一段（短名稱）索引；三隻英雄實測短名稱不重複。公式樹沿用 FormulaMapper，
不支援的組件同樣轉 Unsupported 並計入診斷。
"""

from __future__ import annotations

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.spells import ChampionSpells, SpellData
from lolcp.domain.stats import NORMALIZED_PRECISION
from lolcp.infrastructure.formula_mapping import FormulaMapper

CHARACTER_RECORD_TYPE = "CharacterRecord"


class ChampionSpellMapper:
    def __init__(self, diagnostics: Diagnostics) -> None:
        self._formulas = FormulaMapper(diagnostics)

    def map(self, key: str, raw_bin: dict) -> ChampionSpells:
        spells: dict[str, SpellData] = {}
        for path, entry in raw_bin.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("mSpell"), dict):
                continue
            name = str(path).rsplit("/", 1)[-1]
            spell = entry["mSpell"]
            spells.setdefault(
                name,
                SpellData(
                    name=name,
                    cooldowns=_numbers(spell.get("cooldownTime")),
                    data_values=tuple(
                        (str(dv["name"]), _numbers(dv.get("values")))
                        for dv in spell.get("DataValues") or ()
                        if isinstance(dv, dict) and "name" in dv
                    ),
                    calculations=tuple(
                        (str(calc_name), self._formulas.parse_calculation(body))
                        for calc_name, body in (spell.get("mSpellCalculations") or {}).items()
                    ),
                ),
            )
        return ChampionSpells(
            key=key,
            spells=tuple(sorted(spells.items())),
            attack_speed_ratio=_attack_speed_ratio(raw_bin),
        )


def _attack_speed_ratio(raw_bin: dict) -> float | None:
    """CharacterRecord.attackSpeedRatioModifiable（spec 2026-09-16 §3.1）。"""
    for entry in raw_bin.values():
        if not isinstance(entry, dict) or entry.get("__type") != CHARACTER_RECORD_TYPE:
            continue
        ratio = entry.get("attackSpeedRatioModifiable")
        if isinstance(ratio, dict) and isinstance(ratio.get("baseValue"), (int, float)):
            return round(float(ratio["baseValue"]), NORMALIZED_PRECISION)
    return None


def _numbers(raw: object) -> tuple[float, ...]:
    """bin 以 float32 儲存（0.65 → 0.6499999761581421）；與裝備同精度四捨五入。"""
    if not isinstance(raw, list):
        return ()
    return tuple(
        round(float(v), NORMALIZED_PRECISION)
        for v in raw
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    )
