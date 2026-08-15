"""實際打 CDN，驗證 schema 未變。預設跳過（見 pyproject 的 addopts）。

執行：uv run pytest -m network -v

這是唯一能提早發現 Riot／CommunityDragon 改格式的機制，
而 bin 檔的 schema 是整個專案最脆弱的一層。
"""

import pytest

from lolcp.domain.stats import BIN_FIELD_TO_STAT, DDRAGON_MANA_FIELD
from lolcp.infrastructure.http.fetcher import HttpFetcher
from lolcp.infrastructure.http.patch_gateway import (
    BIN_TEMPLATE,
    CDRAGON_BASE,
    DDRAGON_BASE,
    HttpPatchGateway,
)

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def gateway() -> HttpPatchGateway:
    return HttpPatchGateway(HttpFetcher(timeout=60.0))


@pytest.fixture(scope="module")
def latest(gateway) -> str:
    return gateway.latest_version()


def test_versions_endpoint_returns_a_newest_first_list(gateway, latest):
    from lolcp.infrastructure.http.patch_gateway import VERSIONS_URL

    versions = HttpFetcher(timeout=30.0).get_json(VERSIONS_URL)
    assert isinstance(versions, list) and versions
    assert versions[0] == latest


def test_ddragon_item_json_still_has_the_fields_we_depend_on(gateway, latest):
    url = f"{DDRAGON_BASE}/cdn/{latest}/data/zh_TW/item.json"
    payload = HttpFetcher(timeout=30.0).get_json(url)
    long_sword = payload["data"]["1036"]
    assert long_sword["gold"]["total"] > 0
    assert "maps" in long_sword and "11" in long_sword["maps"]
    assert "image" in long_sword


def test_ddragon_champion_json_still_exposes_partype_and_tags(gateway, latest):
    url = f"{DDRAGON_BASE}/cdn/{latest}/data/en_US/champion.json"
    payload = HttpFetcher(timeout=30.0).get_json(url)
    draven = payload["data"]["Draven"]
    assert draven["partype"] == "Mana"
    assert "Marksman" in draven["tags"]


def test_cdragon_accepts_major_minor_but_not_the_full_version(gateway, latest):
    """/16.15/ 有效、/16.15.1/ 回 404。這個形狀變了就要改 cdragon_version。

    HEAD 請求也必須帶自訂 User-Agent —— CDragon 對 Python 預設 UA 回 403
    （見 fetcher.USER_AGENT 的註解），少了標頭這個測試會誤報。
    """
    import urllib.error
    import urllib.request

    from lolcp.infrastructure.http.fetcher import USER_AGENT

    def head(url: str) -> urllib.request.Request:
        return urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": USER_AGENT}
        )

    major_minor = HttpPatchGateway.cdragon_version(latest)
    ok_url = BIN_TEMPLATE.format(base=CDRAGON_BASE, version=major_minor)
    with urllib.request.urlopen(head(ok_url), timeout=60) as response:
        assert response.status == 200

    bad_url = BIN_TEMPLATE.format(base=CDRAGON_BASE, version=latest)
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(head(bad_url), timeout=60)
    assert excinfo.value.code == 404  # 403 之類代表別的事變了，不可混為一談


def test_bin_still_carries_ability_haste_and_lacks_mana(gateway, latest):
    """兩個關鍵事實：bin 有 Data Dragon 缺的技能加速，且完全不存法力。

    欄位偵測沿用 mapping.looks_like_bin_stat_field 的廣義形態判斷，
    而非寫死 mFlat/mPercent/mAbility 前綴 —— 寫死前綴會讓
    「提早發現 Riot 新屬性」的目的形同虛設（如 mOmnivampMod 會漏接）。
    """
    from lolcp.infrastructure.mapping import looks_like_bin_stat_field

    url = BIN_TEMPLATE.format(
        base=CDRAGON_BASE, version=HttpPatchGateway.cdragon_version(latest)
    )
    payload = HttpFetcher(timeout=120.0).get_json(url)
    stat_fields = {
        field
        for entry in payload.values()
        if isinstance(entry, dict)
        for field, value in entry.items()
        if looks_like_bin_stat_field(field, value)
    }
    assert "mAbilityHasteMod" in stat_fields
    assert "mFlatCritDamageMod" in stat_fields
    assert not any("MPPool" in field for field in stat_fields)
    unknown = stat_fields - set(BIN_FIELD_TO_STAT)
    assert not unknown, f"bin 出現未知屬性欄位，需更新 BIN_FIELD_TO_STAT：{unknown}"


def test_ddragon_still_supplies_mana(gateway, latest):
    url = f"{DDRAGON_BASE}/cdn/{latest}/data/zh_TW/item.json"
    payload = HttpFetcher(timeout=30.0).get_json(url)
    assert payload["data"]["1027"]["stats"][DDRAGON_MANA_FIELD] > 0
