# 邊際效益模型 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 表格新增三個邊際效益欄（ΔDPS/千金×2 目標、ΔEHP/千金），以出裝與等級為脈絡，捕捉線性 CP值 看不見的乘法協同。

**Architecture:** 公式與資料形狀全在 spec `2026-08-17-marginal-model-design.md` §3–§4，本計畫不重複；每個 task 的測試值以 spec §8 的手算黃金值為準。

**Tech Stack:** Python 3.13、uv、pytest（Qt offscreen）。

## Global Constraints

- TDD 先紅後綠；commit 繁中 + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 公式常數（基礎暴傷 175%、攻速上限 2.5、成長公式）寫在 domain 常數；
  proxy 與目標常數只在 `config/combat_model.toml`
- 邊際欄在全域視角或 `base_stats is None` 時顯示「—」，不顯示 0

---

## Task 1: domain — `ChampionBaseStats` 與 `CombatModel`

**Files:** Modify `src/lolcp/domain/entities.py`；Create `src/lolcp/domain/combat.py`；Test `tests/domain/test_combat.py`

**Interfaces（spec §4）:** `ChampionBaseStats`（10 欄位 frozen dataclass）；`Champion.base_stats: ChampionBaseStats | None = None`；`growth_factor(level)`；`TargetProfile`；`SpellProxy`；`CombatModel(spell_proxy)` 的 `profile(base, level, items) -> CombatProfile`、`total_dps(profile, target)`、`mixed_ehp(profile)`；常數 `AS_CAP=2.5`、`BASE_CRIT_BONUS=0.75`

**測試（spec §8 手算值）：** growth_factor(1)=0、(11)=8.775、(18)=17×1.0=17.0；達瑞文裸裝 lv11 AS≈0.8399、對脆皮 AA DPS≈32.55；暴擊係數（25%暴擊+30%暴傷 → 1+0.25×1.05=1.2625）；穿透順序（200 甲、30%物穿+10 穿甲 → 130）；AS 上限 2.5；暴擊率上限 100；法術 proxy（AP100、加速 0 → (300+70)×100/150/8 對 mr50）；EHP 混合平均；攻速裝備加成作用於基礎攻速。

- [ ] Step 1 寫失敗測試 → Step 2 確認紅 → Step 3 實作 → Step 4 綠 + 全套件 → Step 5 提交

## Task 2: domain — `MarginalValuation`

**Files:** Modify `src/lolcp/domain/combat.py`；Test 追加 `tests/domain/test_combat.py`

**Interfaces:** `MarginalResult(item, dps_per_1k: Mapping[str, float], ehp_per_1k: float)`；`MarginalValuation(model, targets)`.`evaluate(base, level, build, candidates) -> tuple[MarginalResult, ...]`

**測試：** 長劍的 ΔDPS = 10×AS×護甲倍率（手算）；**無盡協同**——build 含兩件暴擊裝時 IE 的 ΔDPS/千金 > 空 build 時；穿甲裝對坦克 > 對脆皮；鞋子 ΔDPS=ΔEHP=0（誠實邊界）；紅水晶 ΔEHP>0 且 ΔDPS=0。

- [ ] 同 Task 1 五步驟

## Task 3: infrastructure — 設定與英雄基礎值

**Files:** Create `config/combat_model.toml`（spec §5 原文）；Modify `toml_config.py`（`load_combat_config`）、`file_champion_repository.py`（解析 `stats` 區塊）；Test `tests/infrastructure/test_combat_config.py`、追加 `test_file_repositories.py`

**Interfaces:** `load_combat_config(path) -> tuple[SpellProxy, tuple[TargetProfile, ...]]`（缺欄位/未知鍵擲 `ConfigError`）；repository 產出的 `Champion.base_stats` 帶達瑞文實值（ad=62、as=0.679、as_growth=2.7…）；`stats` 缺漏 → None 不炸

- [ ] 同五步驟

## Task 4: application — `ComputeMarginals` 與 `UseCaseBundle`

**Files:** Create `use_cases/compute_marginals.py`；Modify `main.py`（`UseCaseBundle` dataclass 取代三元組；組裝 CombatModel/targets）、`app_coordinator.py`、`main_window.py` 的 `set_use_cases`／建構參數改收 bundle；Test `tests/application/test_compute_marginals.py`＋更新 `test_composition_root.py`、coordinator／main_window 測試的解包

**Interfaces:** `ComputeMarginals(items, model, targets)`.`execute(champion, level, build_ids) -> tuple[MarginalResult, ...]`（champion None 或無 base_stats → `()`）；`UseCaseBundle(list_valuations, champions, adjust_weights, compute_marginals)`；`MainWindow(bundle, diagnostics, parent=None)`、`set_use_cases(bundle)`

- [ ] 同五步驟

## Task 5: presentation — BuildBar、三欄、接線

**Files:** Create `widgets/build_bar.py`；Modify `item_table_model.py`（三欄 + `set_marginals(dict[int, MarginalResult] | None)`）、`main_window.py`（雙擊加入出裝、BuildBar、重算時機）；Test `tests/presentation/test_build_bar.py`、追加 table model 與 main_window 整合測試

**Interfaces:** `BuildBar`：`set_build(items)`、`build_ids` property、`level` property、signals `build_changed`／`level_changed`；table 欄位常數 `COL_DPS_SQUISHY=5`、`COL_DPS_TANK=6`、`COL_EHP=7`，值一位小數、無資料「—」、可排序（無資料排最後）

**整合測試（fixture 快取）：** 選達瑞文 → 雙擊蒐集者+靈巧披風入裝 → IE 的 ΔDPS/千金 欄值上升（協同貫穿到 UI）；切回全域 → 三欄「—」；等級改變觸發重算

- [ ] 同五步驟＋offscreen 冒煙
