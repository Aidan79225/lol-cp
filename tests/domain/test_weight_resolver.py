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


def champion(key: str, tags: tuple[str, ...], partype: str = "Mana") -> Champion:
    return Champion(key=key, numeric_id=1, name=key, tags=tags, partype=partype)


def defaults() -> RoleDefaults:
    return RoleDefaults({
        "Mage": StatWeights({StatKey.AD: 0.0, StatKey.AP: 1.0, StatKey.MANA: 0.9}),
        "Marksman": StatWeights({
            StatKey.AD: 1.0, StatKey.AP: 0.0, StatKey.MANA: 0.4,
            StatKey.ARMOR_PEN_PERCENT: 0.8,
        }),
    })


def resolver(overrides: dict | None = None, diagnostics: Diagnostics | None = None):
    d = diagnostics or Diagnostics()
    return WeightResolver(
        role_defaults=defaults(),
        resource_rule=ResourceRule(d),
        overrides=ChampionOverrides(overrides or {}),
        diagnostics=d,
    )


def test_none_champion_gives_uniform_objective_weights():
    """全域視角：所有屬性權重 1.0，即客觀 CP值。"""
    weights = resolver().resolve(None)
    assert weights.of(StatKey.AD) == 1.0
    assert weights.of(StatKey.AP) == 1.0
    assert weights.masked_stats == frozenset()


def test_single_tag_champion_uses_role_defaults_directly():
    """達瑞文是純 Marksman，無需聯集也無需覆寫。"""
    weights = resolver().resolve(champion("Draven", ("Marksman",)))
    assert weights.of(StatKey.AD) == 1.0
    assert weights.of(StatKey.AP) == 0.0


def test_multi_tag_champion_unions_roles():
    """凱爾 Mage+Marksman：混合傷害兩邊都保留。"""
    weights = resolver().resolve(champion("Kayle", ("Mage", "Marksman")))
    assert weights.of(StatKey.AD) == 1.0
    assert weights.of(StatKey.AP) == 1.0


def test_non_mana_champion_gets_mana_zeroed():
    """犽宿的資源是 Flow，法力裝備對他無用。"""
    weights = resolver().resolve(champion("Yasuo", ("Marksman",), partype="Flow"))
    assert weights.of(StatKey.MANA) == 0.0


def test_mana_champion_keeps_mana_weight():
    weights = resolver().resolve(champion("Draven", ("Marksman",), partype="Mana"))
    assert weights.of(StatKey.MANA) == 0.4


def test_empty_partype_is_recorded_and_mana_left_alone():
    """空 partype 視為未知，不歸零 —— 隱藏資訊比多算屬性糟。"""
    diagnostics = Diagnostics()
    weights = resolver(diagnostics=diagnostics).resolve(
        champion("Weird", ("Marksman",), partype="")
    )
    assert weights.of(StatKey.MANA) == 0.4
    assert diagnostics.unknown_partypes == ("Weird",)


def test_override_replaces_role_default():
    weights = resolver(
        {"Kayle": {StatKey.ARMOR_PEN_PERCENT: 0.4}}
    ).resolve(champion("Kayle", ("Mage", "Marksman")))
    assert weights.of(StatKey.ARMOR_PEN_PERCENT) == 0.4


def test_override_applies_after_resource_rule():
    """覆寫是最後一層，可以蓋掉 ResourceRule 的歸零。"""
    weights = resolver({"Yasuo": {StatKey.MANA: 0.5}}).resolve(
        champion("Yasuo", ("Marksman",), partype="Flow")
    )
    assert weights.of(StatKey.MANA) == 0.5


def test_champion_without_override_file_is_unaffected():
    """達瑞文與煞蜜拉零覆寫 —— 新增英雄成本為零。"""
    weights = resolver({"Kayle": {StatKey.ARMOR_PEN_PERCENT: 0.4}}).resolve(
        champion("Draven", ("Marksman",))
    )
    assert weights.of(StatKey.ARMOR_PEN_PERCENT) == 0.8


def test_resolve_defaults_excludes_overrides():
    """拉桿基準值 = 前兩層，不含覆寫。

    用純 Marksman 的達瑞文 —— 凱爾的聯集會因 Mage 未定義物穿
    而取到 1.0（寧可多算原則），驗不到「排除覆寫」這件事。"""
    weights = resolver({"Draven": {StatKey.ARMOR_PEN_PERCENT: 0.4}}).resolve_defaults(
        champion("Draven", ("Marksman",))
    )
    assert weights.of(StatKey.ARMOR_PEN_PERCENT) == 0.8


def test_resolve_defaults_still_applies_resource_rule():
    weights = resolver().resolve_defaults(
        champion("Yasuo", ("Marksman",), partype="Flow")
    )
    assert weights.of(StatKey.MANA) == 0.0


def test_resolve_defaults_for_none_is_uniform():
    assert resolver().resolve_defaults(None).of(StatKey.AD) == 1.0


def test_replace_overrides_takes_effect_on_next_resolve():
    r = resolver()
    assert r.resolve(champion("Draven", ("Marksman",))).of(StatKey.ARMOR_PEN_PERCENT) == 0.8
    r.replace_overrides(
        ChampionOverrides({"Draven": {StatKey.ARMOR_PEN_PERCENT: 0.1}})
    )
    assert r.resolve(champion("Draven", ("Marksman",))).of(StatKey.ARMOR_PEN_PERCENT) == 0.1
    assert r.overrides.by_champion["Draven"][StatKey.ARMOR_PEN_PERCENT] == 0.1


def test_non_mana_champion_gets_mana_linked_stats_zeroed():
    """犽宿不但不用法力，也不該重視魔力回復 —— 資源規則涵蓋整組法力連動屬性。"""
    weights = resolver().resolve(champion("Yasuo", ("Marksman",), partype="Flow"))
    assert weights.of(StatKey.MANA) == 0.0
    assert weights.of(StatKey.BASE_MP_REGEN) == 0.0
    assert weights.of(StatKey.MP_REGEN_FLAT) == 0.0
