"""行級編輯的覆寫存放。手寫註解是刻意經營的資產，不可被序列化抹掉。"""

from __future__ import annotations

import re
from pathlib import Path

from lolcp.domain.stats import StatKey
from lolcp.domain.weights import ChampionOverrides
from lolcp.infrastructure.repositories.toml_config import load_champion_overrides

_HEADER = "# 由權重拉桿產生。可手動編輯；既有註解在拉桿寫入時會被保留。\n"


class TomlOverridesStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def load(self) -> ChampionOverrides:
        return load_champion_overrides(self._directory)

    def set_weight(
        self, champion_key: str, stat: StatKey, value: float | None
    ) -> None:
        path = self._directory / f"{champion_key}.toml"
        if not path.is_file():
            if value is None:
                return  # 本來就沒有覆寫
            self._directory.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"{_HEADER}{stat.config_key} = {value:g}\n", encoding="utf-8"
            )
            return

        pattern = re.compile(
            rf"^(\s*{re.escape(stat.config_key)}\s*=\s*)[0-9eE.+-]+(.*)$"
        )
        out: list[str] = []
        replaced = False
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
            match = pattern.match(line)
            if match is None:
                out.append(line)
            elif value is None:
                replaced = True  # 移除覆寫 = 刪行（含行尾註解）
            else:
                newline = "\n" if line.endswith("\n") else ""
                out.append(f"{match.group(1)}{value:g}{match.group(2)}{newline}")
                replaced = True
        if not replaced and value is not None:
            if out and not out[-1].endswith("\n"):
                out[-1] += "\n"
            out.append(f"{stat.config_key} = {value:g}\n")
        path.write_text("".join(out), encoding="utf-8")
