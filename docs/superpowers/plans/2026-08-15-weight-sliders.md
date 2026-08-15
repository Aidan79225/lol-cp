# 英雄權重拉桿 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 英雄視角的 21 種屬性權重可在 UI 以拉桿檢視與調整，調整寫回 `config/champions/*.toml`（保留手寫註解）。

**Architecture:** domain 加 `resolve_defaults`／`replace_overrides`；application 加 `OverridesStore` port 與 `AdjustChampionWeight` use case；infrastructure 以行級編輯實作 `TomlOverridesStore`；presentation 加 `WeightPanel` 並把右側面板改為分頁。

**Tech Stack:** Python 3.13、uv、pytest（Qt offscreen）。

**Spec:** `docs/superpowers/specs/2026-08-15-weight-sliders-design.md`

## Global Constraints

- TDD：先紅再綠才提交；commit 沿用繁中風格 + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 拉桿範圍 0.00–1.00、步進 0.05；全域視角停用
- 「有覆寫」恆等於「與基準值不同」；調回基準 = 刪除覆寫
- 行級編輯：既有行只換數值（行尾註解保留）、整行註解不動

---

## Task 1: domain — `resolve_defaults` / `replace_overrides`

**Files:**
- Modify: `src/lolcp/domain/weights.py`（`WeightResolver`）
- Test: `tests/domain/test_weight_resolver.py`（追加）

**Interfaces:**
- Produces: `WeightResolver.resolve_defaults(champion: Champion | None) -> StatWeights`（只跑前兩層）；`WeightResolver.replace_overrides(overrides: ChampionOverrides) -> None`；`WeightResolver.overrides` property（唯讀取用）
- `resolve` 行為完全不變（重構為 `resolve_defaults` + 覆寫套用）

- [ ] **Step 1: 追加失敗測試**（沿用檔內 `resolver`/`champion` helper）

```python
def test_resolve_defaults_excludes_overrides():
    """拉桿基準值 = 前兩層，不含覆寫。

    用純 Marksman 的達瑞文 —— 凱爾的聯集會因 Mage 未定義物穿
    而取到 1.0（寧可多算原則），驗不到「排除覆寫」這件事。"""
    weights = resolver({"Draven": {StatKey.ARMOR_PEN_PERCENT: 0.4}}).resolve_defaults(
        champion("Draven", ("Marksman",))
    )
    assert weights.of(StatKey.ARMOR_PEN_PERCENT) == 0.8


def test_resolve_defaults_still_applies_resource_rule():
    weights = resolver().resolve_defaults(
        champion("Yasuo", ("Marksman",), partype="Flow")
    )
    assert weights.of(StatKey.MANA) == 0.0


def test_resolve_defaults_for_none_is_uniform():
    assert resolver().resolve_defaults(None).of(StatKey.AD) == 1.0


def test_replace_overrides_takes_effect_on_next_resolve():
    r = resolver()
    assert r.resolve(champion("Draven", ("Marksman",))).of(StatKey.ARMOR_PEN_PERCENT) == 0.8
    r.replace_overrides(
        ChampionOverrides({"Draven": {StatKey.ARMOR_PEN_PERCENT: 0.1}})
    )
    assert r.resolve(champion("Draven", ("Marksman",))).of(StatKey.ARMOR_PEN_PERCENT) == 0.1
    assert r.overrides.by_champion["Draven"][StatKey.ARMOR_PEN_PERCENT] == 0.1
```

- [ ] **Step 2: 確認失敗** — `uv run pytest tests/domain/test_weight_resolver.py -v` → FAIL（`resolve_defaults` 不存在）

- [ ] **Step 3: 實作** — `WeightResolver.resolve` 改為：

```python
    def resolve(self, champion: Champion | None) -> StatWeights:
        if champion is None:
            return StatWeights.uniform()  # 全域客觀視角
        weights = self.resolve_defaults(champion)
        return self._overrides.apply(weights, champion.key)

    def resolve_defaults(self, champion: Champion | None) -> StatWeights:
        """前兩層（角色預設 → 資源規則），即零覆寫時的值。拉桿的基準。"""
        if champion is None:
            return StatWeights.uniform()
        weights = self._role_defaults.union_max(champion.tags, self._diagnostics)
        return self._resource_rule.apply(weights, champion)

    def replace_overrides(self, overrides: ChampionOverrides) -> None:
        """拉桿寫檔後換掉覆寫層。domain 第二個刻意可變處（第一個是 Diagnostics）。"""
        self._overrides = overrides

    @property
    def overrides(self) -> ChampionOverrides:
        return self._overrides
```

- [ ] **Step 4: 確認通過** — 13 passed（原 9 + 新 4）；`uv run pytest -q` 全綠
- [ ] **Step 5: 提交** — `feat: WeightResolver 支援基準值查詢與覆寫替換`

---

## Task 2: application — `OverridesStore` port 與 `AdjustChampionWeight`

**Files:**
- Modify: `src/lolcp/application/ports.py`（追加 `OverridesStore`）
- Create: `src/lolcp/application/use_cases/adjust_champion_weight.py`
- Test: `tests/application/test_adjust_champion_weight.py`

**Interfaces:**
- Consumes: Task 1 的 `resolve_defaults`/`replace_overrides`
- Produces:
  - `OverridesStore`（Protocol）：`load() -> ChampionOverrides`、`set_weight(champion_key: str, stat: StatKey, value: float | None) -> None`（None = 移除）
  - `AdjustChampionWeight(store, resolver)`；`execute(champion, stat, value) -> ChampionOverrides` —— 與基準差 < 1e-9 即移除覆寫，寫檔後 `replace_overrides` 立即生效

- [ ] **Step 1: 寫失敗測試 — `tests/application/test_adjust_champion_weight.py`**

```python
import pytest

from lolcp.application.use_cases.adjust_champion_weight import AdjustChampionWeight
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.entities import Champion
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import (
    ChampionOverrides,
    ResourceRule,
    RoleDefaults,
    StatWeights,
    WeightResolver,
)

DRAVEN = Champion("Draven", 119, "達瑞文", ("Marksman",), "Mana")


class FakeStore:
    def __init__(self):
        self.data: dict[str, dict[StatKey, float]] = {}

    def load(self):
        return ChampionOverrides({k: dict(v) for k, v in self.data.items()})

    def set_weight(self, champion_key, stat, value):
        row = self.data.setdefault(champion_key, {})
        if value is None:
            row.pop(stat, None)
            if not row:
                del self.data[champion_key]
        else:
            row[stat] = value


def make_resolver() -> WeightResolver:
    d = Diagnostics()
    return WeightResolver(
        role_defaults=RoleDefaults(
            {"Marksman": StatWeights({StatKey.AD: 1.0, StatKey.AP: 0.0})}
        ),
        resource_rule=ResourceRule(d),
        overrides=ChampionOverrides({}),
        diagnostics=d,
    )


def test_adjusting_away_from_default_writes_an_override():
    store, resolver = FakeStore(), make_resolver()
    AdjustChampionWeight(store, resolver).execute(DRAVEN, StatKey.AP, 0.5)
    assert store.data["Draven"][StatKey.AP] == 0.5
    assert resolver.resolve(DRAVEN).of(StatKey.AP) == 0.5


def test_adjusting_back_to_default_removes_the_override():
    store, resolver = FakeStore(), make_resolver()
    use_case = AdjustChampionWeight(store, resolver)
    use_case.execute(DRAVEN, StatKey.AP, 0.5)
    use_case.execute(DRAVEN, StatKey.AP, 0.0)  # Marksman 的 AP 基準 = 0.0
    assert "Draven" not in store.data
    assert resolver.resolve(DRAVEN).of(StatKey.AP) == 0.0


def test_returned_overrides_reflect_the_store():
    store, resolver = FakeStore(), make_resolver()
    overrides = AdjustChampionWeight(store, resolver).execute(DRAVEN, StatKey.AP, 0.3)
    assert overrides.by_champion["Draven"][StatKey.AP] == 0.3
```

- [ ] **Step 2: 確認失敗** — `ModuleNotFoundError: ...adjust_champion_weight`

- [ ] **Step 3: 實作**

`ports.py` 檔頂 import 加 `from lolcp.domain.stats import StatKey`、`from lolcp.domain.weights import ChampionOverrides`，檔尾追加：

```python
class OverridesStore(Protocol):
    def load(self) -> ChampionOverrides: ...

    def set_weight(
        self, champion_key: str, stat: StatKey, value: float | None
    ) -> None: ...
```

`use_cases/adjust_champion_weight.py`：

```python
"""拉桿調整英雄權重：寫入覆寫層並讓 resolver 立即生效。"""

from __future__ import annotations

from lolcp.application.ports import OverridesStore
from lolcp.domain.entities import Champion
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import ChampionOverrides, WeightResolver

_EPS = 1e-9


class AdjustChampionWeight:
    def __init__(self, store: OverridesStore, resolver: WeightResolver) -> None:
        self._store = store
        self._resolver = resolver

    def execute(
        self, champion: Champion, stat: StatKey, value: float
    ) -> ChampionOverrides:
        """調到基準值即移除覆寫 —— 「有覆寫」恆等於「與基準不同」。"""
        default = self._resolver.resolve_defaults(champion).of(stat)
        target = None if abs(value - default) < _EPS else value
        self._store.set_weight(champion.key, stat, target)
        overrides = self._store.load()
        self._resolver.replace_overrides(overrides)
        return overrides
```

- [ ] **Step 4: 確認通過** — 3 passed；AST 分層掃描不受影響（application 只 import domain）
- [ ] **Step 5: 提交** — `feat: AdjustChampionWeight use case 與 OverridesStore port`

---

## Task 3: infrastructure — `TomlOverridesStore` 行級編輯

**Files:**
- Create: `src/lolcp/infrastructure/repositories/toml_overrides_store.py`
- Test: `tests/infrastructure/test_toml_overrides_store.py`

**Interfaces:**
- Produces: `TomlOverridesStore(directory: Path)`，結構型別滿足 `OverridesStore`

- [ ] **Step 1: 寫失敗測試**

```python
from pathlib import Path

import pytest

from lolcp.domain.stats import StatKey
from lolcp.infrastructure.repositories.toml_overrides_store import TomlOverridesStore

REPO_CHAMPIONS = Path(__file__).parent.parent.parent / "config" / "champions"


def store_with_kayle(tmp_path) -> TomlOverridesStore:
    (tmp_path / "Kayle.toml").write_text(
        (REPO_CHAMPIONS / "Kayle.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return TomlOverridesStore(tmp_path)


def comment_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("#")
    ]


def test_updating_a_value_preserves_every_comment_line(tmp_path):
    store = store_with_kayle(tmp_path)
    before = comment_lines(tmp_path / "Kayle.toml")
    store.set_weight("Kayle", StatKey.ARMOR_PEN_PERCENT, 0.55)
    after = comment_lines(tmp_path / "Kayle.toml")
    assert before and after == before  # 真的有註解可保，且逐行不變
    assert store.load().by_champion["Kayle"][StatKey.ARMOR_PEN_PERCENT] == 0.55


def test_removing_an_override_deletes_only_that_line(tmp_path):
    store = store_with_kayle(tmp_path)
    store.set_weight("Kayle", StatKey.ARMOR_PEN_PERCENT, None)
    overrides = store.load().by_champion["Kayle"]
    assert StatKey.ARMOR_PEN_PERCENT not in overrides
    assert StatKey.ARMOR_PEN_FLAT in overrides  # 另一行不受影響


def test_new_stat_is_appended_to_existing_file(tmp_path):
    store = store_with_kayle(tmp_path)
    store.set_weight("Kayle", StatKey.LIFE_STEAL, 0.2)
    assert store.load().by_champion["Kayle"][StatKey.LIFE_STEAL] == 0.2
    assert comment_lines(tmp_path / "Kayle.toml")  # 註解仍在


def test_missing_file_is_created_with_header(tmp_path):
    store = TomlOverridesStore(tmp_path)
    store.set_weight("Draven", StatKey.AP, 0.5)
    text = (tmp_path / "Draven.toml").read_text(encoding="utf-8")
    assert text.startswith("#")
    assert store.load().by_champion["Draven"][StatKey.AP] == 0.5


def test_removing_from_missing_file_is_a_noop(tmp_path):
    TomlOverridesStore(tmp_path).set_weight("Draven", StatKey.AP, None)
    assert not (tmp_path / "Draven.toml").exists()


def test_store_satisfies_the_overrides_store_port():
    import inspect

    from lolcp.application.ports import OverridesStore

    for name in ("load", "set_weight"):
        port_sig = inspect.signature(getattr(OverridesStore, name))
        impl_sig = inspect.signature(getattr(TomlOverridesStore, name))
        assert list(port_sig.parameters) == list(impl_sig.parameters)
```

- [ ] **Step 2: 確認失敗** — `ModuleNotFoundError: ...toml_overrides_store`

- [ ] **Step 3: 實作**

```python
"""行級編輯的覆寫存放。手寫註解是刻意經營的資產，不可被序列化抹掉。"""

from __future__ import annotations

import re
from pathlib import Path

from lolcp.domain.stats import StatKey
from lolcp.domain.weights import ChampionOverrides
from lolcp.infrastructure.repositories.toml_config import load_champion_overrides

_HEADER = "# 由權重拉桿產生。可手動編輯；既有註解在拉桿寫入時會被保留。\n"


class TomlOverridesStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def load(self) -> ChampionOverrides:
        return load_champion_overrides(self._directory)

    def set_weight(
        self, champion_key: str, stat: StatKey, value: float | None
    ) -> None:
        path = self._directory / f"{champion_key}.toml"
        if not path.is_file():
            if value is None:
                return  # 本來就沒有覆寫
            self._directory.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"{_HEADER}{stat.config_key} = {value:g}\n", encoding="utf-8"
            )
            return

        pattern = re.compile(
            rf"^(\s*{re.escape(stat.config_key)}\s*=\s*)[0-9eE.+-]+(.*)$"
        )
        out: list[str] = []
        replaced = False
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
            match = pattern.match(line)
            if match is None:
                out.append(line)
            elif value is None:
                replaced = True  # 移除覆寫 = 刪行（含行尾註解）
            else:
                newline = "\n" if line.endswith("\n") else ""
                out.append(f"{match.group(1)}{value:g}{match.group(2)}{newline}")
                replaced = True
        if not replaced and value is not None:
            if out and not out[-1].endswith("\n"):
                out[-1] += "\n"
            out.append(f"{stat.config_key} = {value:g}\n")
        path.write_text("".join(out), encoding="utf-8")
```

- [ ] **Step 4: 確認通過** — 7 passed；`uv run pytest -q` 全綠
- [ ] **Step 5: 提交** — `feat: TomlOverridesStore 行級編輯覆寫檔`

---

## Task 4: presentation — `WeightPanel`

**Files:**
- Create: `src/lolcp/presentation/widgets/weight_panel.py`
- Test: `tests/presentation/test_weight_panel.py`

**Interfaces:**
- Produces: `WeightPanel(parent=None)`；`set_context(champion: Champion | None, defaults: StatWeights | None, overrides: Mapping[StatKey, float])`；signal `weight_committed = Signal(object, float)`（StatKey, 新值）；還原鈕發基準值（移除語意由 use case 判定）

- [ ] **Step 1: 寫失敗測試 — `tests/presentation/test_weight_panel.py`**

```python
import pytest

from lolcp.domain.entities import Champion
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import StatWeights
from lolcp.presentation.widgets.weight_panel import WeightPanel

pytestmark = pytest.mark.usefixtures("qapp")

DRAVEN = Champion("Draven", 119, "達瑞文", ("Marksman",), "Mana")


def defaults() -> StatWeights:
    return StatWeights({StatKey.AD: 1.0, StatKey.AP: 0.0, StatKey.MANA: 0.4})


def test_sliders_reflect_defaults_and_overrides():
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {StatKey.AP: 0.5})
    assert panel._sliders[StatKey.AD].value() == 20  # 1.0 / 0.05
    assert panel._sliders[StatKey.AP].value() == 10  # 覆寫 0.5
    assert panel._values[StatKey.AP].text() == "0.50"
    assert panel._names[StatKey.AP].font().bold() is True
    assert panel._names[StatKey.AD].font().bold() is False


def test_global_view_disables_everything():
    panel = WeightPanel()
    panel.set_context(None, None, {})
    assert not panel._sliders[StatKey.AD].isEnabled()
    assert panel._values[StatKey.AD].text() == "—"


def test_release_emits_the_slider_value():
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {})
    seen: list[tuple[object, float]] = []
    panel.weight_committed.connect(lambda s, v: seen.append((s, v)))
    panel._sliders[StatKey.AP].setValue(13)
    panel._sliders[StatKey.AP].sliderReleased.emit()
    assert seen == [(StatKey.AP, pytest.approx(0.65))]


def test_reset_emits_the_default_value():
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {StatKey.AP: 0.5})
    seen: list[tuple[object, float]] = []
    panel.weight_committed.connect(lambda s, v: seen.append((s, v)))
    panel._on_reset(StatKey.AP)
    assert seen == [(StatKey.AP, 0.0)]


def test_reset_all_emits_for_every_override():
    panel = WeightPanel()
    panel.set_context(DRAVEN, defaults(), {StatKey.AP: 0.5, StatKey.MANA: 0.9})
    seen: list[object] = []
    panel.weight_committed.connect(lambda s, v: seen.append(s))
    panel._on_reset_all()
    assert set(seen) == {StatKey.AP, StatKey.MANA}
```

- [ ] **Step 2: 確認失敗** — `ModuleNotFoundError: ...weight_panel`

- [ ] **Step 3: 實作 `weight_panel.py`**

```python
"""權重拉桿面板。拉桿 = 編輯覆寫層；基準值 = 前兩層解析結果。

sliderReleased 才發 weight_committed —— 每次重算會重跑 NNLS，
拖曳中不觸發。還原鈕發「基準值」，移除覆寫的語意由 use case 判定
（與基準相同即刪除），面板自己不做這個判斷。
"""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lolcp.domain.entities import Champion
from lolcp.domain.stats import StatKey
from lolcp.domain.weights import StatWeights

_STEP = 0.05
_STEPS = 20  # 0.00～1.00


class WeightPanel(QWidget):
    weight_committed = Signal(object, float)  # (StatKey, 新值)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._defaults: StatWeights | None = None
        self._overrides: dict[StatKey, float] = {}
        self._sliders: dict[StatKey, QSlider] = {}
        self._values: dict[StatKey, QLabel] = {}
        self._names: dict[StatKey, QLabel] = {}

        self._hint = QLabel("全域視角為客觀基準，不可調整", self)
        self._reset_all = QPushButton("全部還原", self)
        self._reset_all.clicked.connect(self._on_reset_all)

        grid_host = QWidget(self)
        grid = QGridLayout(grid_host)
        for row, stat in enumerate(StatKey):
            name = QLabel(stat.config_key, grid_host)
            slider = QSlider(Qt.Orientation.Horizontal, grid_host)
            slider.setRange(0, _STEPS)
            slider.sliderReleased.connect(lambda s=stat: self._on_released(s))
            value = QLabel("", grid_host)
            reset = QPushButton("還原", grid_host)
            reset.clicked.connect(lambda _checked=False, s=stat: self._on_reset(s))
            grid.addWidget(name, row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(value, row, 2)
            grid.addWidget(reset, row, 3)
            self._sliders[stat] = slider
            self._values[stat] = value
            self._names[stat] = name
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)

        layout = QVBoxLayout(self)
        layout.addWidget(self._hint)
        layout.addWidget(self._reset_all)
        layout.addWidget(scroll, 1)

    # ---- 外部驅動 ----

    def set_context(
        self,
        champion: Champion | None,
        defaults: StatWeights | None,
        overrides: Mapping[StatKey, float],
    ) -> None:
        editable = champion is not None and defaults is not None
        self._defaults = defaults if editable else None
        self._overrides = dict(overrides) if editable else {}
        self._hint.setVisible(not editable)
        self._reset_all.setEnabled(editable)
        for stat, slider in self._sliders.items():
            slider.setEnabled(editable)
            current = self._current(stat) if editable else 0.0
            slider.blockSignals(True)
            slider.setValue(round(current / _STEP))
            slider.blockSignals(False)
            self._values[stat].setText(f"{current:.2f}" if editable else "—")
            self._set_overridden_style(stat, editable and stat in self._overrides)

    # ---- 內部 ----

    def _current(self, stat: StatKey) -> float:
        if stat in self._overrides:
            return self._overrides[stat]
        return self._defaults.of(stat) if self._defaults else 0.0

    def _set_overridden_style(self, stat: StatKey, overridden: bool) -> None:
        font = self._names[stat].font()
        font.setBold(overridden)
        self._names[stat].setFont(font)

    def _on_released(self, stat: StatKey) -> None:
        if self._defaults is None:
            return
        self.weight_committed.emit(stat, self._sliders[stat].value() * _STEP)

    def _on_reset(self, stat: StatKey) -> None:
        if self._defaults is None:
            return
        self.weight_committed.emit(stat, self._defaults.of(stat))

    def _on_reset_all(self) -> None:
        if self._defaults is None:
            return
        for stat in list(self._overrides):
            self.weight_committed.emit(stat, self._defaults.of(stat))
```

- [ ] **Step 4: 確認通過** — 5 passed
- [ ] **Step 5: 提交** — `feat: WeightPanel 權重拉桿面板`

---

## Task 5: 接線 — MainWindow 分頁、組裝根三元組、整合測試

**Files:**
- Modify: `src/lolcp/presentation/main_window.py`
- Modify: `src/lolcp/main.py`（`build_use_cases` 回傳三元組）
- Modify: `src/lolcp/presentation/app_coordinator.py`（解包三元組）
- Modify: `tests/test_composition_root.py`（解包更新）
- Test: `tests/presentation/test_main_window_weights.py`

**Interfaces:**
- `build_use_cases(context, version) -> (ListValuations, tuple[Champion, ...], AdjustChampionWeight)`
- `MainWindow.__init__(list_valuations, champions, diagnostics, adjust_weights=None, parent=None)`
- `MainWindow.set_use_cases(list_valuations, champions, adjust_weights=None)`

- [ ] **Step 1: 寫失敗測試 — `tests/presentation/test_main_window_weights.py`**

```python
"""拉桿 → use case → 重算 → 寫檔的整合測試（fixture 快取 + tmp 設定複本）。"""

import pathlib
import shutil

import pytest

from lolcp.domain.stats import StatKey
from lolcp.main import build_application, build_use_cases
from lolcp.presentation.main_window import MainWindow

pytestmark = pytest.mark.usefixtures("qapp")

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
CONFIG = pathlib.Path(__file__).parent.parent.parent / "config"


@pytest.fixture
def window(tmp_path):
    cache_root = tmp_path / "cache"
    (cache_root / "16.15.1").mkdir(parents=True)
    for f in (FIXTURES / "16.15.1").iterdir():
        shutil.copy(f, cache_root / "16.15.1" / f.name)
    (cache_root / "16.15.1" / ".complete").write_text("", encoding="utf-8")
    config_dir = tmp_path / "config"
    shutil.copytree(CONFIG, config_dir)
    context = build_application(cache_root=cache_root, config_dir=config_dir)
    list_valuations, champions, adjust = build_use_cases(context, "16.15.1")
    w = MainWindow(list_valuations, champions, context.diagnostics, adjust)
    w.reload()
    return w, config_dir


def select_champion(w: MainWindow, name: str) -> None:
    for i in range(w._profile.count()):
        if w._profile.itemText(i) == name:
            w._profile.setCurrentIndex(i)
            return
    raise AssertionError(f"selector 沒有 {name}")


def zhonya_ratio(w: MainWindow) -> float:
    for r in range(w._model.rowCount()):
        c = w._model.comparison_at(r)
        if c.item.item_id == 3157:
            return c.canonical.ratio
    raise AssertionError("表格裡沒有中婭沙漏")


def test_weight_commit_reprices_and_persists(window):
    w, config_dir = window
    select_champion(w, "達瑞文")
    assert zhonya_ratio(w) == pytest.approx(0.092, abs=0.001)

    w._on_weight_committed(StatKey.AP, 0.5)

    assert zhonya_ratio(w) > 0.3  # 105 法強從全遮罩變 0.5 權重
    text = (config_dir / "champions" / "Draven.toml").read_text(encoding="utf-8")
    assert "ap = 0.5" in text


def test_weight_commit_back_to_default_removes_the_entry(window):
    w, config_dir = window
    select_champion(w, "達瑞文")
    w._on_weight_committed(StatKey.AP, 0.5)
    w._on_weight_committed(StatKey.AP, 0.0)  # Marksman 的 AP 基準 = 0.0
    text = (config_dir / "champions" / "Draven.toml").read_text(encoding="utf-8")
    assert "ap =" not in text
    assert zhonya_ratio(w) == pytest.approx(0.092, abs=0.001)


def test_weight_panel_follows_profile_switching(window):
    w, _ = window
    select_champion(w, "達瑞文")
    assert w._weight_panel._sliders[StatKey.AD].isEnabled()
    select_champion(w, "全域")
    assert not w._weight_panel._sliders[StatKey.AD].isEnabled()
```

- [ ] **Step 2: 確認失敗** — `build_use_cases` 回傳 2 元組 → unpack 錯誤

- [ ] **Step 3: 實作接線**

`main.py` 的 `build_use_cases` 改為（import 區加 `from lolcp.application.use_cases.adjust_champion_weight import AdjustChampionWeight`、`from lolcp.infrastructure.repositories.toml_overrides_store import TomlOverridesStore`；`load_champion_overrides` 改由 store 提供）：

```python
def build_use_cases(context: AppContext, version: str):
    """資料就緒後才能組裝 —— repository 需要知道版本目錄。"""
    patch_dir = context.cache.dir_for(version)
    diagnostics = context.diagnostics
    items = FileItemRepository(patch_dir, ItemMapper(diagnostics))
    champions = FileChampionRepository(patch_dir, diagnostics)
    overrides_store = TomlOverridesStore(context.config_dir / "champions")
    weight_resolver = WeightResolver(
        role_defaults=load_role_defaults(context.config_dir / "role_defaults.toml"),
        resource_rule=ResourceRule(diagnostics),
        overrides=overrides_store.load(),
        diagnostics=diagnostics,
    )
    list_valuations = ListValuations(
        items=items,
        canonical_deriver=CanonicalDeriver(
            load_anchors(context.config_dir / "anchors.toml"), diagnostics
        ),
        least_squares_deriver=LeastSquaresDeriver(diagnostics),
        weight_resolver=weight_resolver,
        valuation=LinearValuation(),
    )
    adjust_weights = AdjustChampionWeight(overrides_store, weight_resolver)
    return list_valuations, champions.all_champions(), adjust_weights
```

（`load_champion_overrides` 若不再被 main.py 使用，從 import 移除。）

`main_window.py`：

1. import 加 `QTabWidget` 與 `from lolcp.presentation.widgets.weight_panel import WeightPanel`
2. `__init__` 簽名加 `adjust_weights=None`（`diagnostics` 之後、`parent` 之前），存 `self._adjust_weights = adjust_weights`
3. 建構區把 `self._detail` 直接進 splitter 改為分頁：

```python
        self._detail = DetailPanel(self)
        self._weight_panel = WeightPanel(self)
        self._weight_panel.weight_committed.connect(self._on_weight_committed)
        tabs = QTabWidget(self)
        tabs.addTab(self._detail, "詳情")
        tabs.addTab(self._weight_panel, "權重")
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._table)
        splitter.addWidget(tabs)
        splitter.setSizes([700, 400])
```

4. `set_use_cases` 加 `adjust_weights=None` 參數並存入
5. `reload()` 末尾加 `self._refresh_weight_panel()`
6. 內部方法追加：

```python
    def _refresh_weight_panel(self) -> None:
        champion = self._profile.current_champion()
        resolver = self._list_valuations.weight_resolver
        if champion is None:
            self._weight_panel.set_context(None, None, {})
            return
        self._weight_panel.set_context(
            champion,
            resolver.resolve_defaults(champion),
            resolver.overrides.by_champion.get(champion.key, {}),
        )

    def _on_weight_committed(self, stat, value: float) -> None:
        champion = self._profile.current_champion()
        if champion is None or self._adjust_weights is None:
            return
        self._adjust_weights.execute(champion, stat, value)
        self.reload()
```

`app_coordinator.py` 的 `on_finished` 兩處解包更新：

```python
        if self._window is None:
            list_valuations, champions, adjust_weights = self._build(result.version)
            self._window = MainWindow(
                list_valuations, champions, self._diagnostics, adjust_weights
            )
            self._window.refresh_button.clicked.connect(self._on_refresh_clicked)
            self._window.show()
        elif result.version != self._version:
            self._window.set_use_cases(*self._build(result.version))
```

`tests/test_composition_root.py` 的 `test_build_use_cases_produces_a_working_pipeline` 解包改為
`list_valuations, champions, _adjust = build_use_cases(context, "16.15.1")`。

- [ ] **Step 4: 確認通過** — 新測試 3 passed；`uv run pytest -q` 全綠（coordinator 測試經 `build` lambda 自動取得三元組）
- [ ] **Step 5: 提交** — `feat: 權重拉桿接線 —— 右側分頁、組裝根三元組`
