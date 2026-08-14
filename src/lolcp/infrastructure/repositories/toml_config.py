"""設定檔載入。所有 toml 的屬性鍵名皆為 StatKey 的 snake_case。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from lolcp.domain.pricing import AnchorConfig, AnchorEntry
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import RoleDefaults, StatWeights


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


def _parse_weights(role: str, body: object) -> StatWeights:
    if not isinstance(body, dict):
        raise ConfigError(f"角色 {role!r} 的內容必須是表格")
    weights: dict[StatKey, float] = {}
    for key, value in body.items():
        stat = StatKey.from_config_key(key)  # 未知鍵擲 UnknownStatKeyError
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{role}.{key} 必須是 0.0～1.0 的數值，得到 {value!r}")
        weights[stat] = float(value)
    return StatWeights(weights)


def load_role_defaults(path: Path) -> RoleDefaults:
    raw = _read_toml(path)
    return RoleDefaults({role: _parse_weights(role, body) for role, body in raw.items()})
