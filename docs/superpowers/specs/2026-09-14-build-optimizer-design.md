# 出裝規劃器（Build Optimizer V1）設計

日期：2026-09-14
狀態：已核准，待實作
前置：`2026-08-17-marginal-model-design.md`（沿用其 CombatModel，不改公式）

## 1. 問題與取徑

邊際效益欄回答「在我已有的出裝上，下一件每千金多多少」，但出裝仍要
使用者手動一件件試。本設計讓工具**自動排出 6 件成品＋購買順序**，
並把每一步的戰力變化攤開 —— 與 op.gg「大家怎麼出」的差別在於：
這裡的每個推薦都能回溯到可手算的公式。

V1 刻意**只用現有模型**（屬性物理三公式），不補被動、不補技能。
目的是先看到推薦結果，由結果決定下一步該補模型的哪一塊。

## 2. 決策記錄

| 決策 | 選擇 |
|---|---|
| 評分 | 輸出為主，生存以 β 次方納入（§3.1）；**不採門檻**（§9 原型實測） |
| 輸出內容 | 6 件成品＋購買順序＋每步戰力 |
| 候選池 | 傳說裝＋二階鞋，由 bin 的 `epicness` 與群組判定，零手工清單 |
| 組合限制 | bin `ItemGroup.mMaxGroupOwnable`（最後耳語系、Lifeline 系等），零手工 |
| 鞋 | 恰一雙，位置固定（預設第 2 件）—— 模型不算移速，放任搜尋會把鞋排到最後 |
| 已有出裝 | 出裝列內容視為**已購前綴**，規劃器只補後面的格子 |
| 執行 | 同步計算（原型實測約 0.2 秒），不開 worker thread |

## 3. 評分（domain，全部可手算）

### 3.1 單一時間點的戰力

持有前 k 件成品時，等級 `lv_k` 取設定檔 `levels[k-1]`：

```
score_k = DPS(prefix_k, lv_k, 目標) × ( EHP(prefix_k, lv_k) / EHP(裸裝, lv_k) ) ^ β
```

- DPS 與 EHP 即 `CombatModel.total_dps` 與 `mixed_ehp`，不改公式
- 除以同等級裸裝 EHP 使比值無因次，β 才能跨英雄、跨等級共用
- 物理意義：`DPS × EHP` ≈「死前打出的總傷害」；β 決定生存的重要度。
  β=0 為純輸出，β=1 為完整的「死前總傷害」

### 3.2 整條購買序列的價值

```
V(序列) = Σ_{k=1..5} score_k × gold(item_{k+1})  +  score_6 × final_holding_gold
```

**持有權重 ∝ 下一件的價格**：金幣收入近似等速，所以攢下一件所需的
金幣就是持有目前前綴的時間。先買便宜又強的件，其戰力會被加權更久 ——
這正是「購買順序」有意義的原因。六神裝以固定常數 `final_holding_gold`
代表後期持有時間。

## 4. 候選池與限制

### 4.1 候選池（16.15.1 與 16.16.1 實測一致）

| 類別 | 判準 | 件數 |
|---|---|---|
| 傳說裝 | `epicness == 5` ∧ 無 `into` ∧ `total ≥ 2000` | 105 |
| 二階鞋 | `epicness == 4` ∧ 屬於 `Boots` 群組 | 7 |

- `≥ 2000` 排除 400g 的輔助／打野任務裝與 1500g 靈魂竊取者
- 無 `into` 排除低語之環（會升級成歌謠之冠的輔助任務裝）
- 三階鞋（`epicness 7`，不朽之道等）是升級而非獨立購買，V1 不納入

### 4.2 組合限制

- 6 格、不重複
- bin 群組：只套用有 `mMaxGroupOwnable` 的群組（沒有上限的群組是其他用途，
  例如 `{3bbe1bdd}`）。實測成品裝中有上限的群組：LastWhisper（5 件）、
  LifelineItems（5）、Spellblade `{8b55a7b3}`（5）、VoidPen（4）、
  LegendaryClearingItems（4）、TearItems（3）、ImmolateItems（2）、女妖面紗系（2）
- 鞋：序列恰含一雙，且位於 `boots_slot`（設定檔，預設 2；0 表示不出鞋）。
  已購前綴若已含鞋，視為滿足，不再檢查位置

### 4.3 已購前綴

- 出裝列中屬於候選池的件，依原順序成為固定前綴
- 不屬於候選池的件（部件，如靈巧披風）**不參與規劃**，結果中列出被略過的件
  —— 絕不靜默丟棄
- 前綴已滿 6 件 → 回傳前綴本身的評分，不搜尋

## 5. 搜尋

兩階段，兩者都是確定性的（同輸入同輸出）：

1. **選組合：beam search**。狀態為序列，每層對所有合法候選展開；
   排序鍵為部分序列的價值，最後一個前綴的持有權重暫用
   `final_holding_gold` 作樂觀估計。同一集合只保留最佳序列（以 frozenset 去重），
   保留前 `beam_width`（預設 40）個
2. **排順序：窮舉**。取第 1 階段價值最高的集合，對非前綴的件窮舉所有
   符合鞋位的排列，取 V 最大者。最壞 5! = 120 種，成本可忽略

第 1 階段是啟發式，不保證全域最佳 —— 誠實邊界，寫在 docstring。
原型實測 105+7 件、beam 40，單次約 0.2 秒（評估一次約 5 µs）。

## 6. 領域模型與資料

### 6.1 `Item` 擴充（`entities.py`，全部有預設值以保持既有建構相容）

```python
@dataclass(frozen=True)
class GroupLimit:
    group_id: str        # bin mItemGroupID，例如 "LastWhisper"、"Boots"
    max_owned: int

# Item 新增
epicness: int | None = None
upgrades: tuple[int, ...] = ()           # Data Dragon `into`
group_limits: tuple[GroupLimit, ...] = ()
```

`is_legendary(item)`、`is_boots(item)` 寫在 domain（§4.1 判準的唯一出處）。

### 6.2 `build_planner.py`（domain）

- `PlannerSettings(levels: tuple[int, ...6], final_holding_gold, beta, boots_slot, beam_width)`
- `PlanStep(item, level, dps, ehp, score)`；`BuildPlan(steps, value, skipped: tuple[Item, ...])`
- `BuildPlanner(model)`.`plan(base, target, pool, prefix, settings) -> BuildPlan`

### 6.3 mapping（infrastructure）

- 讀 bin `epicness`、Data Dragon `into`
- `mItemGroups` 的每個參照到 bin 最外層查 `ItemGroup` 物件，取
  `mItemGroupID` 與 `mMaxGroupOwnable`；**查不到的參照記入 Diagnostics**
- `Items/ItemGroups/Default` 無上限，自然被略過

### 6.4 fixture

`scripts/build_fixtures.py` 目前只保留 `Items/<id>` 條目，fixture 內群組物件為 0。
改為**額外保留被保留裝備參照到的 ItemGroup 物件**，重新產生 16.15.1 fixture
（已確認 `raw.communitydragon.org/16.15/` 仍回 200）。只新增條目，
既有黃金值必須全數不變 —— 這本身就是驗證。

## 7. 設定、application、UI

### 7.1 `config/build_planner.toml`

```toml
# 出裝規劃器常數。主觀擇定、可爭論。改這裡不改碼。
levels = [9, 11, 13, 15, 16, 18]  # 持有第 1..6 件成品時的等級
final_holding_gold = 3000         # 六神裝的持有權重（等價金幣）
beta = 0.25                        # 生存重要度預設值（UI 可調）
boots_slot = 2                     # 鞋在第幾件買；0 = 不出鞋
beam_width = 40
```

`load_planner_config(path) -> PlannerSettings`：未知鍵、缺鍵、型別錯、
`levels` 長度不為 6、`boots_slot` 不在 0..6 皆擲 `ConfigError`。

### 7.2 application

`PlanBuild(items, planner, targets, settings)`.`execute(champion, target_key, beta, prefix_ids) -> BuildPlan | None`
—— champion 為 None 或無 base_stats → None。`UseCaseBundle` 新增 `plan_build`。

### 7.3 UI：右側新分頁「出裝規劃」

- 目標下拉（脆皮／坦克）、β 數值框（0–1，步進 0.05，預設取設定檔）、「規劃」鈕
- 結果表：順序、裝備、等級、DPS、EHP、該步 score
- 「套用到出裝列」鈕：把結果寫入 BuildBar（邊際欄隨之重算）
- 常駐一行誠實邊界：「未計入：裝備被動、移速、吸血；英雄差異僅來自基礎數值」
- 全域視角時整個分頁停用

## 8. 測試

**domain（玩具裝備，可手算）**：
- 兩件序列的 V 手算值（§3.2）；β=0 時 score 等於 DPS
- 群組上限：同群組兩件不會同時出現；無上限群組不限制
- 鞋恰一雙且在 `boots_slot`；`boots_slot=0` 時無鞋
- 前綴保留原順序；部件進入 `skipped`；前綴滿 6 件不搜尋
- 窮舉排序：回傳順序的 V ≥ 同集合任一合法排列（小池子暴力驗證）
- 確定性：同輸入兩次結果相同

**性質（fixture 真資料，達瑞文）**：
- 6 件不重複、恰一雙鞋、無群組超限
- β=1 的最終 EHP ≥ β=0 的最終 EHP

**黃金快照**：達瑞文 vs 脆皮、β=0.25 的完整序列，實作時以 fixture 實測後寫入
本節 —— 改版後推薦悄悄改變時，這是唯一的警報。

## 9. 原型實測（16.16.1，決定 §2 的依據）

達瑞文 vs 脆皮：

| 評分 | 推薦 |
|---|---|
| 門檻：EHP 低於裸裝 1.2 倍時輸出按比例打折 | 無盡 → **步履破壞者** → … |
| 門檻 1.3 倍 | **步履破壞者** → 無盡 → … |
| β = 0 / 0.25 | 無盡 → 狂戰士護脛 → 多明尼克 → 狂暴利刃 → 雲陶狂箭 → 蒐集者 |
| β = 0.5 | …蒐集者 → **三相之力** |
| β = 1.0 | **實驗型海克斯板甲** → 狂戰士護脛 → 無盡 → … |

- 門檻的折扣彈性等於 1，低於門檻時一點 EHP 與一點 DPS 等價，形成斷崖
- β 為平滑旋鈕，0 → 0.25 推薦不變，逐步才引入半肉裝
- 不固定鞋位時鞋一律排第 6 件（移速不在模型內）
- 達瑞文、煞蜜拉、凱爾的推薦**完全相同** —— 證實現有模型沒有英雄特色，
  凱爾出無盡之刃是錯的。這是 V1 預期的限制，也是下一步的方向（§10）

## 10. 非目標與後續

V1 不做：裝備被動、英雄技能、三階鞋、部件購買路徑與回家時機、
針對實際敵方英雄、多組推薦並列。

後續順序（研究結論，2026-09-14）：
1. 裝備被動 —— 與三隻英雄相關的約 15–20 件；數值讀 bin `mDataValues`
   （63/105 件有結構化資料），觸發邏輯逐件手寫
2. 英雄技能 —— CommunityDragon 每英雄 bin（約 70KB）含每級數值、冷卻與
   公式樹（三隻英雄僅用到約 9 種 CalculationPart），施放頻率寫入英雄設定檔
3. 對手模型 —— 以敵方英雄的實際雙抗與血量取代標準目標
