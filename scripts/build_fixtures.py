"""下載 16.15.1 官方資料並裁剪為測試 fixture。

原始 bin 檔 15.8 MB，不適合入庫。本腳本裁剪至約 200 KB。
重新產生：uv run python scripts/build_fixtures.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

VERSION = "16.15.1"
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / VERSION

# CommunityDragon 的版本路徑只有 major.minor（/16.15/ 有效，/16.15.1/ 回 404）。
# 絕不可用 /latest/ —— 實測 latest 的檔案大小與 16.15 不同（15,871,583 vs
# 15,803,748 bytes），代表 latest 已領先。混用會讓兩個來源來自不同改版。
CDRAGON_VERSION = ".".join(VERSION.split(".")[:2])

DDRAGON = f"https://ddragon.leagueoflegends.com/cdn/{VERSION}/data"
CDRAGON = f"https://raw.communitydragon.org/{CDRAGON_VERSION}/game/items.cdtb.bin.json"

# 錨定裝備（見 config/anchors.toml）
ANCHOR_IDS = {1036, 1052, 1028, 1027, 1029, 1033, 1018, 1042, 2022, 1001, 1006}
# 黃金測試裝備
GOLDEN_IDS = {3031, 3078, 3157, 3153}
# 需保留的英雄（涵蓋 Mana / Flow / None 三種 partype 與單/多 tag）
CHAMPION_KEYS = {"Draven", "Kayle", "Samira", "Yasuo", "Garen", "Katarina"}

# raw.communitydragon.org 會擋掉 urllib 預設的 User-Agent（回 403），
# 需帶自訂 UA 才能下載。
USER_AGENT = "lol-cp fixture builder (https://github.com/local/lol-cp)"

# 只剔除這一個欄位：mItemDataClient 是巢狀的 tooltip / loc-key 資料
# （41% 的 bin 大小），我方 mapping 層的屬性欄位判斷式本來就會拒絕它
# （值是 dict 不是數字），程式碼從未讀取過它。mItemGroups／mCategories／
# mCanBeSold 等其他 dict/list 欄位必須保留 —— 之後的任務需要用真實資料
# 驗證「拒絕非屬性欄位」的邏輯分支，不能只靠合成測試資料。
# 別因為手癢就把其他 dict/list 欄位也一起剔除。
STRIP_BIN_FIELDS = {"mItemDataClient"}


def fetch_json(url: str) -> dict:
    print(f"  ↓ {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as r:
        return json.load(r)


def is_sr_standard(item: dict, item_id: str) -> bool:
    gold = item.get("gold", {})
    return (
        item.get("maps", {}).get("11") is True
        and gold.get("purchasable") is True
        and gold.get("total", 0) > 0
        and int(item_id) < 10000
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    print("裝備（zh_TW）")
    items = fetch_json(f"{DDRAGON}/zh_TW/item.json")
    keep_ids = {i for i, v in items["data"].items() if is_sr_standard(v, i)}
    keep_ids |= {str(i) for i in ANCHOR_IDS | GOLDEN_IDS}
    # 保留幾件變體 ID 以測試過濾邏輯
    variants = [i for i in items["data"] if int(i) >= 10000][:6]
    keep_ids |= set(variants)
    trimmed_items = {
        "version": items["version"],
        "data": {i: items["data"][i] for i in sorted(keep_ids, key=int) if i in items["data"]},
    }
    (OUT / "ddragon_items.json").write_text(
        json.dumps(trimmed_items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  → {len(trimmed_items['data'])} 件裝備")

    for locale in ("zh_TW", "en_US"):
        print(f"英雄（{locale}）")
        champs = fetch_json(f"{DDRAGON}/{locale}/champion.json")
        keys = set(CHAMPION_KEYS)
        keys |= {k for k in champs["data"] if k.startswith("Jade_")
                 and k.removeprefix("Jade_") in CHAMPION_KEYS}
        trimmed = {
            "data": {k: champs["data"][k] for k in sorted(keys) if k in champs["data"]}
        }
        (OUT / f"ddragon_champions_{locale}.json").write_text(
            json.dumps(trimmed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        print(f"  → {len(trimmed['data'])} 隻英雄")

    print("bin 檔（15.8 MB，裁剪中）")
    raw = fetch_json(CDRAGON)
    wanted = {f"Items/{i}" for i in keep_ids}
    trimmed_bin = {
        key: {f: v for f, v in entry.items() if f not in STRIP_BIN_FIELDS}
        for key, entry in raw.items()
        if key in wanted
    }
    (OUT / "items_bin.json").write_text(
        json.dumps(trimmed_bin, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  → {len(trimmed_bin)} 個 bin 條目")

    total = sum(f.stat().st_size for f in OUT.iterdir())
    print(f"\nfixture 總大小: {total / 1024:.0f} KB")


if __name__ == "__main__":
    main()
