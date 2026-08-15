import pytest

from lolcp.application.use_cases.adjust_champion_weight import AdjustChampionWeight
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import (
    ChampionOverrides,
    ResourceRule,
    RoleDefaults,
    StatWeights,
    WeightResolver,
)

DRAVEN = Champion("Draven", 119, "達瑞文", ("Marksman",), "Mana")


class FakeStore:
    def __init__(self):
        self.data: dict[str, dict[StatKey, float]] = {}

    def load(self):
        return ChampionOverrides({k: dict(v) for k, v in self.data.items()})

    def set_weight(self, champion_key, stat, value):
        row = self.data.setdefault(champion_key, {})
        if value is None:
            row.pop(stat, None)
            if not row:
                del self.data[champion_key]
        else:
            row[stat] = value


def make_resolver() -> WeightResolver:
    d = Diagnostics()
    return WeightResolver(
        role_defaults=RoleDefaults(
            {"Marksman": StatWeights({StatKey.AD: 1.0, StatKey.AP: 0.0})}
        ),
        resource_rule=ResourceRule(d),
        overrides=ChampionOverrides({}),
        diagnostics=d,
    )


def test_adjusting_away_from_default_writes_an_override():
    store, resolver = FakeStore(), make_resolver()
    AdjustChampionWeight(store, resolver).execute(DRAVEN, StatKey.AP, 0.5)
    assert store.data["Draven"][StatKey.AP] == 0.5
    assert resolver.resolve(DRAVEN).of(StatKey.AP) == 0.5


def test_adjusting_back_to_default_removes_the_override():
    store, resolver = FakeStore(), make_resolver()
    use_case = AdjustChampionWeight(store, resolver)
    use_case.execute(DRAVEN, StatKey.AP, 0.5)
    use_case.execute(DRAVEN, StatKey.AP, 0.0)  # Marksman 的 AP 基準 = 0.0
    assert "Draven" not in store.data
    assert resolver.resolve(DRAVEN).of(StatKey.AP) == 0.0


def test_returned_overrides_reflect_the_store():
    store, resolver = FakeStore(), make_resolver()
    overrides = AdjustChampionWeight(store, resolver).execute(DRAVEN, StatKey.AP, 0.3)
    assert overrides.by_champion["Draven"][StatKey.AP] == 0.3
