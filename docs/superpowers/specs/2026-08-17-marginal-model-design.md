# 邊際效益模型（Level 3 V1）設計

日期：2026-08-17
狀態：已實作
前置：主 spec §5.4（線性模型的極限）、§1.3（工具回答的問題）

## 1. 問題與取徑

線性 CP值 回答「原料划不划算」，回答不了「下一件買什麼」——因為實戰價值
是相乘的（暴傷×暴擊率、穿透×目標護甲、攻速×AD），而乘法意味著一件裝備
的價值取決於**你已經買了什麼**。

使用者的顧慮（傷害計算與操作高度相關、每英雄不同）指向的陷阱是**技能模
擬**——本設計刻意繞開它：不模擬玩家操作與技能連招，只模擬**屬性本身的
物理**（全英雄通用的遊戲規則），英雄差異只透過資料驅動的基礎數值進來，
「操作」以標準目標情境取代。

## 2. 決策記錄

| 決策 | 選擇 |
|---|---|
| V1 範圍 | 普攻 DPS + EHP + 法術爆發 proxy（三條通用公式） |
| UI | 主表格加三欄 + 頂部出裝列（雙擊加入、點擊移除、最多 6 格）+ 等級選擇 |
| 英雄差異 | 只透過 champion.json `stats` 基礎值與成長（零手工建模） |
| 操作假設 | 無。以兩個標準目標（脆皮／坦克）取代 |
| 技能 proxy 常數 | 主觀擇定、寫入設定檔、明標可爭論 |

## 3. 公式（domain `combat.py`，全部可手算驗證）

**等級成長**（Riot 官方非線性）：
`g(lv) = (lv−1) × (0.7025 + 0.0175 × (lv−1))`；`stat(lv) = base + growth × g(lv)`
攻速例外：成長與裝備攻速都是對基礎攻速的百分比加成——
`AS(lv, items) = min(2.5, base_as × (1 + (as_growth × g(lv) + item_as) / 100))`

**普攻 DPS**（對目標 t）：
```
暴擊係數 = 1 + min(暴擊率,100)/100 × (0.75 + 裝備暴傷/100)   # 基礎暴傷 175%
有效護甲 = max(0, t.armor × (1 − 物穿%/100) − 穿甲)           # % 先算、穿甲後扣
AA_DPS  = 總AD × AS × 暴擊係數 × 100/(100 + 有效護甲)
```

**法術爆發 proxy**（對目標 t；常數見 §5，可爭論）：
```
有效魔抗   = max(0, t.mr × (1 − 魔穿%/100) − 固定魔穿)
冷卻       = base_cooldown / (1 + 技能加速/100)
Spell_DPS = (base_damage + ap_ratio × 總AP) × 100/(100 + 有效魔抗) / 冷卻
```

**總 DPS = AA_DPS + Spell_DPS** —— 一組欄位同時服務物理、法系與混傷
（凱爾兩邊都有貢獻；純防裝自然趨零）。基準傷**恆計入**（代表每隻英雄
都有的泛用技能循環）：常數在邊際比較中自然抵銷，AP 件只得到自己的
倍率份額，魔穿與加速合理作用於基準傷。實作曾嘗試 AP>0 閘門，
會讓 435g 增幅典籍繼承整段基準傷而霸榜 —— 已以回歸測試釘死。

**EHP**：`ehp_phys = HP × (1 + 護甲/100)`；`ehp_magic = HP × (1 + 魔抗/100)`；
顯示用混合 EHP = 兩者平均。

**邊際效益**：`Δ指標(裝備) = 指標(出裝+裝備) − 指標(出裝)`；
欄位值 = Δ ÷ 裝備總價 × 1000（每千金）。

## 4. 領域模型

- `ChampionBaseStats`（`entities.py`，frozen）：ad / ad_growth / attack_speed /
  as_growth / hp / hp_growth / armor / armor_growth / mr / mr_growth
- `Champion.base_stats: ChampionBaseStats | None = None`（預設 None 保持
  既有建構相容；無基礎值時邊際欄顯示「—」）
- `combat.py`：`growth_factor(level)`、`TargetProfile(key, name, armor, mr, hp)`、
  `SpellProxy(base_damage, ap_ratio, base_cooldown)`、
  `CombatModel(spell_proxy)`——`profile(base, level, items) -> CombatProfile`
  （聚合總屬性）、`total_dps(profile, target)`、`mixed_ehp(profile)`
- `MarginalValuation(model, targets)`：
  `evaluate(base, level, build: Sequence[Item], candidates) -> tuple[MarginalResult, ...]`
  `MarginalResult(item, dps_per_1k: Mapping[str, float], ehp_per_1k: float)`
  （dps_per_1k 以 target key 為鍵）

模型只讀取公式引用的屬性（AD/AP/攻速/暴擊/暴傷/雙穿/雙魔穿/加速/HP/雙抗）；
移速、吸血、回復等對邊際欄無貢獻——**誠實邊界**，詳情面板不假裝算到。

## 5. 設定 `config/combat_model.toml`

```toml
[spell_proxy]   # 基準技能：主觀擇定、可爭論。改這裡不改碼。
base_damage = 300.0
ap_ratio = 0.7
base_cooldown = 8.0

[targets.squishy]
name = "脆皮"
armor = 60.0
magic_resist = 50.0
hp = 1800.0

[targets.tank]
name = "坦克"
armor = 200.0
magic_resist = 120.0
hp = 4000.0
```

`load_combat_config(path) -> tuple[SpellProxy, tuple[TargetProfile, ...]]`
（`toml_config.py`；未知鍵、缺欄位擲 `ConfigError`）。

## 6. 資料與組裝

- `FileChampionRepository` 解析 en_US `stats` 區塊 → `ChampionBaseStats`；
  區塊缺漏 → `base_stats=None`（不炸——顯示層退化為「—」）
- `build_use_cases` 回傳值改為 `UseCaseBundle` dataclass
  （list_valuations / champions / adjust_weights / compute_marginals）——
  三元組已到可讀性極限，第四個成員前先重構
- application 新 use case `ComputeMarginals(items, model, targets)`：
  `execute(champion, level, build_ids: tuple[int, ...]) -> tuple[MarginalResult, ...]`
  champion 為 None 或無 base_stats → 空 tuple

## 7. UI

- `BuildBar`（新 widget）：已選裝備各一顆按鈕（點擊移除）、「等級」spinbox
  1–18 預設 11、「清空」鈕；signal `build_changed`
- 主表格雙擊列 → 加入出裝（滿 6 格忽略）；新增三欄：
  ΔDPS/千金（脆皮）、ΔDPS/千金（坦克）、ΔEHP/千金——一位小數，
  全域視角或無基礎值顯示「—」；三欄可排序
- 出裝、等級、視角任一變動即重算邊際（純算術，毫秒級，無 NNLS）

## 8. 黃金測試（達瑞文 16.15.1 手算）

`g(11) = 10 × 0.8775 = 8.775`；AD(11) = 62（成長 0）；
AS(11) = 0.679 × 1.236925 ≈ 0.8399；
裸裝對脆皮 AA DPS = 62 × 0.8399 × 1 × 0.625 ≈ 32.55。

關鍵協同斷言（線性模型永遠答不對的那件事）：
**出裝含兩件暴擊裝時，無盡之刃的 ΔDPS/千金 高於空出裝時**。
另斷言：鞋子的 ΔDPS 與 ΔEHP 皆為 0（誠實邊界）；
百分比物穿對坦克的邊際值更高、穿甲（固定值）反而對脆皮的
絕對增益更大 —— 模型自己糾正了設計時的直覺（d/da 100/(100+a)
隨 a 遞減），這正是「打坦買LDR、打脆買穿甲」的數學根源。

## 9. 非目標

技能倍率表與連招模擬、續戰（吸血/回復）模型、羊刀/納什之牙攻擊特效、
被動效果、防禦 EHP 對兩種傷害型的加權（用平均）、全域視角的邊際欄。
