# lol-cp

英雄聯盟召喚峽谷裝備金幣效率（CP值）分析工具。

設計規格：`docs/superpowers/specs/2026-08-12-lol-item-gold-efficiency-design.md`

## 執行

    uv sync
    uv run lolcp

## 架構

Clean Architecture 四層，依賴方向一律朝內：

    presentation ──→ application ──→ domain
                          ↑
                  infrastructure

僅 `src/lolcp/main.py`（組裝根）認識所有層。

### 刻意的例外：numpy／scipy 出現在 domain

`domain/pricing.py` 的最小平方定價法需解 `A·x ≈ b`，直接 import numpy 與 scipy。

嚴格分層會要求把 solver 抽成 port 移到 infrastructure。**這裡刻意不那樣做。**
Clean Architecture 的用意是「業務規則不依賴 I/O、框架、UI」，而 numpy 三者皆非
——它是純函式數學庫，沒有副作用、沒有外部狀態、不綁定執行環境。為教條把一個矩陣
運算拆成跨層介面，只會讓最核心的計算變難讀，且 `A`、`b` 的型別在介面上很尷尬。

除 numpy／scipy 外，**domain 不得 import 任何第三方庫**。

### 為什麼屬性來自 CommunityDragon 而非 Riot 官方

Riot 的 Data Dragon `item.json` 的 `stats` 欄位只有 12 種屬性，缺技能加速、
暴擊傷害、穿透、韌性等現代屬性，影響 41% 的召喚峽谷裝備。CommunityDragon 的
`items.cdtb.bin.json` 是遊戲原始數值檔，有 24 種屬性欄位。

但 bin 檔完全不存法力，所以法力來自 Data Dragon。兩者重疊屬性經實測零分歧。
