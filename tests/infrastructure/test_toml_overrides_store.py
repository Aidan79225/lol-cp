from pathlib import Path

import pytest

from lolcp.domain.stats import StatKey
from lolcp.infrastructure.repositories.toml_overrides_store import TomlOverridesStore

REPO_CHAMPIONS = Path(__file__).parent.parent.parent / "config" / "champions"


def store_with_kayle(tmp_path) -> TomlOverridesStore:
    (tmp_path / "Kayle.toml").write_text(
        (REPO_CHAMPIONS / "Kayle.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return TomlOverridesStore(tmp_path)


def comment_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("#")
    ]


def test_updating_a_value_preserves_every_comment_line(tmp_path):
    store = store_with_kayle(tmp_path)
    before = comment_lines(tmp_path / "Kayle.toml")
    store.set_weight("Kayle", StatKey.ARMOR_PEN_PERCENT, 0.55)
    after = comment_lines(tmp_path / "Kayle.toml")
    assert before and after == before  # 真的有註解可保，且逐行不變
    assert store.load().by_champion["Kayle"][StatKey.ARMOR_PEN_PERCENT] == 0.55


def test_removing_an_override_deletes_only_that_line(tmp_path):
    store = store_with_kayle(tmp_path)
    store.set_weight("Kayle", StatKey.ARMOR_PEN_PERCENT, None)
    overrides = store.load().by_champion["Kayle"]
    assert StatKey.ARMOR_PEN_PERCENT not in overrides
    assert StatKey.ARMOR_PEN_FLAT in overrides  # 另一行不受影響


def test_new_stat_is_appended_to_existing_file(tmp_path):
    store = store_with_kayle(tmp_path)
    store.set_weight("Kayle", StatKey.LIFE_STEAL, 0.2)
    assert store.load().by_champion["Kayle"][StatKey.LIFE_STEAL] == 0.2
    assert comment_lines(tmp_path / "Kayle.toml")  # 註解仍在


def test_missing_file_is_created_with_header(tmp_path):
    store = TomlOverridesStore(tmp_path)
    store.set_weight("Draven", StatKey.AP, 0.5)
    text = (tmp_path / "Draven.toml").read_text(encoding="utf-8")
    assert text.startswith("#")
    assert store.load().by_champion["Draven"][StatKey.AP] == 0.5


def test_removing_from_missing_file_is_a_noop(tmp_path):
    TomlOverridesStore(tmp_path).set_weight("Draven", StatKey.AP, None)
    assert not (tmp_path / "Draven.toml").exists()


def test_store_satisfies_the_overrides_store_port():
    import inspect

    from lolcp.application.ports import OverridesStore

    for name in ("load", "set_weight"):
        port_sig = inspect.signature(getattr(OverridesStore, name))
        impl_sig = inspect.signature(getattr(TomlOverridesStore, name))
        assert list(port_sig.parameters) == list(impl_sig.parameters)
