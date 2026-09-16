# 接近的替代選項 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 規劃結果每一步列出分數差距在容忍範圍內的其他合法候選，讓「第一名只贏 0.7%」這件事可見。

**Architecture:** 定義與限制全在 spec `2026-09-16-near-tie-alternatives-design.md` §3–§5。

**Tech Stack:** Python 3.13、uv、pytest（Qt offscreen）。

## Global Constraints

- TDD 先紅後綠；每個 task 結束立刻 commit；commit 繁中，結尾附
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` 與
  `Claude-Session: https://claude.ai/code/session_01LT9PBadGQMgNV9hQDQAzt9`
- 既有黃金快照（選中的六件與順序）不得改變 —— 這一步只增加資訊，不改決策

---

## Task 1: domain —— 替代選項計算與設定

**Files:** Modify `domain/build_planner.py`（`PlanAlternative`、`PlanStep.alternatives`、定序後計算）、`infrastructure/repositories/toml_config.py`（兩個新鍵）、`config/build_planner.toml`；Test 追加 `tests/domain/test_build_planner.py`、`tests/infrastructure/test_planner_config.py`

**測試：** spec §6 全部（容忍度邊界、數量上限、群組與鞋位合法性、排序、不含自己）；設定未知鍵／範圍錯誤大聲失敗

- [ ] Step 1 寫失敗測試 → Step 2 確認紅 → Step 3 實作 → Step 4 綠 + 全套件 → Step 5 提交

## Task 2: UI —— 「接近的替代」欄

**Files:** Modify `presentation/widgets/plan_panel.py`；Test 追加 `tests/presentation/test_plan_panel.py`、`tests/presentation/test_main_window_weights.py`

**測試：** 有替代時顯示名稱與百分比、無替代顯示「—」；整合測試選達瑞文規劃後該欄有內容

- [ ] 同五步驟＋offscreen 截圖

## Task 3: 黃金與文件

**Files:** Test 追加 `tests/application/test_plan_build.py`（煞蜜拉第 1 步含無盡之刃）；Modify spec 標為已實作、效能實測

- [ ] 同五步驟＋效能實測（≤ 1 秒）
