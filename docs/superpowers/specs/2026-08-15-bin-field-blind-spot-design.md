# bin 欄位命名盲點修復設計

日期：2026-08-15
狀態：已與使用者確認（全部一次修），待實作
起因：使用者實測發現固定物穿（穿甲）不見了——鋸齒短匕／殘暴之力
1000g、20 物攻、10 穿甲，但系統完全沒讀到穿甲。

## 1. 根因

bin 檔的屬性欄位有**三種命名慣例**，`looks_like_bin_stat_field` 只認第一種
（`m`+大寫開頭+`Mod` 結尾），其餘被靜默丟棄——違反「絕不靜默丟棄」：

1. `mXxxMod`（24 個，已映射）
2. 裸名：`PhysicalLethality`
3. 小寫開頭：`flatMPPoolMod`、`percentBaseMPRegenMod`、`flatMPRegenMod`、
   大寫開頭非 m：`PercentOmnivampMod`

spec 原文兩處結論因此錯誤：「固定物穿在 SR 可購買裝備中未出現」
（實有 12 件）、「bin 完全不存法力」（實有 15 件，值與 DD 全部一致）。

## 2. 16.15.1 實測影響（SR 可購買）

| 欄位 | 件數 | 映射 | 正規化 |
|---|---|---|---|
| `PhysicalLethality` | 12 | `ARMOR_PEN_FLAT`（既有） | 原值 |
| `PercentOmnivampMod` | 6 | `OMNIVAMP`（新增） | ×100（0.025 → 2.5%） |
| `percentBaseMPRegenMod` | 19 | `BASE_MP_REGEN`（新增） | ×100（1.25 → 125%） |
| `flatMPRegenMod` | 1 | `MP_REGEN_FLAT`（新增） | 原值 |
| `flatMPPoolMod` | 15 | `MANA`（既有） | 原值；與 DD 零分歧，交叉檢查涵蓋 |

黃金 4 件裝備（無盡／三相／中婭／殞落王者）都不帶上述欄位，
**12 個黃金 CP值 不變**。

## 3. 變更

### stats.py
- 新增 `OMNIVAMP`、`BASE_MP_REGEN`、`MP_REGEN_FLAT` 三個 StatKey
- `SR_STATS` 21 → **25**（+ARMOR_PEN_FLAT +三個新鍵）；
  非 SR 剩 cooldown_reduction／attack_range／attack_speed_multiplicative
- `BIN_FIELD_TO_STAT` 追加上表 5 個欄位
- `NORMALIZE_X100` 追加 `OMNIVAMP`、`BASE_MP_REGEN`

### mapping.py
- `looks_like_bin_stat_field` 放寬為：數值非 bool 且
  `endswith("Mod") or endswith("Lethality")`。
  已對全 fixture 驗證無誤判（`sellBackModifier` 不以 Mod 結尾、
  `maxStack`／`LastMajorChange*`／`ShopOrderPriority`／`mRequiredLevel` 皆不中）

### weights.py（ResourceRule）
- 歸零集合從單一 `MANA` 擴為 `MANA_LINKED = {MANA, BASE_MP_REGEN,
  MP_REGEN_FLAT}` —— 犽宿不該重視魔力回復

### role_defaults.toml（4 條新列 × 6 角色；可爭論、可修改）
- `armor_pen_flat`：鏡射 `armor_pen_percent`（F0.7 T0.0 M0.0 Mk0.8 A1.0 S0.0）
- `omnivamp`：A0.6 F0.6 Mage0.4 Mk0.6 S0.2 T0.3（全能吸血對法師也有效）
- `base_mp_regen`＝`mp_regen_flat`：鏡射 `mana`（F0.4 T0.4 Mage0.9 Mk0.4 A0.4 S0.8）

### anchors.toml
- `[armor_pen_flat]` 扣除錨：殘暴之力 3134（(1000 − 20AD×35) / 10 = **30.0/穿甲**；
  無被動基礎組件，與權杖／耳語同構）。權威定價 13 → **14** 種；
  未定價 8 + 3 個新屬性 = **11** 種（SR 25 = 14 + 11）

### 黃金測試
- canonical：+ARMOR_PEN_FLAT 30.0、UNPRICED += 3 新屬性、計數 13→14
- NNLS：矩陣 198×21 → 198×24（新欄位進解），全部單價重解 ——
  以 `scripts/report_ls_prices.py` 再生 EXPECTED（Task 8 既有流程）
- 扣除錨自鎖 100% 參數 += 殘暴之力 3134
- 12 個黃金 CP值 斷言不動（黃金 4 件不帶新欄位）

### 主 spec 修正
- §3.3「bin 完全不存法力」→ 更正（小寫欄位、與 DD 零分歧）
- §5.3「固定物穿未出現」→ 更正為扣除錨
- 資料集不變量：屬性種類 21 → 25、可定價/未定價 14/11、NNLS 矩陣欄數

### 連帶效果（不需改碼）
- 權重面板經 `SR_STATS` 自動長出 4 根新拉桿（固定物穿「回來了」）
- 凱爾手寫的 `armor_pen_flat = 0.4` 覆寫從「僅記錄」變為實際生效
- 契約測試的未知欄位偵測（已共用同一 predicate）自動獲得新視野；
  需實跑 `-m network` 確認 16.16.1 無新未知欄位

## 4. 提交策略

StatKey／SR_STATS 一動，role_defaults 覆蓋測試、NNLS 黃金、canonical
未定價清單同時紅，無法拆成各自獨立綠燈的 commit。分三個原子綠燈：

1. **新屬性落地**：stats + mapping + ResourceRule + role_defaults +
   canonical UNPRICED + NNLS 再生（一個大 commit，內部 TDD 先紅後綠）
2. **穿甲扣除錨**：anchors.toml + 相關黃金
3. **spec 更正**

## 5. 非目標

全能吸血／魔回的錨定（無明顯乾淨錨，留給日後爭論）、
lethality 依等級換算物穿的實戰模型（屬 §5.4 Level 3）。
