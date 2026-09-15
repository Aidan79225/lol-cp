"""從快取目錄讀英雄技能（spec champion-kits §7）。"""

from pathlib import Path

from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.spells import KIT_CHAMPION_KEYS
from lolcp.infrastructure.champion_spell_mapper import ChampionSpellMapper
from lolcp.infrastructure.repositories.file_champion_spells_repository import (
    FileChampionSpellsRepository,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "16.15.1"


def repo(patch_dir, diagnostics):
    return FileChampionSpellsRepository(patch_dir, ChampionSpellMapper(diagnostics), diagnostics)


def test_reads_every_kit_champion_from_the_fixture():
    diagnostics = Diagnostics()
    repository = repo(FIXTURES, diagnostics)
    for key in KIT_CHAMPION_KEYS:
        spells = repository.spells_for(key)
        assert spells is not None and spells.key == key
    assert repository.spells_for("Draven").spell("DravenSpinning") is not None
    assert diagnostics.missing_champion_spells == ()


def test_missing_file_yields_none_and_is_recorded(tmp_path):
    """舊快取補抓失敗時不炸 —— 該英雄退回泛用基準技能，但必須留痕。"""
    diagnostics = Diagnostics()
    assert repo(tmp_path, diagnostics).spells_for("Draven") is None
    assert diagnostics.missing_champion_spells == ("Draven",)


def test_results_are_cached_per_instance():
    diagnostics = Diagnostics()
    repository = repo(FIXTURES, diagnostics)
    assert repository.spells_for("Kayle") is repository.spells_for("Kayle")
