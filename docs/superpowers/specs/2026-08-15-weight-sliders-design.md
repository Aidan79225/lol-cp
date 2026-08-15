# 英雄權重拉桿設計

日期：2026-08-15
狀態：已與使用者確認設計，待實作
前置：主 spec §7（三層權重解析）、§8（元件）

## 1. 問題

選英雄只會看到 CP值 變化，21 種屬性權重本身在 UI 看不到也改不了——
它們藏在 `role_defaults.toml` 與 `config/champions/*.toml`。domain 當初
已為此鋪路（遮罩與可調權重同為 float，`weights.py` docstring 明言
「日後加滑桿 UI 是純 presentation 工作」）。

## 2. 決策記錄

| 決策 | 選擇 | 理由 |
|---|---|---|
| 持久化 | 拉桿寫回 `config/champions/*.toml` | 拉桿就是在編輯現有「手動覆寫」層，不加新層；可手動編輯、可進版控 |
| 註解保留 | 行級編輯 | 檔內手寫判斷理由是刻意經營的資產；已存在的行只換數值、整行註解不動 |
| 全域視角 | 拉桿停用 | 全域的定義就是客觀基準（權重全 1.0） |
| 重算時機 | 拉桿放開（sliderReleased）才觸發 | 每次 execute 會重跑 NNLS，拖曳中不重算 |
| 還原語意 | 拉回基準值 = 移除該覆寫（刪行） | 檔案保持最小；「有覆寫」恆等於「與基準不同」 |

## 3. UI

右側面板改為 QTabWidget 兩分頁：「詳情」（現有 `DetailPanel`）＋
「權重」（新 `WeightPanel`）。權重頁：

- 每種 StatKey 一列：屬性名（config_key）、水平拉桿（0.00–1.00，
  步進 0.05）、數值標籤（兩位小數）、單屬性「還原」鈕
- 有覆寫（≠ 基準值）的列以粗體標示
- 頂部「全部還原」鈕：對每個有覆寫的屬性發出還原
- 英雄為 None（全域）時清空列表、顯示「全域視角為客觀基準，不可調整」

拉桿基準值 = 前兩層解析結果（角色預設 → 資源規則），即零覆寫時的值。

## 4. 架構

### domain（`weights.py`）

- `WeightResolver.resolve_defaults(champion) -> StatWeights` —— 只跑前兩層；
  `resolve` 重構為 `resolve_defaults` + 覆寫套用，行為不變
- `WeightResolver.replace_overrides(overrides: ChampionOverrides) -> None` ——
  換掉覆寫層（Diagnostics 已有「刻意可變」先例）
- `WeightResolver.overrides` property —— 目前覆寫層（唯讀取用）

### application

- port `OverridesStore`（`ports.py`）：
  `load() -> ChampionOverrides`；
  `set_weight(champion_key: str, stat: StatKey, value: float | None) -> None`
  （None = 移除該屬性覆寫）
- use case `AdjustChampionWeight(store, resolver)`：
  `execute(champion: Champion, stat: StatKey, value: float) -> ChampionOverrides`
  1. `default = resolver.resolve_defaults(champion).of(stat)`
  2. 與基準值差 < 1e-9 → `set_weight(..., None)`，否則寫入 value
  3. 重新 `load()`、`resolver.replace_overrides(...)`、回傳新覆寫

### infrastructure

- `TomlOverridesStore(directory: Path)` 實作 `OverridesStore`：
  - `load` 委派現有 `load_champion_overrides`
  - `set_weight` 行級編輯 `<champion_key>.toml`：
    - 已存在的 `key = value` 行：只替換數值，行尾註解保留
    - 整行註解與空行不動
    - 新屬性追加檔尾；移除（None）= 刪該屬性的行
    - 檔案不存在且寫入值 → 建新檔附生成標頭註解；不存在且 None → no-op

### presentation

- `WeightPanel(QWidget)`：`set_context(champion, defaults: StatWeights,
  overrides: Mapping[StatKey, float])`；signal
  `weight_committed = Signal(object, float)`（StatKey, 新值）
- `MainWindow`：右側改 QTabWidget；`_on_weight_committed` 呼叫 use case →
  `reload()` → 刷新權重頁；切視角時同步刷新權重頁
- `build_use_cases` 回傳 `(list_valuations, champions, adjust_weights)`；
  `MainWindow.__init__` 與 `set_use_cases` 增收 `adjust_weights`；
  `AppCoordinator` 對應解包

## 5. 測試

- domain：`resolve_defaults` 不含覆寫；`replace_overrides` 後 `resolve` 反映新值；重構後既有測試全綠
- application：寫入 ≠ 基準 → 覆寫存在；調回基準 → 覆寫被移除；resolver 被更新
- infrastructure（重點）：以 Kayle.toml 實檔複本驗證「換值後全部註解逐行不變」；刪行；追加；建新檔含標頭；None + 無檔 no-op
- presentation：WeightPanel 反映基準與覆寫（粗體）、全域停用、sliderReleased 發訊號、還原鈕發基準值（offscreen）
- 組裝：`build_use_cases` 三元組、coordinator 測試同步更新

## 6. 非目標（YAGNI）

權重 > 1.0、全域自訂 profile、覆寫 reason 欄位、拖曳中即時重算、
role_defaults 層的 UI 編輯。
