"""設定檔載入。所有 toml 的屬性鍵名皆為 StatKey 的 snake_case。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from lolcp.domain.combat import SpellProxy, TargetProfile
from lolcp.domain.pricing import AnchorConfig, AnchorEntry
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import ChampionOverrides, RoleDefaults, StatWeights


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
        deduct_raw = body.get("deduct", [])
        if not isinstance(deduct_raw, list):
            raise ConfigError(f"錨定項 {key!r} 的 deduct 必須是陣列")
        if not all(isinstance(d, str) for d in deduct_raw):
            raise ConfigError(f"錨定項 {key!r} 的 deduct 元素必須是字串")
        entries.append(
            AnchorEntry(
                stat=stat,
                item_id=int(body["item_id"]),
                reason=str(body.get("reason", "")),
                deduct=tuple(StatKey.from_config_key(d) for d in deduct_raw),
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


def load_champion_overrides(directory: Path) -> ChampionOverrides:
    """讀取 config/champions/*.toml。檔名主幹即英雄 key（Data Dragon 的 en_US key）。

    目錄不存在或沒有檔案都是正常狀態 —— 多數英雄不需要覆寫。
    """
    if not directory.is_dir():
        return ChampionOverrides({})
    by_champion: dict[str, dict[StatKey, float]] = {}
    for path in sorted(directory.glob("*.toml")):
        raw = _read_toml(path)
        weights = _parse_weights(path.stem, raw)
        by_champion[path.stem] = dict(weights.weights)
    return ChampionOverrides(by_champion)


def load_combat_config(path: Path) -> tuple[SpellProxy, tuple[TargetProfile, ...]]:
    """讀取邊際效益模型常數。缺區塊、缺欄位都要大聲失敗。"""
    raw = _read_toml(path)
    for section in raw:
        if section not in ("spell_proxy", "targets"):
            raise ConfigError(f"{path.name} 出現未知區塊 {section!r}")
    proxy_raw = raw.get("spell_proxy")
    if not isinstance(proxy_raw, dict):
        raise ConfigError(f"{path.name} 缺少 [spell_proxy] 區塊")
    proxy = SpellProxy(
        base_damage=_required_number(proxy_raw, "base_damage", "spell_proxy"),
        ap_ratio=_required_number(proxy_raw, "ap_ratio", "spell_proxy"),
        base_cooldown=_required_number(proxy_raw, "base_cooldown", "spell_proxy"),
    )
    unknown = set(proxy_raw) - {"base_damage", "ap_ratio", "base_cooldown"}
    if unknown:
        raise ConfigError(f"spell_proxy 出現未知欄位 {sorted(unknown)}")

    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, dict) or not targets_raw:
        raise ConfigError(f"{path.name} 缺少 [targets.*] 區塊")
    targets: list[TargetProfile] = []
    for key, body in targets_raw.items():
        if not isinstance(body, dict):
            raise ConfigError(f"targets.{key} 的內容必須是表格")
        unknown = set(body) - {"name", "armor", "magic_resist", "hp"}
        if unknown:
            raise ConfigError(f"targets.{key} 出現未知欄位 {sorted(unknown)}")
        if "name" not in body:
            raise ConfigError(f"targets.{key} 缺少欄位 name")
        targets.append(
            TargetProfile(
                key=key,
                name=str(body["name"]),
                armor=_required_number(body, "armor", f"targets.{key}"),
                magic_resist=_required_number(body, "magic_resist", f"targets.{key}"),
                hp=_required_number(body, "hp", f"targets.{key}"),
            )
        )
    return proxy, tuple(targets)


def _required_number(body: dict, field: str, where: str) -> float:
    if field not in body:
        raise ConfigError(f"{where} 缺少欄位 {field}")
    value = body[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where}.{field} 必須是數值，得到 {value!r}")
    return float(value)
