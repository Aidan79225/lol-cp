# 扣除法錨定 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 權威定價法支援扣除法錨定，讓 life_steal 由吸血鬼權杖定出 375/7 ≈ 53.571/1%。

**Architecture:** `AnchorEntry` 加選配 `deduct` 欄位；`CanonicalDeriver.derive` 兩趟（純錨定 → 扣除錨），三道嚴格驗證任一不符即擲 `AnchorItemMissingError`。設定驅動，這次只錨 life_steal。連帶把 `DetailPanel` 殘差措辭改為三分支。

**Tech Stack:** Python 3.13、uv、pytest（Qt 測試以 `QT_QPA_PLATFORM=offscreen`）。

**Spec:** `docs/superpowers/specs/2026-08-15-deduction-anchors-design.md`

## Global Constraints

- TDD：先寫失敗測試、確認失敗、再實作、確認通過、才提交
- 測試皆離線（`-m network` 預設跳過，本計畫不動網路層）
- commit 訊息沿用本 repo 繁中風格，結尾附 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 計畫或 spec 的錯誤以獨立「計畫修正」commit 先修再實作
- 錯誤訊息一律繁中，包含裝備 ID 與名稱

---

## Task 1: domain — `AnchorEntry.deduct` 與兩趟推導

**Files:**
- Modify: `src/lolcp/domain/pricing.py`（`AnchorEntry`、`CanonicalDeriver`）
- Test: `tests/domain/test_pricing_canonical.py`（追加）

**Interfaces:**
- Consumes: 現有 `AnchorEntry(stat, item_id, reason)`、`CanonicalDeriver`、`AnchorItemMissingError`
- Produces:
  - `AnchorEntry.deduct: tuple[StatKey, ...] = ()`（keyword 選配，預設空 = 純錨定）
  - `CanonicalDeriver.derive` 支援扣除錨：`單價 = (total_gold − Σ 扣除量×純錨單價) / 目標量`
  - 驗證失敗訊息關鍵詞：`屬性集合`（集合不符）、`純錨定`（依賴違規）、`殘額`（≤ 0）

- [ ] **Step 1: 追加失敗測試到 `tests/domain/test_pricing_canonical.py`**

檔尾追加（沿用檔內既有 `item`/`anchors` helper；`anchors` helper 只建純錨定，扣除錨直接建 `AnchorEntry`）：

```python
def test_deduction_anchor_prices_the_remainder():
    """吸血鬼權杖 (900 − 15AD×35) / 7 = 53.571... 每 1%。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    table = CanonicalDeriver(config, Diagnostics()).derive(items)
    assert table.unit_price(StatKey.LIFE_STEAL) == pytest.approx(375 / 7)


def test_deduction_entry_order_in_config_does_not_matter():
    """扣除錨寫在它依賴的純錨之前也要能解 —— 兩趟推導與設定順序無關。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
        AnchorEntry(StatKey.AD, 1036, "test"),
    ))
    table = CanonicalDeriver(config, Diagnostics()).derive(items)
    assert table.unit_price(StatKey.LIFE_STEAL) == pytest.approx(375 / 7)


def test_extra_stat_on_deduction_anchor_fails_loudly():
    """Riot 幫權杖加了新屬性 —— 目標∪deduct 必須恰好等於裝備全屬性。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0),
             StatLine(StatKey.HP, 100.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="屬性集合"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_deduct_listing_a_stat_the_item_lacks_fails_loudly():
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1018, 600, StatLine(StatKey.CRIT_CHANCE, 15.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.CRIT_CHANCE, 1018, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test",
                    deduct=(StatKey.AD, StatKey.CRIT_CHANCE)),
    ))
    with pytest.raises(AnchorItemMissingError, match="屬性集合"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_deduct_referencing_an_unanchored_stat_fails_loudly():
    """單層依賴：deduct 只能引用設定內的純錨定屬性。"""
    items = [
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="純錨定"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_deduct_referencing_another_deduction_anchor_fails_loudly():
    """扣除錨引用扣除錨也違反單層依賴，同樣要炸。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 900, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
        item(3172, 1100, StatLine(StatKey.LIFE_STEAL, 5.0), StatLine(StatKey.TENACITY, 20.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
        AnchorEntry(StatKey.TENACITY, 3172, "test", deduct=(StatKey.LIFE_STEAL,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="純錨定"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_nonpositive_remainder_fails_loudly():
    """扣完 ≤ 0 代表錨定假設崩壞，不可產生負單價或零單價。"""
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 400, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="殘額"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_exactly_zero_remainder_also_fails():
    items = [
        item(1036, 350, StatLine(StatKey.AD, 10.0)),
        item(1053, 525, StatLine(StatKey.AD, 15.0), StatLine(StatKey.LIFE_STEAL, 7.0)),
    ]
    config = AnchorConfig((
        AnchorEntry(StatKey.AD, 1036, "test"),
        AnchorEntry(StatKey.LIFE_STEAL, 1053, "test", deduct=(StatKey.AD,)),
    ))
    with pytest.raises(AnchorItemMissingError, match="殘額"):
        CanonicalDeriver(config, Diagnostics()).derive(items)


def test_pure_entries_default_to_empty_deduct():
    assert AnchorEntry(StatKey.AD, 1036, "test").deduct == ()
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/domain/test_pricing_canonical.py -v`
Expected: FAIL — `TypeError: AnchorEntry.__init__() got an unexpected keyword argument 'deduct'`

- [ ] **Step 3: 修改 `src/lolcp/domain/pricing.py`**

`AnchorEntry` 加欄位（docstring 一併補充）：

```python
@dataclass(frozen=True)
class AnchorEntry:
    """一種屬性的錨定基礎裝備。

    item_id 一律為數值 ID。以名稱查找會拿到其他模式的變體
    （長劍 1036 是 350g，771036 是 400g），單價全錯且不報錯。

    deduct 非空即為「扣除錨」：單價 = (總價 − Σ 扣除屬性量 × 純錨單價)
    ÷ 目標屬性量。用於沒有純屬性基礎裝備的屬性（如吸血）。
    deduct 只能引用純錨定屬性（單層依賴，見 spec 2026-08-15 §5）。
    """

    stat: StatKey
    item_id: int
    reason: str
    deduct: tuple[StatKey, ...] = ()
```

`CanonicalDeriver` 改為兩趟，並把共用檢查抽成 `_anchor_item` / `_target_amount`：

```python
    def derive(self, items: Sequence[Item]) -> PriceTable:
        by_id = {i.item_id: i for i in items}
        prices: dict[StatKey, float | None] = {stat: None for stat in StatKey}
        pure = [e for e in self._anchors.entries if not e.deduct]
        derived = [e for e in self._anchors.entries if e.deduct]
        for entry in pure:
            prices[entry.stat] = self._price_from_anchor(entry, by_id)
        pure_stats = frozenset(e.stat for e in pure)
        for entry in derived:
            prices[entry.stat] = self._price_by_deduction(
                entry, by_id, prices, pure_stats
            )
        return PriceTable(prices=prices, low_confidence=frozenset())

    def _price_from_anchor(self, entry: AnchorEntry, by_id: dict[int, Item]) -> float:
        anchor = self._anchor_item(entry, by_id)
        return anchor.total_gold / self._target_amount(entry, anchor)

    def _price_by_deduction(
        self,
        entry: AnchorEntry,
        by_id: dict[int, Item],
        prices: dict[StatKey, float | None],
        pure_stats: frozenset[StatKey],
    ) -> float:
        """扣除法（spec 2026-08-15 §5）：三道嚴格驗證，任一不符即大聲失敗。

        Riot 改動錨定裝備的屬性組成時要在啟動時炸掉，
        絕不靜默產生漂移的單價。
        """
        anchor = self._anchor_item(entry, by_id)

        expected = frozenset((entry.stat, *entry.deduct))
        if expected != anchor.stat_keys:
            missing = sorted(s.name for s in expected - anchor.stat_keys)
            extra = sorted(s.name for s in anchor.stat_keys - expected)
            raise AnchorItemMissingError(
                f"扣除錨 {entry.item_id}（{anchor.name}）屬性集合不符："
                f"deduct 多列了 {missing or '無'}、裝備多出 {extra or '無'}。"
                f"Riot 可能改動了該裝備，需更新 anchors.toml。"
            )

        outside = sorted(s.name for s in entry.deduct if s not in pure_stats)
        if outside:
            raise AnchorItemMissingError(
                f"扣除錨 {entry.item_id}（{anchor.name}）的 deduct {outside} "
                f"不是純錨定屬性 —— deduct 只能引用純錨定（單層依賴）。"
            )

        remainder = anchor.total_gold - sum(
            anchor.amount_of(s) * prices[s] for s in entry.deduct
        )
        if remainder <= 0:
            raise AnchorItemMissingError(
                f"扣除錨 {entry.item_id}（{anchor.name}）扣除後殘額 "
                f"{remainder:g} ≤ 0，錨定假設已崩壞，無法定價。"
            )
        return remainder / self._target_amount(entry, anchor)

    def _anchor_item(self, entry: AnchorEntry, by_id: dict[int, Item]) -> Item:
        anchor = by_id.get(entry.item_id)
        if anchor is None:
            raise AnchorItemMissingError(
                f"錨定裝備 {entry.item_id} 不存在於當前版本"
                f"（{entry.stat.config_key}）。Riot 可能已移除該裝備，需更新 anchors.toml。"
            )
        return anchor

    @staticmethod
    def _target_amount(entry: AnchorEntry, anchor: Item) -> float:
        amount = anchor.amount_of(entry.stat)
        if amount is None:
            raise AnchorItemMissingError(
                f"錨定裝備 {entry.item_id}（{anchor.name}）沒有 "
                f"{entry.stat.name} 屬性，無法用於定價。"
            )
        if amount == 0:
            raise AnchorItemMissingError(
                f"錨定裝備 {entry.item_id}（{anchor.name}）的 "
                f"{entry.stat.name} 數量為 0，無法作為分母。"
            )
        return amount
```

注意：原 `_price_from_anchor` 的檢查全部移入 `_anchor_item`/`_target_amount`，錯誤訊息一字不改（既有測試 `match="1036"`、`match="AD"`、`match="數量為 0"` 靠它們）。

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest tests/domain/test_pricing_canonical.py -v`
Expected: 18 passed（原 9 + 新 9）

- [ ] **Step 5: 執行完整測試套件**

Run: `uv run pytest -q`
Expected: 全部通過（307 passed；`AnchorEntry` 加選配欄位不影響既有呼叫端）

- [ ] **Step 6: 提交**

```bash
git add src/lolcp/domain/pricing.py tests/domain/test_pricing_canonical.py
git commit -m "feat: CanonicalDeriver 支援扣除法錨定

deduct 非空的條目改用兩趟推導：先解全部純錨定，再以
(總價 − Σ 扣除量×純錨單價) ÷ 目標量 解扣除錨。

三道嚴格驗證任一不符即擲 AnchorItemMissingError：
1. 目標∪deduct 必須恰好等於裝備全屬性 —— Riot 改裝備要炸
2. deduct 只能引用純錨定屬性 —— 單層依賴，循環不可能
3. 扣除後殘額必須 > 0 —— 不產生荒謬單價

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 2: infrastructure — `load_anchors` 解析 `deduct`

**Files:**
- Modify: `src/lolcp/infrastructure/repositories/toml_config.py`（`load_anchors`）
- Test: `tests/infrastructure/test_toml_config.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `AnchorEntry.deduct`
- Produces: `load_anchors` 解析 toml 的 `deduct = ["ad", ...]` 為 `tuple[StatKey, ...]`；省略時為 `()`；未知鍵名擲 `UnknownStatKeyError`；非陣列擲 `ConfigError`（訊息含「陣列」）

- [ ] **Step 1: 追加失敗測試到 `tests/infrastructure/test_toml_config.py`**

```python
def test_deduct_list_is_parsed_into_stat_keys(tmp_path):
    toml = tmp_path / "anchors.toml"
    toml.write_text(
        '[ad]\nitem_id = 1036\nreason = "純錨"\n\n'
        '[life_steal]\nitem_id = 1053\ndeduct = ["ad"]\nreason = "扣除錨"\n',
        encoding="utf-8",
    )
    entry = load_anchors(toml).for_stat(StatKey.LIFE_STEAL)
    assert entry is not None
    assert entry.deduct == (StatKey.AD,)


def test_omitted_deduct_defaults_to_empty(tmp_path):
    toml = tmp_path / "anchors.toml"
    toml.write_text('[ad]\nitem_id = 1036\nreason = "純錨"\n', encoding="utf-8")
    entry = load_anchors(toml).for_stat(StatKey.AD)
    assert entry.deduct == ()


def test_unknown_deduct_key_is_rejected_with_valid_options(tmp_path):
    toml = tmp_path / "anchors.toml"
    toml.write_text(
        '[life_steal]\nitem_id = 1053\ndeduct = ["attak_speed"]\nreason = "typo"\n',
        encoding="utf-8",
    )
    with pytest.raises(UnknownStatKeyError) as exc:
        load_anchors(toml)
    assert "attack_speed" in str(exc.value)


def test_non_list_deduct_is_rejected(tmp_path):
    toml = tmp_path / "anchors.toml"
    toml.write_text(
        '[life_steal]\nitem_id = 1053\ndeduct = "ad"\nreason = "非陣列"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="陣列"):
        load_anchors(toml)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/infrastructure/test_toml_config.py -v`
Expected: FAIL — 前兩個新測試因 `load_anchors` 未傳 `deduct`（`entry.deduct == ()` 那個會過，`(StatKey.AD,)` 那個會敗）；非陣列與未知鍵測試因未解析而不擲錯

- [ ] **Step 3: 修改 `load_anchors`**

`toml_config.py` 的 `load_anchors` 迴圈內，`entries.append` 前加解析、`AnchorEntry` 補參數：

```python
def load_anchors(path: Path) -> AnchorConfig:
    raw = _read_toml(path)
    entries: list[AnchorEntry] = []
    for key, body in raw.items():
        stat = StatKey.from_config_key(key)  # 未知鍵擲 UnknownStatKeyError
        if not isinstance(body, dict) or "item_id" not in body:
            raise ConfigError(f"錨定項 {key!r} 缺少 item_id")
        deduct_raw = body.get("deduct", [])
        if not isinstance(deduct_raw, list):
            raise ConfigError(f"錨定項 {key!r} 的 deduct 必須是陣列")
        entries.append(
            AnchorEntry(
                stat=stat,
                item_id=int(body["item_id"]),
                reason=str(body.get("reason", "")),
                deduct=tuple(StatKey.from_config_key(d) for d in deduct_raw),
            )
        )
    return AnchorConfig(entries=tuple(entries))
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest tests/infrastructure/test_toml_config.py -v`
Expected: 12 passed（原 8 + 新 4）

- [ ] **Step 5: 提交**

```bash
git add src/lolcp/infrastructure/repositories/toml_config.py tests/infrastructure/test_toml_config.py
git commit -m "feat: load_anchors 解析 deduct 清單

省略時為空 tuple（純錨定）；未知鍵名沿用 UnknownStatKeyError
報有效選項；非陣列擲 ConfigError。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 3: 設定 life_steal 錨 + 黃金測試與 spec 更新

**Files:**
- Modify: `config/anchors.toml`（新增 `[life_steal]`）
- Modify: `tests/infrastructure/test_toml_config.py`（條目數 11→12、屬性集合）
- Modify: `tests/golden/test_canonical_prices.py`（單價表、未定價清單、計數）
- Modify: `tests/golden/test_golden_cp_values.py`（BotRK 三視角、新增權杖黃金測試）
- Modify: `docs/superpowers/specs/2026-08-12-lol-item-gold-efficiency-design.md`（§5.3、§8、§10.2）

**Interfaces:**
- Consumes: Task 1–2 的扣除錨機制
- Produces: 權威法 12 種定價屬性；life_steal = 375/7；BotRK 黃金值 (80.0, 639.3, 0, 0)

**注意**：anchors.toml 一改，`test_real_anchors_file_has_eleven_entries`、`test_real_anchors_cover_exactly_the_priceable_stats`、`test_canonical_prices` 的三個斷言與 `test_golden_cp_values` 的 BotRK 列會立刻紅，因此設定與測試更新必須同一個 commit。先改測試（紅）、再改設定（綠），TDD 順序如下。

- [ ] **Step 1: 更新黃金測試與 toml 測試（先紅）**

`tests/infrastructure/test_toml_config.py`：

```python
def test_real_anchors_file_has_twelve_entries():
    config = load_anchors(ANCHORS)
    assert len(config.entries) == 12
```

（原 `test_real_anchors_file_has_eleven_entries` 改名改數。）

`test_real_anchors_cover_exactly_the_priceable_stats` 的集合加入 `StatKey.LIFE_STEAL`。

`tests/golden/test_canonical_prices.py`：

- `EXPECTED_PRICES` 加 `StatKey.LIFE_STEAL: 375 / 7,   # 53.571 每 1% —— 扣除錨：權杖 900 − 15AD×35`
- `UNPRICED` 移除 `StatKey.LIFE_STEAL`（剩 9 種）
- `test_exactly_eleven_stats_are_priced` 改名 `test_exactly_twelve_stats_are_priced`，斷言 12

`tests/golden/test_golden_cp_values.py` 的 `EXPECTED` 三列 BotRK 更新：

```python
    (None, BOTRK): (80.0, 639.3, 0, 0),       # 吸血以扣除法計價後不再是下限
    ("Draven", BOTRK): (80.0, 639.3, 0, 0),   # 與全域相同：AD/攻速/吸血權重皆 1.0
    ("Kayle", BOTRK): (80.0, 639.3, 0, 0),    # Mage∪Marksman 聯集後同上
```

並在檔尾追加：

```python
def test_vampiric_scepter_is_locked_to_exactly_100_percent(engine):
    """扣除錨的固有代價：錨定裝備自身 CP值 恆為 100%、殘差 0。

    這個黃金值同時驗證扣除法的算式 —— 若單價不是 375/7，比率不會是 1。
    """
    by_id, prices, resolver, _ = engine
    result = LinearValuation().evaluate(by_id[1053], prices, resolver.resolve(None))
    assert result.ratio == pytest.approx(1.0)
    assert result.residual == pytest.approx(0.0, abs=1e-9)
    assert result.unpriced == ()
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/infrastructure/test_toml_config.py tests/golden -q`
Expected: FAIL — 條目數 12≠11、LIFE_STEAL 單價為 None、BotRK 仍是 63.3

- [ ] **Step 3: 修改 `config/anchors.toml`**

檔尾追加：

```toml
[life_steal]
item_id = 1053   # 吸血鬼權杖 (900 − 15AD×35) / 7% = 53.571 每 1%
deduct = ["ad"]
reason = "無純吸血基礎裝備（七件帶吸血裝備皆複合屬性）。社群傳統扣除法：權杖扣掉物攻餘額歸吸血。代價：權杖自身 CP值 被鎖成 100%。NNLS 給 37.0，兩法分歧本身是分析入口。"
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest -q`
Expected: 全部通過（原數 + 新增 1 個權杖黃金測試）

- [ ] **Step 5: 更新主 spec**

`docs/superpowers/specs/2026-08-12-lol-item-gold-efficiency-design.md`：

1. §5.3「**其餘 10 種無錨可定價**」段落：10 改 9，清單移除「生命偷取」，
   並在錨定表描述處補一句：「生命偷取為扣除錨：吸血鬼權杖扣除物攻餘額歸吸血
   （375/7 ≈ 53.571），見 `2026-08-15-deduction-anchors-design.md`」。
2. `grep -n '63\.3\|1175' docs/superpowers/specs/2026-08-12-lol-item-gold-efficiency-design.md`
   找出所有 BotRK 舊值（§8 敘事、§8 表格、§10.2 黃金值表），逐一改為
   80.0%／殘差 639：§8 那句
   「**殞落王者之劍 63.3%（與全域相同）** — 低分來自生命偷取未定價，與英雄無關」
   改為
   「**殞落王者之劍 80.0%（與全域相同）** — 吸血已由扣除法計價，殘差 639g 是被動（現血狂擊）的隱含價值，與英雄無關」。
   改完再 grep 一次確認無殘留。
3. 若 §10.2 有「未定價 1」之類的 BotRK 欄位，一併改 0。

- [ ] **Step 6: 提交**

```bash
git add config/anchors.toml tests/infrastructure/test_toml_config.py tests/golden docs/superpowers/specs/2026-08-12-lol-item-gold-efficiency-design.md
git commit -m "feat: life_steal 扣除錨上線

吸血鬼權杖 (900 − 15AD×35) / 7% = 53.571 每 1%。
權威法定價屬性 11 → 12 種，未定價 10 → 9 種。

殞落王者之劍 63.3% → 80.0%（殘差 1175 → 639），
三視角相同的性質保持成立（Marksman 與 Mage∪Marksman
的吸血權重皆 1.0）。權杖自身被鎖成恰好 100%／殘差 0，
作為新黃金值 —— 這同時驗證扣除算式本身。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Task 4: DetailPanel 殘差三分支措辭

**Files:**
- Modify: `src/lolcp/presentation/widgets/detail_panel.py`（`render_lines` 尾段）
- Test: `tests/presentation/test_widgets.py`（追加）

**Interfaces:**
- Consumes: `ValuationResult.residual`（float）；domain 的 `residual_is_passive_value` 語意不變
- Produces: 殘差顯示三分支——`>0`「至少這些金幣花在被動效果上」、`<0`「屬性本身已超值」、`=0`「屬性恰好定價」；分支判斷用**取整後**的值，浮點雜訊（±1e-13）歸零

- [ ] **Step 1: 追加失敗測試到 `tests/presentation/test_widgets.py`**

```python
def test_zero_residual_is_neither_passive_nor_bargain():
    fair = Item(item_id=1, name="公道", total_gold=350, sell_gold=175,
                stats=(StatLine(StatKey.AD, 10.0),), tags=(), icon="", recipe=())
    result = evaluate(fair, StatWeights.uniform(), {StatKey.AD: 35.0})
    text = "\n".join(DetailPanel.render_lines(result))
    assert "恰好定價" in text
    assert "被動" not in text and "超值" not in text


def test_float_noise_residual_is_treated_as_zero():
    """扣除錨裝備（吸血鬼權杖）的殘差是 ±1e-13 浮點雜訊，
    不可顯示成「+0g（被動…）」或「-0g（超值）」。"""
    noisy = Item(item_id=1, name="雜訊", total_gold=900, sell_gold=450,
                 stats=(StatLine(StatKey.LIFE_STEAL, 7.0),), tags=(), icon="", recipe=())
    result = evaluate(noisy, StatWeights.uniform(), {StatKey.LIFE_STEAL: 900 / 7.0})
    text = "\n".join(DetailPanel.render_lines(result))
    assert "恰好定價" in text
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `uv run pytest tests/presentation/test_widgets.py -v`
Expected: FAIL — 目前零殘差走「屬性本身已超值」分支，無「恰好定價」字樣

- [ ] **Step 3: 修改 `render_lines` 尾段**

把

```python
        if result.residual_is_passive_value:
            lines.append(f"殘差 +{result.residual:.0f}g（至少這些金幣花在被動效果上）")
        else:
            lines.append(f"殘差 {result.residual:.0f}g（屬性本身已超值）")
```

改為

```python
        residual = round(result.residual)  # 顯示取整；扣除錨的 ±1e-13 浮點雜訊歸零
        if residual > 0:
            lines.append(f"殘差 +{residual}g（至少這些金幣花在被動效果上）")
        elif residual < 0:
            lines.append(f"殘差 {residual}g（屬性本身已超值）")
        else:
            lines.append("殘差 0g（屬性恰好定價）")
```

- [ ] **Step 4: 執行測試確認通過**

Run: `uv run pytest tests/presentation/test_widgets.py -v`
Expected: 16 passed（原 14 + 新 2）

- [ ] **Step 5: 執行完整測試套件**

Run: `uv run pytest -q`
Expected: 全部通過

- [ ] **Step 6: 提交**

```bash
git add src/lolcp/presentation/widgets/detail_panel.py tests/presentation/test_widgets.py
git commit -m "fix: 殘差措辭三分支，浮點雜訊歸零

殘差恰為 0（扣除錨裝備必然如此）原本會顯示「屬性本身已超值」，
措辭錯誤。改為 >0 被動／<0 超值／=0 恰好定價，且分支判斷用
取整後的值 —— 權杖的 ±1e-13 殘差不可顯示成 +0g（被動…）。

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
