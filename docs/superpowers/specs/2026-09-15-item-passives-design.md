# 裝備被動（Item Passives V1）設計

日期：2026-09-15
狀態：已實作（2026-09-15）
前置：`2026-08-17-marginal-model-design.md`（CombatModel）、
`2026-09-14-build-optimizer-design.md`（§10 後續第 1 項）

## 1. 問題與取徑

CombatModel 只算屬性，破敗、海妖、鬼索這類「價值在被動」的裝備被系統性低估，
規劃器因此偏向純屬性裝。本設計為約 20 件與普攻單體輸出相關的傳說裝補上被動。

三條原則：

1. **數字讀資料，觸發邏輯手寫。** 公式樹與 `mDataValues` 只有數字；
   「每三下一次」「充能普攻」「疊滿幾層」在資料裡不存在，只能逐件寫在 domain
2. **對不上就大聲失敗。** 綁定的數值名稱或公式在改版後消失、或公式含不支援的
   組件 → 記入 Diagnostics、該件效果停用。絕不當 0 默默算
3. **公式計算器通用化。** 裝備公式用到的組件與英雄技能 bin 大量重疊，
   這一步做好，英雄技能（下一步）直接沿用

已知限制（先講清楚）：只補被動，三隻英雄的推薦差異仍有限 —— 凱爾出納什之牙的
理由在她的技能。本步驟是英雄技能的前置：傷害拆分與公式計算器都是技能模型需要的。

## 2. 決策記錄

| 決策 | 選擇 |
|---|---|
| 戰鬥模型 | **整場平均**：仍是可手算的閉式公式；假設寫入設定檔（§3.3） |
| 範圍 | 約 20 件：屬性轉換、命中特效、充能普攻、削弱目標、魔法彎刀（§5） |
| 數字來源 | 通用公式計算器：mapping 把 bin 公式樹轉成 domain 型別，按等級與屬性求值 |
| 效果索引 | 以裝備 ID 綁定（主 spec §3.5：絕不以名稱查找） |
| 綁定失敗 | Diagnostics 計數＋該件效果停用 |

## 3. 傷害模型 V2（`combat.py`）

### 3.1 拆分

一次普攻拆成三種傷害，各自吃對應抗性：

```
每下物理 = 總AD × 暴擊係數 + Σ 物理命中特效
每下魔法 = Σ 魔法命中特效
普攻DPS  = 攻速 × (每下物理 × 物理倍率 + 每下魔法 × 魔法倍率)
彎刀DPS  = 觸發率 × 彎刀傷害 × 對應倍率
總DPS    = (普攻DPS + 彎刀DPS + 基準技能DPS) × Π(1 + 增傷) × 斬殺係數
```

- 命中特效不吃暴擊（遊戲規則）
- 有效護甲 = `max(0, 護甲 × (1 − 削甲) × (1 − 物穿%) − 穿甲)`；
  削甲先於穿透（Riot 規則）。多個 % 穿透相乘疊加 `(1−a)(1−b)`
- 有效魔抗同型；臨界點的魔穿與物穿同步生效

### 3.2 近戰／遠程

`ChampionBaseStats.attack_range`（champion.json `attackrange`）；
`attack_range ≥ 300` 為遠程。實測：達瑞文 550、煞蜜拉 500、凱爾 175。
凱爾 6 級起靠被動變遠程 —— 技能不在 V1，她以近戰數值計算（已知限制）。

### 3.3 整場平均假設（`combat_model.toml` 新區塊）

```toml
[fight]
# 整場戰鬥中目標平均剩餘生命比例（從滿血打到 0 的線性平均）。
# 破敗、電流旋風劍吃當前生命；海妖吃已損失生命 = 1 − 此值。
average_current_hp_ratio = 0.5
# 充能普攻每幾下普攻觸發一次（移動＋普攻共同充能，主觀擇定）。
energized_attacks = 4
```

其餘假設不設旋鈕、寫在 docstring：疊層型被動視為已疊滿（鬼索 4 層、
黑切 5 層、雲陶狂箭 25% 暴擊、峽谷製造者 8%）、增益視為常駐（雲陶狂箭攻速）。
—— 整場平均的本質就是穩態，忽略疊層過程。

### 3.4 目標額外生命

多明尼克吃目標的額外生命。`TargetProfile` 新增 `bonus_hp`（設定檔必填）：
脆皮 300、坦克 2000。

## 4. 公式計算器（`domain/formulas.py`）

### 4.1 型別

```
Constant(value)
DataValue(name)                                   # mDataValues 查名
StatTerm(stat, part, coefficient: Formula)        # 屬性 × 係數
LevelBreakpoints(level1, breakpoints)             # 見 §4.3
Sum(parts) / Product(left, right)
Scaled(inner, multiplier: Formula)                # GameCalculation.mMultiplier、GameCalculationModified
RangedScaled(inner, ranged_multiplier: Formula)   # 型別名雜湊 {e9a3c91d}，以 mRangedMultiplier 鍵辨識
CalcRef(name)                                     # {f3cbe7b2}.mSpellCalculationKey、mModifiedGameCalculation
Unsupported(reason)
```

`evaluate(formula, ctx)`；ctx 含等級、是否遠程、該件的 data values 與 calculations、
屬性查表。遇到 `Unsupported` 擲 `UnsupportedFormulaError`（綁定時就會發現，
不會在計算中途才炸）。

### 4.2 屬性代碼（由資料反推，每一條都有實例佐證）

| mStat | 屬性 | 佐證 |
|---|---|---|
| 缺省（0） | 法術強度 | 巫妖之禍 `LichBaneAPValue` 0.45、納什之牙 0.15 —— 描述皆為 AP 係數 |
| 2 | 物理攻擊 | 達瑞文 Q `ADScaling`（描述為額外 AD） |
| 12 | 生命 | 史特拉克 `HealthPercent`、泰坦九頭蛇 |

`mStatFormula`：缺省＝總值、1＝基礎值、2＝額外值。
**其餘代碼（8、13、29、31、34…）V1 一律 `Unsupported`**，記入 Diagnostics。
例：奪魄之鐮用代碼 8（疑為暴擊率，但單位未驗證）→ V1 不納入（§5.6）。

### 4.3 等級分段

`ByCharLevelBreakpointsCalculationPart` 兩種寫法（實測）：

- `mBonusPerLevelAtAndAfter`：從該級起每級加。海妖 150、9 級起 +5 →
  8 級 150、9 級 155、18 級 200
- `mAdditionalBonusAtThisLevel`：到該級一次加。臨界點 6、11 級 +1、14 級 +1 →
  10 級 6、11 級 7、14 級 8

### 4.4 mapping

`Item` 新增 `data_values` 與 `calculations`（皆為 tuple of pairs，保持 Item 可雜湊）。
公式樹逐節點轉換；不認識的組件型別或屬性代碼轉為 `Unsupported` 並計數
（Diagnostics `unsupported_formula_parts`）。未被任何效果綁定的公式即使
Unsupported 也無害 —— 只有綁定時才會停用效果。

## 5. 效果清單（`domain/item_effects.py`，數值為 16.15.1 fixture 實測）

效果以裝備 ID 註冊，每個效果宣告它需要的 data value／calculation 名稱。
綁定器（`ItemEffectBinder`）在組裝時檢查一次：缺名或公式不支援 →
`Diagnostics.unbound_item_effect(item_id, 缺什麼)`、該件不註冊。

### 5.1 屬性轉換（套用在 profile 聚合之後）

| ID | 裝備 | 效果 | 綁定 |
|---|---|---|---|
| 3053 | 史特拉克手套 | 額外 AD += 基礎 AD × 0.45 | calc `BonusAD` |
| 2501 | 狂霸血甲 | AD += 額外生命 × 2.5%（「報應」吃自身已損血，不計） | dv `HPToADPercentage` |
| 4633 | 峽谷製造者 | AP += 額外生命 × 2%；增傷 8%（視為疊滿） | dv `HealthToAPConversionPercent`、`EternityDamageIncreaseMax` |
| 3032 | 雲陶狂箭 | 暴擊率 +25（上限 100）；攻速 +30%（視為常駐） | dv `CritMax`、`ASMod` |
| 3089 | 死亡之帽 | 總 AP × 1.3（在所有 AP 加總與轉換之後） | dv `APAmp` |

史特拉克在 16.16.1 為 0.5 —— 寫死常數的話改版後就默默錯了，這正是讀資料的理由。

### 5.2 命中特效（每下普攻）

| ID | 裝備 | 每下 | 型別 | 綁定 |
|---|---|---|---|---|
| 3153 | 殞落王者之劍 | 目標當前生命 × (遠程 6%／近戰 9%) | 物理 | dv `RangedValue`、`MeleeValue` |
| 6672 | 海妖殺手 | `DamageAmount(lv)` × (1 + 0.75 × 已損生命比) ÷ 3 | 物理 | calc `DamageAmount`；dv `MaxAmpNumber`、`AttackCount` |
| 3115 | 納什之牙 | 15 + 15% AP | 魔法 | calc `TotalOnHitDamage` |
| 3091 | 智慧末刃 | 45 | 魔法 | calc `OnHitDamage` |
| 3302 | 臨界點 | 30 + 10% 額外 AD + 10% AP；物穿魔穿 +30%；物防魔防 +`ARMRMaxScaling(lv)` | 魔法 | calc `OnHitDamage`、`ARMRMaxScaling`；dv `PenMax` |
| 3124 | 鬼索的狂暴之刃 | 30；攻速 +32%；滿層每 3 下多觸發一次**所有**命中特效 → 命中特效 × 4/3 | 魔法 | dv `OnHitDamage`、`AttackSpeedPerStack`、`MaxStacks` |

- 海妖增傷隨已損生命線性增加（上限 `MaxAmpNumber` 1.75）—— 線性為假設，寫 docstring
- 鬼索「每 3 下」出自描述文字，資料無此數值 —— 常數寫在效果內並註明出處

### 5.3 充能普攻（每 `energized_attacks` 下一次，攤平到每下）

| ID | 裝備 | 每次充能 | 型別 | 綁定 |
|---|---|---|---|---|
| 3097 | 狂暴利刃 | 100 | 魔法 | calc `TotalProcDamage` |
| 3094 | 衝擊火炮 | 40 | 魔法 | dv `BonusDamage` |
| 3087 | 史提克彈簧刀 | 60（只計主目標；「電擊」加速充能不計） | 魔法 | dv `ChainDamage` |
| 6699 | 電流旋風劍 | 目標當前生命 × (遠程 7%／近戰 9%)（穿甲增益不計） | 物理 | dv `PercentCurrentHPRanged`、`PercentCurrentHPMelee`（**百分點**，÷100） |

多件充能裝在同一下充能普攻上同時觸發，傷害相加。

### 5.4 削弱目標

| ID | 裝備 | 效果 | 綁定 |
|---|---|---|---|
| 3071 | 黑色切割者 | 目標護甲 × (1 − 6% × 5) | dv `ShredPerStack`、`MaxStacks` |
| 3036 | 多明尼克的問候 | 增傷 15% × min(1, 目標額外生命 ÷ 1500) | dv `MaxBonusDamagePercent`、`MaxBonusHealth` |
| 6676 | 蒐集者 | 斬殺係數 1 ÷ (1 − 5%) | dv `ExecuteThreshold` |

### 5.5 魔法彎刀（每次施放技能後的下一下普攻）

觸發率 = `1 / max(SpellbladeCooldown, 基準技能冷卻 ÷ (1 + 技能加速/100))`。
魔法彎刀群組上限 1（bin），同時最多一件。

| ID | 裝備 | 傷害 | 型別 | 綁定 |
|---|---|---|---|---|
| 3078 | 三相之力 | 基礎 AD × 2 | 物理 | calc `SpellbladeDamage`；dv `SpellbladeCooldown` |
| 6662 | 寒冰霸拳 | 基礎 AD × 1.5 | 物理 | 同上 |
| 3100 | 巫妖之禍 | 75% 基礎 AD + 45% AP | 魔法 | 同上 |
| 2510 | 暮夜與黎明 | 75% 基礎 AD + 10% AP | 魔法 | 同上 |

### 5.6 V1 不納入（附理由）

| 類別 | 裝備 | 理由 |
|---|---|---|
| 單位未驗證 | 奪魄之鐮 | 公式用屬性代碼 8，單位未知 —— 猜錯比不算糟 |
| 只打周圍 | 芮蘭颶風箭、狂怒／泰坦／瀆神九頭蛇、步履破壞者 | 單體模型下為 0 |
| 擊殺觸發 | 傲慢、公理弧刃、海克斯光學 C44、破堡者 | 需要擊殺序列 |
| 施放大絕觸發 | 獵魔弩箭、實驗型海克斯板甲 | 需要技能模型 |
| 回復與護盾 | 嗜血者、不朽盾弓、魔提斯、死亡之舞、史特拉克的護盾 | 續戰模型是非目標 |
| 法力相關 | 魔劍正宗、大天使之杖 | 模型不算法力 |
| 法師燃燒 | 黎安卓、黑焰火炬、盧登、黯影之炎 | 依賴技能模型 |
| 影響小 | 星蝕、破船戰斧、闇影戰戟 | 之後再補 |

## 6. 組裝與 UI

- `main.py`：`ItemEffectBinder(diagnostics).bind(items)` → `CombatModel(spell_proxy, fight, effects)`；
  邊際欄與規劃器共用，自動吃到被動
- 規劃分頁誠實邊界改為：「已計入 N 件裝備被動；未計入：移速、吸血與護盾、群體效果、英雄技能」
- 詳情面板新增一行：該件的被動是「已建模（類別）」「未建模」或「綁定失敗（缺 X）」
- 狀態列：`unbound_item_effects` 計數
  （實作時更正：`unsupported_formula_parts` 不列入狀態列。真實資料本來就大量含不支援
  組件，只有被效果綁定才有害，而那已以「被動綁定失敗」呈現；列入只會讓狀態列
  永遠不是「無異常」。計數仍保留在 Diagnostics 可查。）

## 7. 效能

每次 profile 評估會多出被動求值。預算：規劃器在 16.16.1 單次 ≤ 1 秒（無被動時 0.37 秒）。
不依賴屬性的公式（海妖、臨界點分段）按 (件, 等級, 遠近程) 快取。

實測（2026-09-15，未做快取）：16.15.1 與 16.16.1 單次規劃 0.75–0.84 秒，在預算內
但已接近上限 —— 快取暫不做，等英雄技能加入後若超標再處理。

## 8. 測試

**公式計算器（fixture 真公式樹）**：海妖 `DamageAmount` 8／9／18 級 = 150／155／200、
遠程 18 級 = 160；臨界點 `ARMRPerHitScaling` 10／11／14 級 = 6／7／8、`ARMRMaxScaling` 14 級 = 24；
納什之牙 AP 100 → 30；三相 基礎 AD 62 → 124。不支援的組件 → `Unsupported` 且計數。

**效果（玩具英雄＋真裝備 ID，手算）**：
- 破敗：遠程、目標 2000 生命、比例 0.5 → 每下 60 物理
- 海妖：遠程 18 級 → 160 × 1.375 ÷ 3 ≈ 73.33 物理
- 鬼索：攻速 +32%；納什＋鬼索時命中特效 × 4/3
- 黑切：目標護甲 200 → 140（先於穿透）
- 多明尼克：坦克額外生命 2000 → × 1.15；脆皮 300 → × 1.03
- 蒐集者：× 1/0.95
- 死亡之帽在峽谷製造者轉換之後乘
- 充能：狂暴利刃每 4 下 100 → 每下 25 魔法
- 魔法彎刀：觸發率受 `SpellbladeCooldown` 下限約束

**綁定失敗**：拿掉 fixture 某件的 `RangedValue` → 破敗效果停用、Diagnostics 記錄。

**不變量**：既有 CombatModel 手算測試（玩具裝備、無被動 ID）數值全數不變。

**預期變更**：規劃器黃金快照（16.15.1 達瑞文）會改變 —— 實測後更新，
並在 `2026-09-14-build-optimizer-design.md` §8 記錄新舊序列與原因。
