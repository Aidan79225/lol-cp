# 英雄技能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 達瑞文、凱爾、煞蜜拉的技能模型；固定戰鬥時長；三隻英雄的出裝推薦彼此不同。

**Architecture:** 機制、綁定表、假設全在 spec `2026-09-15-champion-kits-design.md` §3–§9，本計畫不重複。

**Tech Stack:** Python 3.13、uv、pytest（Qt offscreen）。

## Global Constraints

- TDD 先紅後綠；commit 繁中，結尾附
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` 與
  `Claude-Session: https://claude.ai/code/session_01LT9PBadGQMgNV9hQDQAzt9`
- **每個 task 結束立刻 commit**（上一輪 Task 2 漏 commit，事後補救打亂了歷史順序）
- 技能以英雄 key 綁定；數值只從 bin 讀，描述文字裡的常數（煞蜜拉 R 10 發）寫在 kit 內並註明出處
- 無 kit 英雄的既有測試數值不變

---

## Task 1: 公式擴充與技能 mapping

**Files:** Modify `domain/formulas.py`、`infrastructure/formula_mapping.py`；Create `domain/spells.py`（`SpellData`、`ChampionSpells`）、`infrastructure/champion_spell_mapper.py`；Test 追加 `test_formulas.py`、Create `tests/infrastructure/test_champion_spell_mapper.py`

**測試：** spec §10 公式擴充；三隻英雄真 bin 的 DataValues 陣列、冷卻、公式解析（Q `TotalDamage` 等）

- [ ] Step 1 寫失敗測試 → Step 2 確認紅 → Step 3 實作 → Step 4 綠 + 全套件 → Step 5 提交

## Task 2: 管線 —— 英雄 bin 下載、舊快取補抓、fixture

**Files:** Modify `infrastructure/http/patch_gateway.py`、`application/use_cases/sync_game_data.py`、`infrastructure/cache/patch_cache.py`、`scripts/build_fixtures.py`；Create `infrastructure/repositories/file_champion_spells_repository.py`；重建 fixture；Test 追加 gateway／sync／cache／repository 測試

**測試：** 版本路徑 major.minor；缺英雄 bin 的完整快取觸發補抓且逐檔原子；repository 缺檔 → None＋診斷

- [ ] 同五步驟（fixture 重建後既有斷言不變）

## Task 3: 技能等級與 kit 設定

**Files:** Create `domain/skill_ranks.py`、`config/kits/{Draven,Kayle,Samira}.toml`；Modify `toml_config.py`（`load_kit_config`）、`combat_model.toml`（`fight_duration_seconds`）；Test Create `test_skill_ranks.py`、`test_kit_config.py`

**測試：** spec §10 技能等級；設定未知鍵、缺鍵、型別、`skill_order` 必須是 Q/W/E 的排列

- [ ] 同五步驟

## Task 4: 戰鬥窗口與三隻 kit

**Files:** Create `domain/champion_kits.py`；Modify `domain/combat.py`（`for_champion`、窗口 DPS、`spell_window_damage`、`magic_shred`、彎刀觸發率、kit 決定遠近程）；Test Create `test_champion_kits.py`

**測試：** spec §10 各英雄與施放次數／持續率；綁定失敗退回泛用基準；無 kit 不變量

- [ ] 同五步驟

## Task 5: 接線、效能、黃金快照

**Files:** Modify `main.py`、`compute_marginals.py`、`plan_build.py`；Test 更新黃金快照（三隻）；Modify build-optimizer spec §8

**內容：** 16.16.1 實測規劃 ≤ 1 秒（超標做 spec §11 快取）；**三隻推薦彼此不同**寫成斷言

- [ ] 同五步驟＋效能實測

## Task 6: UI 誠實邊界

**Files:** Modify `widgets/plan_panel.py`、`diagnostics.py`、`main_window.py`；Test 追加 plan panel／widgets／整合測試

- [ ] 同五步驟＋offscreen 截圖
