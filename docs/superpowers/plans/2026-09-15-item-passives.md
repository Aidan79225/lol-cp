# 裝備被動 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為約 20 件普攻單體輸出相關傳說裝補上被動；數字由通用公式計算器從 bin 讀取。

**Architecture:** 公式、綁定表、假設全在 spec `2026-09-15-item-passives-design.md` §3–§6，本計畫不重複。

**Tech Stack:** Python 3.13、uv、pytest（Qt offscreen）。

## Global Constraints

- TDD 先紅後綠；commit 繁中，結尾附
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` 與
  `Claude-Session: https://claude.ai/code/session_01LT9PBadGQMgNV9hQDQAzt9`
- 效果一律以裝備 ID 綁定；數值只從 data values／calculations 讀，
  資料不存在的語意常數（鬼索「每 3 下」）寫在效果內並註明出處
- 綁定失敗、不支援的公式組件一律記入 Diagnostics
- 既有 CombatModel 手算測試數值不變；規劃器黃金快照允許改變，但須記錄

---

## Task 1: 公式計算器與 mapping

**Files:** Create `domain/formulas.py`；Modify `domain/entities.py`（`Item.data_values`、`Item.calculations`）、`infrastructure/mapping.py`（公式樹轉換）、`domain/diagnostics.py`（`unsupported_formula_parts`）；Test `tests/domain/test_formulas.py`、追加 `tests/infrastructure/test_mapping.py`

**測試：** spec §8 公式計算器清單（fixture 真公式樹）；兩種分段語意；`StatTerm` 的總值／基礎／額外；`CalcRef` 與 `Scaled`；未知組件與未知屬性代碼 → `Unsupported` 且計數；`UnsupportedFormulaError`

- [x] Step 1 寫失敗測試 → Step 2 確認紅 → Step 3 實作 → Step 4 綠 + 全套件 → Step 5 提交

## Task 2: 資料與設定 —— 攻擊距離、`[fight]`、目標額外生命

**Files:** Modify `domain/entities.py`（`ChampionBaseStats.attack_range`）、`file_champion_repository.py`、`domain/combat.py`（`FightAssumptions`、`TargetProfile.bonus_hp`）、`toml_config.py`（`load_combat_config` 回傳加 fight）、`config/combat_model.toml`；Test 更新 `test_combat_config.py`、`test_file_repositories.py`

**測試：** 達瑞文 attack_range 550、凱爾 175；`[fight]` 缺欄位／未知欄位／型別錯；`energized_attacks` ≥ 1；`average_current_hp_ratio` 在 0..1；targets 缺 `bonus_hp` 大聲失敗

- [x] 同五步驟

## Task 3: 效果與傷害模型 V2

**Files:** Create `domain/item_effects.py`（效果、註冊表、`ItemEffectBinder`）；Modify `domain/combat.py`（傷害拆分、效果套用）、`domain/diagnostics.py`（`unbound_item_effects`）；Test `tests/domain/test_item_effects.py`、確認 `tests/domain/test_combat.py` 不變

**測試：** spec §8 效果清單全數（真裝備 ID 取自 fixture）；綁定失敗停用＋記錄；多件充能相加；彎刀觸發率下限；既有 test_combat 全綠

- [x] 同五步驟

## Task 4: 組裝、效能、黃金快照

**Files:** Modify `main.py`、`application/use_cases/*`（若簽名變動）；Test 更新 `tests/application/test_plan_build.py` 黃金快照、`test_compute_marginals.py`；Modify spec `2026-09-14-build-optimizer-design.md` §8

**內容：** 綁定器接入組裝根；16.16.1 實測規劃器單次 ≤ 1 秒（超過則做 spec §7 的快取）；重新實測黃金快照、記錄新舊序列與原因

- [x] 同五步驟＋效能實測

## Task 5: UI 誠實邊界

**Files:** Modify `widgets/plan_panel.py`（邊界文字含已建模件數）、`widgets/detail_panel.py`（被動狀態行）、`widgets/status_bar.py`（新診斷計數）；Test 追加 `test_plan_panel.py`、`test_widgets.py`、`test_main_window_weights.py`

**內容：** 邊界文字；詳情面板「已建模（類別）／未建模／綁定失敗」；offscreen 截圖目視

- [x] 同五步驟＋offscreen 截圖
