# 英雄技能（Champion Kits V1）設計

日期：2026-09-15
狀態：研究完成，待核准
前置：`2026-09-15-item-passives-design.md`（傷害拆分、公式計算器、整場平均）、
`2026-09-14-build-optimizer-design.md` §10 後續第 2 項

## 1. 問題與取徑

裝備被動上線後，三隻英雄的推薦仍幾乎相同：模型裡的「技能」只有一個泛用
基準技能（300 傷、0.7 AP、8 秒冷卻），英雄差異只剩基礎數值。本設計為
達瑞文、凱爾、煞蜜拉建立技能模型，讓推薦反映各自的機制。

原則沿用裝備被動：

1. **數字讀資料，機制手寫。** CommunityDragon 每英雄 bin（約 70KB）有每級數值、
   冷卻與公式樹；「接斧頭」「評分 S 才能放大絕」這類規則只在描述文字裡，逐隻寫在 domain
2. **對不上就大聲失敗。** 綁定名稱缺漏或公式不支援 → Diagnostics、該英雄退回泛用基準技能
3. **操作假設明寫。** 技能傷害與操作高度相關，這一步繞不過去 —— 每個假設都是
   `config/kits/<英雄>.toml` 裡一個具名旋鈕，預設「熟練玩家」

## 2. 決策記錄

| 決策 | 選擇 |
|---|---|
| 戰鬥模型 | **固定戰鬥時長**（預設 10 秒）：開場技能皆可用、依冷卻重放、大絕至少一次；DPS = 窗口總傷 ÷ 時長 |
| 裝備被動 | 仍用整場平均（穩態）；兩者疊加 |
| 操作假設預設 | 熟練玩家（達瑞文雙斧全接、技能冷卻好就放） |
| 範圍 | 三隻完整；煞蜜拉以「連段秒數」「近戰普攻比例」取代逐步連招模擬 |
| 無技能模型的英雄 | 維持泛用基準技能（既有行為與測試不變） |
| 設定位置 | `config/kits/<Key>.toml`（`config/champions/` 是權重覆寫，且含使用者私人檔） |

## 3. 戰鬥窗口（`combat_model.toml` `[fight]` 新欄位）

```toml
fight_duration_seconds = 10.0   # 固定戰鬥時長：一波交戰的長度（主觀擇定）
```

- **施放次數** = `1 + floor(時長 ÷ 實際冷卻)`；實際冷卻 = 冷卻 ÷ (1 + 技能加速/100)。
  大絕冷卻 80–160 秒 → 窗口內 1 次
- **窗口內 DPS** = 普攻 DPS（穩態，含技能對普攻的修飾）+ Σ 技能總傷 ÷ 時長
- **增益持續率** = `min(1, 施放次數 × 持續秒數 ÷ 時長)`（煞蜜拉 E 攻速、凱爾 Q 削抗）；
  以持續率線性加權 —— 近似，寫 docstring
- **魔法彎刀觸發率**改用真實施放：`min(Σ 一般技能施放次數, 時長 ÷ 彎刀冷卻) ÷ 時長`，
  取代原本「基準技能冷卻」的假設（僅限有技能模型的英雄）

## 4. 技能等級

`config/kits/<Key>.toml` 的 `skill_order`（主升順序，例 `["Q", "W", "E"]`）推算
每個英雄等級下的技能等級，套用遊戲規則：

- 1–3 級依主升順序各點一個技能（先學三招）
- 大絕在 6／11／16 級升級
- 一般技能等級 ≤ `(英雄等級 + 1) // 2`，上限 5
- 其餘點數依主升順序、在規則允許下優先投入

**數值陣列索引即技能等級**（實測對照：達瑞文 Q `BaseDamage` [35, 40, …] 1 級 = 40、
凱爾 E `PassiveDamage` [15, 15, 20, …] 1 級 = 15；索引 0 為佔位）。
等級 0（尚未學）的技能不施放、不修飾普攻。

## 5. 公式計算器擴充（`formulas.py`）

三隻英雄的技能公式實測需要：

| 新增 | 語意 | 佐證 |
|---|---|---|
| `ByCharLevelInterpolation(start, end)` | 1 級 start 到 18 級 end 線性內插 | 煞蜜拉被動近戰傷 AD 係數 3.5% → 10.5% |
| `StatBySubPart(stat, part, sub)` | 屬性 × 子公式 | 煞蜜拉被動：AD × 內插係數 |
| `LevelBreakpoints.initial_per_level` | 1 級起每級加（`mInitialBonusPerLevel`） | 煞蜜拉被動 2 + 1/級 → 18 級 19 |
| `FormulaStat.CRIT_DAMAGE = 9` | 總暴擊傷害倍率（基礎 1.75 + 裝備暴傷） | 煞蜜拉 R `CriticalDamageCalc` = 傷害 × 代碼 9；Q = 傷害 × (1 + 0.5 × (代碼 9 − 1)) |

技能的 data value 是陣列 —— 綁定時依技能等級取值後填入 `FormulaContext.data_values`，
計算器本身不變。

## 6. 三隻英雄（數值為 CommunityDragon 實測；16.15 fixture 須重新確認）

### 6.1 達瑞文

| 技能 | 模型 | 綁定 |
|---|---|---|
| Q 旋轉飛斧 | 強化普攻比例 `q_empowered_attack_ratio` × 每下 `TotalDamage`（40–60 + 75–115% 額外 AD）物理、不吃暴擊 | `DravenSpinning` calc `TotalDamage` |
| W 狂熱血性 | 額外攻速 `Temp_AS`%（20–40）× 持續率 `w_uptime`（接斧頭重置冷卻 → 熟練時常駐） | `DravenFury` dv `Temp_AS` |
| E 閃避開 | 每次施放 `TotalDamage`（75–215 + 50% 額外 AD）物理 | `DravenDoubleShot` calc `TotalDamage` |
| R 死亡旋轉 | 每次施放 `RCalculatedDamage` × 2（去回各中一次；單體不衰減）物理 | `DravenRCast` calc `RCalculatedDamage` |
| 被動 | 金錢，無戰鬥值 | — |

```toml
# config/kits/Draven.toml —— 熟練玩家預設
skill_order = ["Q", "W", "E"]
q_empowered_attack_ratio = 1.0   # 雙斧全接：每下普攻都帶 Q
w_uptime = 1.0                   # 接斧頭重置 W 冷卻 → 攻速常駐
```

### 6.2 凱爾

| 技能 | 模型 | 綁定 |
|---|---|---|
| 被動 神聖昇華 | 1 級起攻速疊層 `EnrageASPerStack` × `EnrageMaxStacks`（30%，視為疊滿）；6 級起遠程（影響裝備遠近程數值）；11 級起每下普攻附劍氣 `PassiveWaveDamage`（魔法） | `KaylePassive` dv `LevelForPassiveRank1..3`、`EnrageASPerStack`、`EnrageMaxStacks`；calc `PassiveWaveDamage` |
| E 星焰聖劍 | 被動：每下普攻 `EPassiveTotalDamage`（魔法命中特效）；主動：每次施放 `ActiveTotalExecuteDamage` × 目標已損生命（整場平均 50%）魔法 | `KayleE` calc 兩者 |
| Q 天光爆擊 | 每次施放 `TotalDamage` 魔法；削雙抗 `ShredPercent`% × 持續率（`ShredDuration` 4 秒） | `KayleQ` calc `TotalDamage`；dv `ShredPercent`、`ShredDuration` |
| W 天界祝福 | 補血加速，無輸出 | — |
| R 神聖審判 | 每次施放 `TotalDamage` 魔法 | `KayleR` calc `TotalDamage` |

劍氣在 11–15 級需疊滿才觸發、16 級常駐 —— 疊層視為滿，11 級起一律計入。

```toml
# config/kits/Kayle.toml —— 熟練玩家預設
skill_order = ["E", "Q", "W"]
```

### 6.3 煞蜜拉

| 技能 | 模型 | 綁定 |
|---|---|---|
| 被動 狂熱衝勁 | 近戰距離普攻比例 `melee_attack_ratio` × 每下 `BonusMeleeDamage`（2–19 + 3.5–10.5% AD）魔法 | `SamiraPassive` calc `BonusMeleeDamage` |
| Q 華麗射擊 | 每次施放 `DamageCalc`（110% AD）× 暴擊期望 `1 + 暴擊率 × 0.5 × (暴傷倍率 − 1)` 物理（劍與槍傷害相同） | `SamiraQ` calc `DamageCalc`；dv `CritDamageMod` |
| W 刃舞 | 每次施放 `DamageCalc` × 2（兩段）物理 | `SamiraW` calc `DamageCalc` |
| E 狂野衝刺 | 每次施放 `DashDamage` 魔法；額外攻速 `BonusAttackSpeed` × 持續率（`AttackSpeedDuration` 5 秒） | `SamiraE` calc `DashDamage`；dv `BonusAttackSpeed`、`AttackSpeedDuration` |
| R 狂亂扳機 | 評分 S 才能放：窗口 ≥ `combo_seconds` 時施放 1 次；10 發 × `DamageCalc` × 暴擊期望 `1 + 暴擊率 × (暴傷倍率 − 1)` 物理 | `SamiraR` calc `DamageCalc`；描述「10 times」為常數並註明出處 |

- 評分 S = 連續 6 次「與上一次不同」的普攻或技能命中；以 `combo_seconds` 取代逐步模擬
- 放完 R 評分清空：窗口 10 秒內重新打到 S 需要再一輪連段 → 施放次數 = `1 + floor((時長 − combo_seconds) ÷ (combo_seconds + 2))`，
  其中 2 為 R 施放時間（描述「over 2 seconds」）
- 「對被硬控目標普攻會衝刺」「擊殺重置 E」—— 需要隊友控場與擊殺序列，不計

```toml
# config/kits/Samira.toml —— 熟練玩家預設
skill_order = ["Q", "E", "W"]
melee_attack_ratio = 0.6   # 近戰距離普攻占比（主觀）
combo_seconds = 3.0        # 開場打到 S 級評分所需秒數（主觀）
```

## 7. 資料管線

- **下載**：`SyncGameData` 額外下載有技能模型的英雄 bin：
  `raw.communitydragon.org/<major.minor>/game/data/characters/<key>/<key>.bin.json`
  （16.15、16.16 實測皆 200；**不用 /latest/**）→ 快取 `champion_bins/<key>.bin.json`
- **舊快取**：已標記 `.complete` 但缺英雄 bin 的版本目錄（例：現有 16.16.1）→ 下次同步時補下載
  缺的檔案（逐檔原子寫入），不重抓整包
- **mapping**：`ChampionSpellMapper` 解析 `mSpell.DataValues`（陣列）、`cooldownTime`、
  `mSpellCalculations`（沿用 `FormulaMapper`）→ domain `SpellData`
- **fixture**：`build_fixtures.py` 加入三隻英雄 16.15 bin，只保留 `mSpell` 條目

## 8. 領域模型

- `SpellData(name, cooldowns: tuple[float, ...], data_values: tuple[(name, tuple[float, ...]), ...], calculations)`
- `ChampionSpells(key, spells: Mapping[str, SpellData])`
- `domain/champion_kits.py`：`ChampionKit`（宣告需要的法術與名稱、`apply(ctx)`）、
  註冊表 `KITS: dict[str, ChampionKit]`（以英雄 key 索引）、`ChampionKitBinder`
- `KitSettings`：`skill_order` 與各英雄的操作假設（由 `load_kit_config` 讀取、未知鍵大聲失敗）
- **CombatModel 綁定英雄**：`model.for_champion(kit_or_none) -> CombatModel` 回傳帶技能的視圖；
  `ComputeMarginals`、`PlanBuild` 以英雄查 kit 後取得視圖。無 kit → 泛用基準技能
- 技能對普攻的修飾（達瑞文 Q、凱爾 E 被動與劍氣、煞蜜拉被動）寫入既有 `AttackModifiers`；
  技能總傷另存 `spell_window_damage`（物理／魔法分開）；凱爾 Q 削抗新增 `magic_shred`
- 遠近程：`EffectContext.is_ranged` 改由 kit 決定（凱爾 6 級起遠程），無 kit 時沿用攻擊距離

## 9. UI

- 規劃分頁誠實邊界：有技能模型的英雄顯示「技能：已建模（熟練玩家假設，見 config/kits/達瑞文）」；
  其他英雄顯示「技能：泛用基準」
- 狀態列：`unbound_champion_kits` 計數（綁定失敗的英雄退回泛用基準）

## 10. 測試

**公式擴充**：內插 1／18 級端點與中點；`initial_per_level` 18 級 = 19；
代碼 9 讀總暴擊傷害倍率。

**技能等級**：達瑞文 Q>W>E —— 1 級 Q1、3 級 Q1W1E1、9 級 Q5、6 級 R1、18 級全滿；
一般技能等級永不超過 `(等級 + 1) // 2`。

**各英雄（玩具基礎值＋真 bin，手算）**：
- 達瑞文：`q_empowered_attack_ratio` 0 與 1 的普攻 DPS 差 = 攻速 × Q 傷；W 持續率 1 時攻速 +Temp_AS%；
  R 在 10 秒窗口施放 1 次、傷害 × 2
- 凱爾：5 級近戰、6 級遠程（破敗數值切換）；10 級無劍氣、11 級有；E 主動吃已損生命
- 煞蜜拉：R 暴擊期望在暴擊率 0／100% 的兩端值；`combo_seconds` > 時長時 R 不施放；
  Q 暴擊只吃一半暴傷
- 施放次數與持續率：冷卻 8 秒、時長 10 秒 → 2 次

**不變量**：無 kit 的英雄（泛用基準）所有既有測試數值不變。

**綁定失敗**：拿掉 fixture 某個 calc → 該英雄退回泛用基準並記錄。

**預期變更**：三隻英雄的規劃黃金快照會改變 —— 實測後更新並記錄，
**且三隻的推薦應彼此不同**（這一步的核心驗收）。

## 11. 效能

每次 profile 多出技能求值。規劃器現況 0.8 秒／次，預算 1 秒 —— 技能公式中不依賴屬性的部分
（依等級、技能等級）預先快取；若仍超標，改為每個等級只算一次技能等級與常數表。

## 12. 非目標

隊友控場觸發（煞蜜拉衝刺、擊殺重置 E）、達瑞文被動金錢與斬殺、凱爾 W 補血與 R 無敵、
技能命中率（一律命中）、多目標、逐步連招時間軸、其他 170 隻英雄。
