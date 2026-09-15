# 出裝規劃器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 自動排出 6 件成品＋購買順序＋每步戰力，評分為 DPS × (EHP/裸裝EHP)^β。

**Architecture:** 公式、判準、限制全在 spec `2026-09-14-build-optimizer-design.md` §3–§7，本計畫不重複；CombatModel 不改。

**Tech Stack:** Python 3.13、uv、pytest（Qt offscreen）。

## Global Constraints

- TDD 先紅後綠；commit 繁中，結尾附
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` 與
  `Claude-Session: https://claude.ai/code/session_01LT9PBadGQMgNV9hQDQAzt9`
- 規劃常數只在 `config/build_planner.toml`；候選池與群組判準只在 domain
- 查不到的群組參照、被略過的部件一律留下痕跡（Diagnostics／`BuildPlan.skipped`）
- 既有 411 個測試的斷言不得修改數值

---

## Task 1: 資料 —— `Item` 擴充、群組解析、fixture 重建

**Files:** Modify `domain/entities.py`（`GroupLimit`、`Item.epicness/upgrades/group_limits`）、`infrastructure/mapping.py`、`domain/diagnostics.py`（未解析群組計數）、`scripts/build_fixtures.py`；重建 `tests/fixtures/16.15.1/items_bin.json`；Test 追加 `tests/infrastructure/test_mapping.py`

**測試：** 無盡之刃 epicness=5、upgrades=()；暴風之劍 upgrades 含 3031；多明尼克的問候 group_limits 含 `GroupLimit("LastWhisper", 1)`；狂戰士護脛含 `GroupLimit("Boots", 1)`；Default 群組不出現；bin 參照不存在的群組 → Diagnostics 計數 +1（合成資料）

- [x] Step 1 寫失敗測試 → Step 2 確認紅 → Step 3 實作 mapping 與 fixture 腳本 → Step 4 重建 fixture（`uv run python scripts/build_fixtures.py`），**全套件既有斷言不變** → Step 5 提交

## Task 2: domain —— `build_planner.py`

**Files:** Create `domain/build_planner.py`；Test `tests/domain/test_build_planner.py`

**Interfaces（spec §6.2）:** `is_legendary`、`is_boots`、`PlannerSettings`、`PlanStep`、`BuildPlan`、`BuildPlanner(model).plan(base, target, pool, prefix, settings)`

**測試（玩具裝備，spec §8 domain 清單全數）：** V 手算值、β=0 等於 DPS、群組上限、鞋位與 `boots_slot=0`、前綴保序、部件入 skipped、前綴滿 6、窮舉排序最優（小池子暴力比對）、確定性

- [x] 同五步驟

## Task 3: 設定與 application —— `build_planner.toml`、`PlanBuild`、bundle

**Files:** Create `config/build_planner.toml`（spec §7.1 原文）、`application/use_cases/plan_build.py`；Modify `toml_config.py`（`load_planner_config`）、`main.py`（`UseCaseBundle.plan_build`）；Test `tests/infrastructure/test_planner_config.py`、`tests/application/test_plan_build.py`、更新 `test_composition_root.py`

**測試：** 設定檔錯誤分支（未知鍵、缺鍵、型別、levels 長度、boots_slot 範圍）；champion None／無 base_stats → None；fixture 達瑞文性質測試（6 件不重複、恰一雙鞋、無群組超限、β=1 EHP ≥ β=0）

- [x] 同五步驟

## Task 4: presentation —— 「出裝規劃」分頁

**Files:** Create `presentation/widgets/plan_panel.py`；Modify `main_window.py`（分頁、規劃、套用到出裝列）、`widgets/build_bar.py`（`set_items(items)` 一次替換，只發一次 `build_changed`）；Test `tests/presentation/test_plan_panel.py`、追加 `test_main_window_weights.py` 整合測試

**整合測試：** 全域視角分頁停用；選達瑞文 → 規劃 → 結果 6 列；套用後 `build_bar.build_ids` 等於結果序列且邊際欄重算；出裝列有部件時結果顯示被略過的件

- [x] 同五步驟＋offscreen 冒煙＋實際開 app 目視一次

## Task 5: 黃金快照

**Files:** Test 追加 `tests/application/test_plan_build.py`；Modify spec §8（寫入實測序列）

**內容：** 以 fixture 實測達瑞文 vs 脆皮、β=0.25 的完整序列寫成斷言，並回填 spec §8

- [x] 實測 → 寫斷言 → 綠 → 回填 spec → 提交
