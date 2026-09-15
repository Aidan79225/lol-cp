# 英雄聯盟裝備 CP值 分析工具 — 設計規格

日期：2026-08-12
狀態：已核准，待撰寫實作計畫
資料版本基準：Data Dragon `16.15.1`

---

## 1. 目標

一個本機桌面工具，抓取當前版本英雄聯盟的裝備數值，計算**召喚峽谷**裝備的金幣效率（CP值），供作者個人分析選裝。

作者常玩英雄：**達瑞文（Draven）、凱爾（Kayle）、煞蜜拉（Samira）**。工具需支援「以特定英雄視角評估裝備價值」，且新增英雄的成本要低。

三隻英雄的 `tags` 皆含 `Marksman`（見 §7.5），因此 v1 的實際覆寫需求極低——這強化了「角色預設 + 只寫差異」的設計選擇，但也意味著遮罩機制在此英雄池中主要作用於法術強度類裝備。

### 1.1 技術約束（使用者指定）

| 項目 | 決定 |
|---|---|
| 套件管理 | `uv` |
| GUI | PySide6 |
| 架構 | Clean Architecture |
| Python | **3.13**（`pyproject.toml` 釘住 `>=3.13,<3.14`） |

**版本選擇依據**（`uv lock` 實測，非推測）：

| 套件 | 版本 | 限制 |
|---|---|---|
| PySide6 | 6.11.1 | `requires_python = ">=3.10,<3.15"`；wheel 為 `cp310-abi3-macosx_13_0_universal2`（穩定 ABI，不需編譯 Qt） |
| numpy | 2.5.2 | arm64 wheel 涵蓋 cp312–cp315 |
| scipy | 1.18.0 | arm64 wheel 涵蓋 cp312–cp314，**無 cp315** |

3.12 / 3.13 / 3.14 的 `uv lock` 解析結果完全相同。**3.15 出局**（PySide6 上限 + scipy 無 wheel）。選 3.13 而非 3.14 是因為後者已是 PySide6 支援天花板，無升級空間；選 3.13 而非 3.12 是因為解析結果既然相同，沒有落後兩版的理由。

### 1.2 明確非目標（v1 不做）

- **Level 3 邊際效益模型**（見 §5.4）— ~~架構留擴充點，另案處理~~
  2026-08-17 已實作窄版（`2026-08-17-marginal-model-design.md`）：
  屬性物理三公式＋標準目標，無技能倍率表 —— 比 §5.4 想像的範圍窄，勿混同
- 召喚峽谷以外的地圖
- 出裝路線推薦、合成樹最佳化 —— 2026-09-14 出裝推薦立案
  （`2026-09-14-build-optimizer-design.md`：6 件成品＋順序）；合成樹／部件路徑仍為非目標
- 符文與召喚師技能
- 跨版本比較的 UI（快取結構已支援，不做介面）
- 對戰紀錄／帳號整合
- 打包為 `.app` 發佈 — v1 能 `uv run lolcp` 啟動即可

### 1.3 這個工具回答的問題（重要界定）

線性 CP值 回答的是「**這件裝備的原料划不划算**」——3500g 買到的屬性值不值 3500g。它**不**回答「這件裝備對我的英雄好不好」，後者需要非線性的實戰效益模型（§5.4）。兩者都有用，但不可混為一談。英雄權重（§7）讓前者更貼近你的英雄，但不改變它的本質。

---

## 2. 環境前置作業

```bash
brew install uv      # ✅ 已安裝（uv 0.12.3）
brew install node    # 選用，尚未安裝。僅 brainstorming 瀏覽器版需要
```

Python 由 uv 管理（`uv python install 3.13`），不使用系統或 pyenv 的 Python。

> **已知環境干擾**：本機 pyenv shim（`~/.pyenv/shims/python`）會讓 `uv pip install --python-version` 之類的指令探測失敗（`pyenv: python: command not found`）。在 uv 專案內操作（`uv sync` / `uv run` / `uv lock`）不受影響，因為 uv 使用專案自己的 `.venv`。實作時一律用專案內指令，不要用 `uv pip --python-version`。

---

## 3. 資料來源調查結果

以下為實測結論（非推測），構成後續設計的依據。

### 3.1 Data Dragon（Riot 官方靜態 CDN）

```
https://ddragon.leagueoflegends.com/api/versions.json
https://ddragon.leagueoflegends.com/cdn/<version>/data/<locale>/item.json
https://ddragon.leagueoflegends.com/cdn/<version>/data/<locale>/champion.json
```

免 API key。`16.15.1` 共 868 件裝備。召喚峽谷可購買的篩選條件為 `maps["11"] == true` ∧ `gold.purchasable` ∧ `gold.total > 0` ∧ **`int(id) < 10000`**（見 §3.5），符合者 **212 件**。

**可靠欄位**：中文名稱、圖示、`gold.total`、`gold.sell`、`maps`、`from`/`into` 合成樹、`stats.FlatMPPoolMod`。

**缺陷**：`stats` 的**欄位種類**不足，只有 12 種，缺整批現代屬性。並非「大量空白」（僅 8%，18/212 完全空白），而是 schema 本身不完整：

| Data Dragon 缺少的屬性 | 影響 SR 裝備數 |
|---|---|
| 技能加速 | 69 |
| 魔法穿透 | 8 |
| 韌性 | 7 |
| 物理穿透 | 4 |
| 暴擊傷害 | 3 |

合計 **86/212（41%）** 裝備會被系統性低估。

實例（無盡之刃 3031）：`description` 寫「75 物攻 / 25% 暴擊率 / **30% 暴擊傷害**」，但 `stats` 只有 `FlatPhysicalDamageMod: 75` 與 `FlatCritChanceMod: 0.25`，暴擊傷害不存在。

### 3.2 已排除的來源

| 來源 | 實測結果 |
|---|---|
| Meraki Analytics CDN | **已停止服務**，所有路徑回 404 |
| CommunityDragon client `v1/items.json` | 活著、有 `zh_tw`，但**零結構化屬性**，僅描述字串 |

### 3.3 CommunityDragon 遊戲原始檔（採用為屬性來源）

```
https://raw.communitydragon.org/latest/game/items.cdtb.bin.json      # 15.8 MB
```

遊戲真正的數值檔，key 形如 `Items/3031`。**29 種屬性欄位**（Data Dragon 的兩倍以上；其中 5 個使用非 `mXxxMod`
命名慣例 —— `PhysicalLethality` 裸名、`flatMPPoolMod` 等小寫開頭 ——
曾因偵測器盲點被靜默丟棄，2026-08-15 修復，見
`2026-08-15-bin-field-blind-spot-design.md`），涵蓋標準 ID 的 SR 可購買裝備 **94%（199/212，盲點修復後）**。

實例（`Items/3031`）：
```
mFlatPhysicalDamageMod: 75.0
mFlatCritChanceMod:     0.25
mFlatCritDamageMod:     0.30    ← Data Dragon 漏掉的
```

**缺陷**：
- 無在地化名稱（僅 `Item_3031_Name` 這類 loc key）
- 無總價（`price: 725` 是合成價，非 `total: 3500`）
- 無地圖限制
- ~~完全不存法力~~ **更正（2026-08-15）**：bin 以小寫 `flatMPPoolMod` 存法力
  （15 件；女神之淚、藍水晶等仍無），DD 23 件補缺，重疊值零分歧

**雜湊化欄位**：存在 8 種未解名欄位（`{4f958685}` 等），已逐一檢視，**全非屬性**（守衛、裝備群組、鞋子升級 metadata）。無屬性靜默遺失風險。

### 3.4 兩來源交叉比對（決定合併規則）

| 比對項 | 結果 |
|---|---|
| 只有 Data Dragon 有的屬性 | ~~法力~~ 更正：bin 亦有 15 件（小寫欄位），DD 23 件補缺 |
| 只有 bin 有的屬性 | 技能加速、暴擊傷害、魔穿、物穿、韌性、治療量、緩速抗性 |
| 重疊屬性數值分歧 | **0 筆**（完全一致） |

零分歧可直接作為測試斷言：日後出現分歧即 schema 漂移警報。

### 3.5 裝備 ID 變體污染（必須過濾）

`maps["11"]` 為 `true` 的裝備中，有 **36 件使用非標準 ID**：前綴 `32`（21 件）與 `66`（15 件），各自包裹一個標準 ID（`323070` = `32` + `3070` 女神之淚）。這些是其他遊戲模式的變體，與 §3.6 的 `Jade_` 英雄同性質。

**它們必須被過濾，理由不只是重複計數**：

- **23 件是純重複** — 標準版也在集合內（`3003` 大天使之杖 與 `323003` 同名同價 2900g）
- **部分變體價格不同** — `2065` 蘇瑞亞的戰歌 2200g vs `322065` 2600g。同樣屬性、不同售價，在 NNLS 的聯立矩陣裡是**互相矛盾的方程式**，會實際扭曲解出的單價
- **錨定裝備也有變體** — 長劍 `1036`(350g/10AD) 另有 `771036`(400g/10AD)；治療寶珠 `1006`(300g) 另有 `771006`(180g)，且後者用的是**不同的屬性欄位**（`mFlatHPRegenMod` 而非 `mPercentBaseHPRegenMod`）

最後一點是關鍵：**錨定裝備一律以數值 ID 查找，絕不以名稱查找。** 用名稱查會拿到變體，單價全錯且不會報錯。

**過濾規則**：`int(id) < 10000`。過濾掉的件數須記錄（目前 36），數量劇變時應調查。

> **與英雄不同：裝備名稱不唯一，不可斷言唯一。** 標準 ID 內仍有 3 組同名裝備——熾爪幼犬（`1101`/`1107`）、馭風幼狐（`1102`/`1106`）、重踏幼螈（`1103`/`1105`）——這些是叢林寵物的正常變體，兩者皆為合法遊戲內容，必須保留。

### 3.6 英雄資料

`champion.json` 共 **233 個條目，但僅 173 隻真英雄**。60 個 `Jade_` 前綴變體（numeric id ≥ 60000）為其他模式資料，必須濾除，否則視角選單會出現重複英雄（凱爾即在重複名單內）。

```
key=Kayle        id=30     ← 真英雄
key=Jade_Kayle   id=60030  ← 濾除
```

`partype` 為**在地化字串**（zh_TW 為 `'魔力'`）。判斷非法力英雄必須讀 **en_US**：

| 判斷規則 | 涵蓋英雄數 | 備註 |
|---|---|---|
| `stats.mp == 0` | 11 | **不足** — 犽宿 `mp=100` 但資源是 Flow |
| `partype != "Mana"`（en_US） | **33** | 採用此規則 |

由此確立架構規則：**邏輯欄位讀 `en_US`，顯示欄位讀 `zh_TW`**。

---

## 4. 架構分層

### 4.1 依賴方向

```
presentation ──→ application ──→ domain
                      ↑
              infrastructure
              （實作 ports，箭頭朝內）
```

僅 `main.py`（組裝根）認識所有層，負責依賴注入。**domain 不 import 任何層；application 只認 domain 與自身 ports。**

### 4.2 目錄結構

```
lol-cp/
├── pyproject.toml                  # uv, requires-python = ">=3.13,<3.14"
├── src/lolcp/
│   ├── domain/                     # 純邏輯，零 I/O
│   │   ├── entities.py             # Item, Champion
│   │   ├── stats.py                # StatKey(Enum), StatLine
│   │   ├── pricing.py              # PriceTable, PriceDeriver(Protocol),
│   │   │                           #   CanonicalDeriver, LeastSquaresDeriver
│   │   ├── weights.py              # StatWeights, WeightResolver
│   │   └── valuation.py            # ItemValuation(Protocol), LinearValuation,
│   │                               #   ValuationResult, Contribution, ItemComparison
│   ├── application/
│   │   ├── ports.py                # ItemRepository, ChampionRepository,
│   │   │                           #   WeightConfigSource, PatchGateway
│   │   └── use_cases/
│   │       ├── sync_game_data.py
│   │       ├── list_valuations.py
│   │       └── explain_item.py
│   ├── infrastructure/
│   │   ├── http/                   # ddragon_client.py, cdragon_client.py
│   │   ├── cache/                  # patch_cache.py
│   │   ├── mapping.py              # bin/DD 欄位 → StatKey + 單位正規化
│   │   └── repositories/           # composite_item_repository.py,
│   │                               #   file_champion_repository.py,
│   │                               #   toml_weight_source.py
│   ├── presentation/
│   │   ├── main_window.py
│   │   ├── item_table_model.py     # QAbstractTableModel
│   │   └── widgets/                # detail_panel, profile_selector, filter_bar
│   └── main.py                     # 組裝根
├── config/
│   ├── anchors.toml                # 錨定基礎裝備表（附選擇理由註解）
│   ├── role_defaults.toml          # 6 種 tag 的預設權重
│   └── champions/                  # Kayle.toml（Draven/Samira 用預設即可）
└── tests/
    ├── domain/
    ├── golden/
    ├── infrastructure/
    └── fixtures/16.15.1/           # 裁剪後的資料（~200 KB）
```

### 4.3 兩個刻意的架構判斷

**numpy／scipy 放在 domain 內。** 最小平方法需解 `A·x ≈ b`。嚴格分層會要求把 solver 抽成 port 移到 infrastructure，但 Clean Architecture 的用意是「業務規則不依賴 I/O、框架、UI」，而 numpy 三者皆非——它是純函式數學庫。為教條把矩陣運算拆成跨層介面只會讓最核心的計算難讀，且 `A`、`b` 的型別在介面上很尷尬。此例外須在 README 說明理由。

**`config/` 置於專案內，非使用者家目錄。** 錨定表、角色預設、英雄覆寫是會手改、需版控、需 `git diff` 追溯的**專案資產**，不是使用者設定。僅快取（15.8 MB）走 `~/.cache/lol-cp/`。

---

## 5. Domain 核心計算

### 5.1 StatKey 與單位正規化

召喚峽谷共出現 **21 種屬性**。原始資料單位不一致，是會靜默算錯的陷阱：

```
bin:  mFlatCritChanceMod     = 0.25    ← 分數
      mPercentAttackSpeedMod = 0.10    ← 分數
      mFlatPhysicalDamageMod = 75.0    ← 絕對值
```

**mapping 層執行一次正規化：百分比類屬性一律轉為「以 1% 為單位」。**

```python
0.25  →  StatLine(StatKey.CRIT_CHANCE, 25.0)
0.10  →  StatLine(StatKey.ATTACK_SPEED, 10.0)
75.0  →  StatLine(StatKey.AD, 75.0)
```

正規化後單價即社群慣用值（40 g/1%、25 g/1%），而非 4000 g/1.0 這種反直覺數字。

**不變量：轉換只存在於 mapping 層；domain 內的數值一律已正規化。** 須有測試守護。

**哪些欄位要 ×100 不能靠前綴判斷。** `mFlatCritDamageMod = 0.30` 帶 `Flat` 前綴卻是分數；欄位名完全不可靠。下表由實際值域推定（`16.15.1` 全裝備掃描），**須寫成明確常數集合，不得用字串前綴推導**：

| 需 ×100（分數） | 不需轉換（絕對值） |
|---|---|
| `mFlatCritChanceMod` (0.08–0.5) | `mFlatPhysicalDamageMod` (4–150) |
| `mFlatCritDamageMod` (0.3–0.45) ← **陷阱** | `mFlatMagicDamageMod` (7–300) |
| `mPercentAttackSpeedMod` (0.1–0.7) | `mFlatHPPoolMod` (25–1100) |
| `mPercentBaseHPRegenMod` (0.25–2.0) | `mFlatArmorMod` (8–100) |
| `mPercentLifeStealMod` (0.05–0.3) | `mFlatSpellBlockMod` (8–100) |
| `mPercentMovementSpeedMod` (0.04–0.15) | `mFlatMovementSpeedMod` (25–100) |
| `mPercentHealingAmountMod` (0.08–0.2) | `mAbilityHasteMod` (5–40) |
| `mPercentTenacityItemMod` (0.2–0.3) | `mFlatHPRegenMod` (0.8–4) |
| `mPercentSlowResistMod` (0.15–0.4) | `mFlatMagicPenetrationMod` (10–20) |
| `mPercentMagicPenetrationMod` (0.08–0.4) | `MANA`（來自 Data Dragon，絕對值） |
| `mPercentArmorPenetrationMod` (0.08–0.4) | |

上列 21 項即 §3.1 所述「SR 出現的 21 種屬性」。

**SR 未出現但需納入 `StatKey` 的欄位**（供未知欄位偵測用，映射存在但實務上不會出現）：`mPercentCooldownMod`（值為**負數** −0.2～0.01）、`mFlatArmorPenetrationMod`（值域 0.05–22，**語意混雜**，僅 4 件非 SR 裝備，遇到須警告）、`mFlatAttackRangeMod`、`mPercentMultiplicativeAttackSpeedMod`。

### 5.2 屬性合併規則

```python
stats = bin_stats(item_id)              # 基底：21 種中的 20 種
stats |= ddragon_mana_only(item_id)     # 補：法力（bin 無此欄位）
```

規則刻意寫窄：**Data Dragon 僅用於補法力，不參與其他屬性。** bin 是遊戲原始檔即 ground truth，讓第二來源有機會覆寫只會製造不確定性。重疊部分執行一致性檢查，不一致則記錄警告（不靜默通過）。

### 5.3 兩種定價法（並列顯示）

```python
class PriceDeriver(Protocol):
    def derive(self, items: Sequence[Item]) -> PriceTable: ...
```

#### CanonicalDeriver — 錨定基礎裝備

21 種屬性中可定價 **11 種**：

| 屬性 | 錨定裝備 | 單價 |
|---|---|---|
| 物理攻擊 | 長劍 (1036) 350g / 10 | 35.0 |
| 法術強度 | 增幅典籍 (1052) 400g / 20 | 20.0 |
| 生命 | 紅水晶 (1028) 400g / 150 | 2.667 |
| 法力 | 藍水晶 (1027) 300g / 300 | 1.0 |
| 護甲 | 布甲 (1029) 300g / 15 | 20.0 |
| 魔法抗性 | 抗魔斗篷 (1033) 400g / 20 | 20.0 |
| 暴擊率 | 靈巧披風 (1018) 600g / 15% | 40.0 /1% |
| 攻擊速度 | 短劍 (1042) 250g / 10% | 25.0 /1% |
| 技能加速 | 發光結晶 (2022) 250g / 5 | 50.0 |
| 移動速度 | 鞋子 (1001) 300g / 25 | 12.0 |
| 基礎生命回復 | 治療寶珠 (1006) 300g / 100% | 3.0 /1% |

> **正規化陷阱（實際踩過）**：`mPercentBaseHPRegenMod` 的原始值是分數（治療寶珠 `1.0` ↔ 描述「100% 基礎生命回復」、星體抗力 `0.75` ↔「75%」）。若拿未正規化的 `1.0` 去除 300g，會得到 `300.0` 的單價；套上正規化後的 `100.0` 數量就放大 100 倍。**錨定表的單價必須與正規化後的單位一致。** 此案例須成為明確測試（見 §10.2）。

錨定裝備為**明確選定**，非自動取最便宜者。兩個需說明的選擇：

- **暴擊率選靈巧披風（40.0）而非神聖之劍（50.0）** — 40 為社群通用值
- **物攻選長劍（35.0）而排除剔除鐮刀（64.29）** — 後者為帶被動的線上裝，單價被被動污染

錨定選擇及理由寫入 `config/anchors.toml` 註解，可爭論、可修改。

**三種屬性為扣除錨**（機制與驗證見 `2026-08-15-deduction-anchors-design.md`）：

- 生命偷取：吸血鬼權杖 (900 − 15AD×35) / 7% = 375/7 ≈ 53.571 每 1%
- 百分比物穿：最後耳語 (1450 − 20AD×35) / 18% = 750/18 ≈ 41.667 每 1%
  （成品的試算值被被動稀釋：致死宣告 25.8、席利妲 19.3、多明尼克 30.7，不採）
- 穿甲（固定物穿）：殘暴之力 (1000 − 20AD×35) / 10 = 30.0 每 1 穿甲
  （盲點修復後現身，12 件；見 `2026-08-15-bin-field-blind-spot-design.md`）

**其餘 11 種無錨可定價**，介面標示「未定價」，**不當作 0 併入**：

暴擊傷害、固定生命回復、移速%、治療與護盾力量、韌性、緩速抗性、
固定魔穿、百分比魔穿、全能吸血、基礎魔力回復、固定魔力回復。

（暴擊傷害連扣除法也定不出來：全 SR 只有無盡之刃帶它，且 IE 的其他屬性
已比整件貴 125g，餘額為負 —— 這正是扣除錨「殘額必須 > 0」驗證擋下的情況。
全能吸血與魔回暫無明顯乾淨錨，留待爭論。）

（註：固定物穿在 SR 可購買裝備中未出現，故不列。）

#### LeastSquaresDeriver — 全裝備聯立求解

```python
# 解 A·x ≈ b，x ≥ 0
A = 198 × 21   屬性矩陣（已正規化，僅標準 ID）
b = 198        各裝備總價
x = scipy.optimize.nnls(A, b)
```

用非負最小平方（NNLS）而非普通最小平方，因單價不應為負。優點：21 種全有價、無黑洞，離群裝備自動平均化。代價：數字不再能用「長劍 350g」直接驗證。

### 5.4 估值

```python
class ItemValuation(Protocol):
    def evaluate(self, item: Item, prices: PriceTable,
                 weights: StatWeights) -> ValuationResult: ...
```

```
每條屬性貢獻 = 數量 × 單價 × 權重
總價值       = Σ 貢獻
CP值         = 總價值 / 售價
殘差         = 售價 − 總價值
```

**殘差的兩種語意（介面措辭須區分）**：
- **正殘差** — 至少這些金幣花在被動／主動效果上
- **負殘差** — 屬性本身已超值

```python
@dataclass(frozen=True)
class Contribution:
    stat: StatKey
    amount: float          # 已正規化
    unit_price: float
    weight: float
    gold: float            # amount × unit_price × weight

@dataclass(frozen=True)
class ValuationResult:
    item: Item
    contributions: tuple[Contribution, ...]
    unpriced: tuple[StatKey, ...]      # 有此屬性但無單價
    masked: tuple[StatKey, ...]        # 有單價但權重為 0
    total_value: float
    ratio: float                       # CP值
    residual: float

@dataclass(frozen=True)
class ItemComparison:
    canonical: ValuationResult
    least_squares: ValuationResult
    delta: float                       # least_squares.ratio − canonical.ratio
```

**`unpriced` 與 `masked` 必須分開儲存。** 「這屬性算不出價」與「這屬性對你的英雄沒用」是完全不同的事；混為一談就無法判斷 CP值 低是資料限制還是英雄不適配。

### 5.5 Level 3 擴充點（v1 不實作）

`ItemValuation` 是 Protocol 而非具體類別，正是為此保留：

```
ItemValuation (Protocol)
  ├─ LinearValuation(CanonicalPrices)        ← v1
  ├─ LinearValuation(LeastSquaresPrices)     ← v1
  └─ MarginalEfficiencyValuation(champion)   ← 未來，另案
```

Level 3 不是擴充而是**替換核心**，因為線性模型假設「屬性可獨立定價後相加」，而實戰價值是相乘的：

```
DPS = AD × 攻速 × (1 + 暴擊率 × 暴擊傷害)
EHP = 生命 × (1 + 護甲/100)
冷卻 = 基礎 × 100/(100 + 技能加速)          ← 邊際遞減
```

外加英雄專屬機制（犽宿暴擊率翻倍、破敗王者之刃吃對手最大生命）皆戳破線性假設。Level 3 另需英雄基礎數值、技能係數（Data Dragon 僅埋在 tooltip 字串中，需解析）、假想對手護甲魔抗、戰鬥時長、技能循環——工程量差一個量級。

**`evaluate` 收 `weights` 作為參數而非寫死，是 v1 唯一必須保留的 seam。**

---

## 6. 資料管線

### 6.1 快取結構

```
~/.cache/lol-cp/
├── 16.15.1/
│   ├── ddragon_items.json                692 KB
│   ├── ddragon_champions_zh_TW.json      顯示用
│   ├── ddragon_champions_en_US.json      邏輯用（partype/tags）
│   ├── items_bin.json                    15.8 MB
│   └── .complete                         ← 完整性標記
└── 16.16.1/ ...
```

**`.complete` 標記為必要機制。** 下載寫入暫存目錄，全部成功才 `rename` 至正式目錄並寫入標記（同檔案系統的 `rename` 為原子操作）。無標記的目錄一律視為不存在。否則 15.8 MB 下載中途關閉 app，下次啟動將讀到截斷的 JSON。

按版本號分目錄、舊版不刪，跨版本比較日後不需改結構。

### 6.2 啟動流程

```
1. GET versions.json  (2 KB, timeout 3s)
   ├─ 成功 → latest = versions[0]
   └─ 失敗 → 用本地最新完整版本，狀態列標示「離線」
2. cache.is_complete(latest)?
   ├─ 是 → 直接載入（瞬開）
   └─ 否 → 背景下載，進度條 + 可取消
             ├─ 成功 → rename → 載入
             └─ 失敗 → 退回本地最新完整版，標示「更新失敗，顯示 16.15.1」
3. 無任何本地完整版本且網路失敗 → 錯誤畫面 + 重試鈕
```

### 6.3 執行緒與分層

`SyncGameData` use case **不得認識 Qt**。它接收普通回呼，由 presentation 層 adapter 轉為 Qt signal 並在 worker thread 執行。15.8 MB 下載不可阻塞 UI 執行緒。

```python
# application：不知 Qt 存在
def sync(self, on_progress: Callable[[int, int], None]) -> PatchVersion: ...

# presentation：QThread worker，回呼轉 signal
worker.progress.connect(self.progress_bar.setValue)
```

---

## 7. 英雄權重（Level 1）

### 7.1 型別決定

`StatWeights = dict[StatKey, float]`，取值 **0.0 ～ 1.0**（非布林開關）。

後果：Level 1 與 Level 2 在 domain 層**完全同型**，差別僅在「是否有滑桿 UI」。日後加滑桿是純 presentation 工作。

代價：CP值 數字不再自我解釋。**介面必須隨時顯示當前英雄視角，且客觀值須可見。**

### 7.2 三層解析

```python
class WeightResolver:
    def resolve(self, champion: Champion | None) -> StatWeights:
        if champion is None:
            return StatWeights.uniform(1.0)                # 全域客觀視角
        w = self.role_defaults.union_max(champion.tags)     # ① 角色預設
        w = self.resource_rule.apply(w, champion)           # ② 資源類型
        w = self.overrides.apply(w, champion.key)           # ③ 手動覆寫
        return w
```

**新增英雄成本為零** — `tags` 自動給出預設，173 隻立即可用。僅在預設不準時撰寫覆寫檔。

### 7.3 ① RoleDefaults

6 種 tag（Fighter / Tank / Mage / Marksman / Assassin / Support）各一份權重，取英雄 `tags` 的**聯集 `max`**。

聯集用 `max` 而非平均：遮罩錯誤的兩方向代價不對稱——**把英雄實際會用的屬性設為 0 會直接隱藏資訊**，比多算一個邊緣屬性糟得多。

摘錄（完整表見 `config/role_defaults.toml`）：

| | AD | AP | 生命 | 護甲 | 暴擊 | 攻速 | 技能加速 | 韌性 | 魔穿 | 物穿 |
|---|---|---|---|---|---|---|---|---|---|---|
| Fighter | 1.0 | 0 | 1.0 | 0.9 | 0.2 | 0.6 | 1.0 | 0.9 | 0 | 0.7 |
| Tank | 0.3 | 0 | 1.0 | 1.0 | 0 | 0.3 | 0.9 | 1.0 | 0 | 0 |
| Mage | 0 | 1.0 | 0.6 | 0.5 | 0 | 0.1 | 1.0 | 0.5 | 1.0 | 0 |
| Marksman | 1.0 | 0 | 0.4 | 0.3 | 1.0 | 1.0 | 0.5 | 0.4 | 0 | 0.8 |
| Assassin | 1.0 | 0 | 0.4 | 0.3 | 0.6 | 0.5 | 0.8 | 0.4 | 0 | 1.0 |
| Support | 0.2 | 0.7 | 0.7 | 0.6 | 0 | 0.2 | 1.0 | 0.6 | 0.5 | 0 |

### 7.4 ② ResourceRule

`partype != "Mana"`（讀 **en_US**）→ 法力權重 0。涵蓋 33 隻，含犽宿（Flow）。

`partype` 為空字串者（1 隻）視為未知，**不歸零**（隱藏資訊比多算屬性糟），並記錄警告。

### 7.5 ③ ChampionOverride

**設定檔鍵名規則**：所有 toml（`anchors.toml`、`role_defaults.toml`、`champions/*.toml`）的屬性鍵一律為 `StatKey` 成員名的 **snake_case**，單一來源、無別名表。

```
StatKey.AD                  → ad
StatKey.ABILITY_HASTE       → ability_haste
StatKey.ARMOR_PEN_PERCENT   → armor_pen_percent
StatKey.CRIT_CHANCE         → crit_chance
```

未知鍵名須報錯並列出合法選項（見 §9.1）——靜默忽略會讓打錯字的權重看似生效。

僅寫差異。作者三隻英雄的實際結果：

作者三隻英雄的 `tags` 與覆寫需求：

| 英雄 | `tags` | 解析結果 | 需覆寫 |
|---|---|---|---|
| 達瑞文 | `['Marksman']` | 直接套用 Marksman 預設（單一 tag，無需聯集） | **無** |
| 煞蜜拉 | `['Marksman', 'Assassin']` | 聯集正確捕捉刺客的穿透需求 | **無** |
| 凱爾 | `['Mage', 'Marksman']` | 聯集正確捕捉混合傷害（AD 1.0 ∧ AP 1.0） | 2 行 |

```toml
# config/champions/Kayle.toml
# Mage+Marksman 聯集已正確捕捉混合傷害：AD 1.0 AP 1.0 攻速 1.0 暴擊 1.0
armor_pen_flat    = 0.4    # 後期傷害大半為魔法，物穿價值減半
armor_pen_percent = 0.4
```

**三隻英雄裡兩隻零覆寫、一隻兩行**，即「新增英雄方便性」的具體樣貌。作者日後加新英雄的流程是：先什麼都不寫、看預設準不準，僅在不同意時補幾行。

---

## 8. 介面

### 8.1 主畫面：表格 + 右側詳情面板

```
視角: [全域|▣達瑞文|凱爾|煞蜜拉]  篩選:[AD ▾]  版本: 16.15.1  [檢查更新]
┌─表格──────────────────────┐┌─詳情──────────────┐
│裝備      售價   權威   平方   差異││ 中婭沙漏      3250g  │
│▸無盡之刃  3500  103.6   〔示意〕  ││ ▾ 屬性拆解           │
│ 三相之力  3333   82.2   〔示意〕  ││ 105 AP    ×20.0 ×0.0 │
│ 殞落王者  3200   80.0   〔示意〕  ││       = 0g  ⚠ 遮罩   │
│ 中婭沙漏  3250    9.2   〔示意〕  ││  50 護甲  ×20.0 ×0.3 │
│                                  ││       = 300g         │
│                                  ││ ──────────────────── │
│                                  ││ 價值 300 / 3250      │
│                                  ││    = 9.2%            │
│                                  ││ 殘差 +2950g（被動）  │
└──────────────────────────┘└──────────────────┘
狀態: 3 個未知屬性欄位  |  bin↔DD 衝突 0 筆  |  低信賴單價 4 種
```

上表「權威」欄為**達瑞文視角的實際計算值**，與 §10.2 黃金測試一致。「平方」欄標示〔示意〕是因為 NNLS 需 scipy，設計階段未實際求解，實作後補入黃金測試。

三個標示是這個工具全部的分析價值所在：`⚠ 遮罩`（英雄用不到）、`⚠ 未定價`（算不出來）、`殘差`（被動的隱含價值）。

達瑞文視角的四筆剛好示範了英雄權重的三種不同效果：

- **無盡之刃 103.6%（與全域相同）** — 只有物攻與暴擊率，兩者對 ADC 權重皆為 1.0，完全適配
- **殞落王者之劍 80.0%（與全域相同）** — 吸血已由扣除法計價，殘差 639g 是被動（現血狂擊）的隱含價值，與英雄無關
- **三相之力 109.5% → 82.2%** — 生命（0.4）與技能加速（0.5）對 ADC 折價
- **中婭沙漏 95.4% → 9.2%** — 105 點法術強度全數遮罩，只剩低權重護甲

「與全域相同」這兩筆很重要：它證明英雄視角不是把所有數字一律往下壓，而是有選擇性的。

### 8.2 元件

| 元件 | 說明 |
|---|---|
| `ProfileSelector` | 視角切換（全域 + 已設定英雄）。切換即重算 |
| `FilterBar` | 依 `tags` 篩選（AD/AP/坦/…）、依價格區間 |
| `ItemTableModel` | `QAbstractTableModel`，可排序。欄位：裝備、售價、權威 CP值、平方 CP值、差異 |
| `DetailPanel` | 屬性逐條拆解、未定價清單、遮罩清單、殘差 |
| 狀態列 | 版本、離線標示、診斷計數（未知欄位／衝突／低信賴） |

---

## 9. 錯誤處理

### 9.1 核心原則：絕不靜默丟棄

最危險的失效不是崩潰，是**安靜地算錯**。每一個「不認識這東西」的分支都必須留下痕跡。

| 失效 | 處理 |
|---|---|
| bin 出現未知屬性欄位 | 收集，狀態列顯示計數，可展開看名稱。不丟棄、不當 0 |
| bin 與 DD 重疊屬性不一致 | 目前 0 筆。非 0 → 記錄警告 + 顯示筆數，採用 bin |
| item id 僅在單邊出現 | 記錄雙向計數，診斷面板可查 |
| 錨定裝備消失 | **啟動時大聲失敗**：「錨定裝備 1036 不存在於 \<version\>」。藍水晶曾被移除，此事遲早發生 |
| 英雄設定檔含未知屬性名 | 明確報錯並列出合法選項。打錯字若靜默忽略，使用者會誤以為權重生效 |
| 英雄名稱重複 | 斷言失敗（§3.6），不靜默去重 |
| 裝備使用非標準 ID | 過濾並記錄件數（§3.5）。**裝備名稱不唯一，不可斷言唯一** |
| 網路失敗 | 見 §6.2 離線降級 |

### 9.2 最小平方法的信賴度

**屬性出現次數過少** — 僅出現在少數裝備的屬性（如暴擊傷害僅 3 件），解出的單價實質是那幾件的殘差在硬湊。規則：**出現次數 < 5 者標為低信賴**，介面以灰字加註。

**「解出 0」與「無價格」須區分** — NNLS 可能將某屬性解為 `0.0`（解出來就是零）；`unpriced` 是無法定價。`PriceTable` 中為不同狀態（`0.0` vs `None`），不可混。

另計算並顯示矩陣 condition number，過高時警告整欄不可信。

---

## 10. 測試策略

### 10.1 domain 單元測試（快、純、佔多數）

單位正規化、加權貢獻、殘差正負、`unpriced`／`masked` 分離、`union_max`、ResourceRule、覆寫合併、NNLS（用已知解的小矩陣）。

### 10.2 黃金測試

將 `16.15.1` 資料**裁剪後**入庫（僅 SR 裝備 + 錨定裝備，約 200 KB，非 15.8 MB），斷言以下實測值：

```
# 錨定單價（正規化後）
長劍 → 35.0        增幅典籍 → 20.0      紅水晶 → 2.667
藍水晶 → 1.0       靈巧披風 → 40.0/1%   發光結晶 → 50.0
短劍 → 25.0/1%     鞋子 → 12.0          治療寶珠 → 3.0/1%   ← 正規化陷阱，見 §5.3

# CP值（權威法，全域視角 = 權重全 1.0）
三相之力     3333g → 109.5%   殘差 −315g   （4 種屬性全可定價，屬性本身超值）
無盡之刃     3500g → 103.6%   殘差 −125g   （暴擊傷害未定價，此為下限）
中婭沙漏     3250g →  95.4%   殘差 +150g   （金身被動）
殞落王者之劍 3200g →  80.0%   殘差 +639g   （吸血已扣除法計價，殘差為被動價值）

# CP值（權威法，達瑞文視角 = 純 Marksman 預設、零覆寫）
無盡之刃     3500g → 103.6%   殘差  −125g   未定價 1  遮罩 0   ← 與全域相同
殞落王者之劍 3200g →  80.0%   殘差  +639g   未定價 0  遮罩 0   ← 與全域相同
三相之力     3333g →  82.2%   殘差  +593g   未定價 0  遮罩 0
中婭沙漏     3250g →   9.2%   殘差 +2950g   未定價 0  遮罩 1（法術強度）

# 資料集不變量
SR 可購買裝備（標準 ID）= 212      被過濾的變體 ID = 36
其中有結構化屬性        = 199      → NNLS 矩陣 199 × 25（盲點修復後）
NNLS condition number   = 1509.2   （實測，良態；過高才需警告整欄不可信）
NNLS 低信賴屬性（<5 件）= 7 種：暴擊傷害 1、固定生命回復 2、緩速抗性 3、
                                百分比物穿 4、固定魔穿 4、百分比魔穿 4、
                                固定魔力回復 1
SR 屬性種類 = 25（14 可定價 / 11 未定價；吸血/物穿%/穿甲為扣除錨）
真英雄 = 173              Jade_ 變體 = 60
partype != "Mana" = 33    bin↔DD 衝突 = 0

# 錨定裝備 ID（必須以 ID 查找，不可以名稱查找 — 見 §3.5）
長劍 1036   增幅典籍 1052   紅水晶 1028   藍水晶 1027   布甲 1029
抗魔斗篷 1033   靈巧披風 1018   短劍 1042   發光結晶 2022
鞋子 1001   治療寶珠 1006   吸血鬼權杖 1053（扣除錨）   最後耳語 3035（扣除錨）
殘暴之力 3134（扣除錨）
```

達瑞文視角的四筆驗證了 RoleDefaults 套用、遮罩與未定價分離、以及「英雄視角不會一律壓低數字」這個性質（前兩筆與全域相同）。

凱爾是三隻中唯一多 tag 的英雄，因此是 `union_max` 的唯一測試點：

```
# 凱爾聯集結果（Mage ∪ Marksman，取 max）
AD 1.0   AP 1.0   暴擊 1.0   攻速 1.0   生命 0.6   護甲 0.5

# CP值（權威法，凱爾視角）
無盡之刃     3500g → 103.6%   殘差  −125g   未定價 1  遮罩 0
三相之力     3333g →  98.8%   殘差   +40g   未定價 0  遮罩 0
中婭沙漏     3250g →  80.0%   殘差  +650g   未定價 0  遮罩 0
殞落王者之劍 3200g →  80.0%   殘差  +639g   未定價 0  遮罩 0
```

**中婭沙漏在達瑞文視角是 9.2%、在凱爾視角是 80.0%**——同一件裝備差距 8.7 倍，且凱爾視角遮罩數為 0。這一組對比是 `union_max` 正確捕捉混合傷害的最強斷言：若聯集誤用平均或誤取單一 tag，AP 權重會掉到 0.5 或 0，這個數字立刻不同。

這是唯一能發現「改版後計算悄悄變了」的機制。

### 10.3 infrastructure 測試

用同一份裁剪 fixture 測 mapping／join／`Jade_` 過濾／`.complete` 原子性（含模擬中斷的下載）。**不打網路。**

### 10.4 契約測試

標記 `@pytest.mark.network`，實際請求 CDN 驗證 schema 未變（欄位仍在、URL 仍活、三種命名慣例的代表欄位仍在）。預設跳過，需確認改版影響時手動執行。

**這是唯一能提早發現 Riot 改格式的機制**，而 bin 檔 schema 是整個專案最脆弱的一層。

### 10.5 presentation 測試

`ItemTableModel` 為 `QAbstractTableModel`，不開視窗即可測 `rowCount`／`data`／排序／視角切換後重算。視窗本身手動驗證，不寫自動化測試。

---

## 11. 決策紀錄摘要

| # | 決策 | 理由 |
|---|---|---|
| 1 | CP值 = 從基礎裝備反推單價 | 改版後單價自動跟上，不需手動維護常數表 |
| 2 | 兩種定價法並列顯示 | 差異大者 = 被動價值高或屬性被低估，本身即分析入口 |
| 3 | 屬性來源 = CommunityDragon bin | Data Dragon 缺 41% 裝備的屬性；Meraki 已死；CDragon client 無屬性 |
| 4 | 法力 bin 優先、DD 補缺 | 兩來源各 15 件、零分歧（2026-08-15 更正） |
| 5 | 英雄層 = Level 1，float 權重 | 與 Level 2 同型，日後加 UI 不動 domain |
| 6 | 權重三層解析 | 新增英雄零成本；覆寫僅寫差異 |
| 7 | 介面 = 表格 + 詳情面板 | 屬性拆解是「為何 CP值 低」的唯一答案所在 |
| 8 | 啟動自動檢查版本 | 永遠最新；無網路時降級讀舊快取 |
| 9 | numpy 允許進 domain | 純函式數學庫，非 I/O／框架／UI |
| 10 | 邏輯讀 en_US、顯示讀 zh_TW | `partype` 是在地化字串，比對中文會隨語言爆掉 |
