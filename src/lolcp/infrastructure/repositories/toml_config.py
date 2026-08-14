"""設定檔載入。所有 toml 的屬性鍵名皆為 StatKey 的 snake_case。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from lolcp.domain.pricing import AnchorConfig, AnchorEntry
from lolcp.domain.stats import StatKey


class ConfigError(ValueError):
    """設定檔內容不合法。"""


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"設定檔不存在：{path}")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_anchors(path: Path) -> AnchorConfig:
    raw = _read_toml(path)
    entries: list[AnchorEntry] = []
    for key, body in raw.items():
        stat = StatKey.from_config_key(key)  # 未知鍵擲 UnknownStatKeyError
        if not isinstance(body, dict) or "item_id" not in body:
            raise ConfigError(f"錨定項 {key!r} 缺少 item_id")
        entries.append(
            AnchorEntry(
                stat=stat,
                item_id=int(body["item_id"]),
                reason=str(body.get("reason", "")),
            )
        )
    return AnchorConfig(entries=tuple(entries))
