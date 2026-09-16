# 戰鬥模型修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正攻速公式與上限、雲陶狂箭持續率、達瑞文接斧比例預設；佐證寫進 spec。

**Architecture:** 佐證與公式全在 spec `2026-09-16-combat-model-corrections-design.md`，本計畫不重複。

**Tech Stack:** Python 3.13、uv、pytest（Qt offscreen）。

## Global Constraints

- TDD 先紅後綠；每個 task 結束立刻 commit；commit 繁中，結尾附
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` 與
  `Claude-Session: https://claude.ai/code/session_01LT9PBadGQMgNV9hQDQAzt9`
- 無技能模型的英雄（泛用基準）所有既有測試數值不得改變
- 兩項「確認原本就對」（Q 加傷不吃暴擊、臨界點明暗可同時）**不得動**，只補註解與佐證

---

## Task 1: 攻速公式、攻速係數與上限

**Files:** Modify `domain/spells.py`（`ChampionSpells.attack_speed_ratio`）、`infrastructure/champion_spell_mapper.py`（讀 CharacterRecord）、`domain/combat.py`（公式、`AS_CAP`、`ChampionKitView`、`StatSheet`）、`domain/champion_kits.py`（BoundKit 轉發）、`scripts/build_fixtures.py`（已改，保留 CharacterRecord）；Test 追加 `test_champion_spell_mapper.py`、`test_combat.py`、`test_champion_kits.py`

**測試：** spec §5 攻速公式與上限；凱爾 1.292、達瑞文／煞蜜拉不變；無 kit 等價

- [x] Step 1 寫失敗測試 → Step 2 確認紅 → Step 3 實作 → Step 4 綠 + 全套件 → Step 5 提交

## Task 2: 雲陶狂箭 Flurry 持續率

**Files:** Modify `domain/item_effects.py`（階段改為傷害類、以冷卻實算）、`domain/combat.py`（`StatSheet.attack_speed`）；Test 追加 `test_item_effects.py`

**測試：** spec §5 Flurry 三個端點；綁定名稱缺漏 → 效果停用並留痕

- [x] 同五步驟

## Task 3: 接斧比例預設、黃金快照與文件

**Files:** Modify `config/kits/Draven.toml`；Test 更新 `test_plan_build.py` 黃金快照與 `test_kit_config.py`；Modify build-optimizer spec §8、本 spec 標為已實作

**內容：** 實測三隻英雄新序列並更新；三隻推薦彼此不同必須持續成立；效能仍需 ≤ 1 秒

- [x] 同五步驟＋效能實測
