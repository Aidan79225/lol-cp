import pytest

from lolcp.domain.build_planner import AlternativeTier, BuildPlan, PlanAlternative, PlanStep
from lolcp.domain.combat import TargetProfile
from lolcp.domain.entities import Champion, ChampionBaseStats, Item
from lolcp.presentation.widgets.plan_panel import PlanPanel

pytestmark = pytest.mark.usefixtures("qapp")

BASE = ChampionBaseStats(
    attack_damage=62.0, attack_damage_growth=0.0,
    attack_speed=0.679, attack_speed_growth=2.7,
    hp=675.0, hp_growth=104.0,
    armor=29.0, armor_growth=4.5,
    magic_resist=30.0, magic_resist_growth=1.3,
)
DRAVEN = Champion("Draven", 119, "達瑞文", ("Marksman",), "None", base_stats=BASE)
GHOST = Champion("Ghost", 1, "無數值", ("Mage",), "Mana", base_stats=None)
TARGETS = (
    TargetProfile("squishy", "脆皮", 60.0, 50.0, 1800.0),
    TargetProfile("tank", "坦克", 200.0, 120.0, 4000.0),
)


def item(item_id: int, name: str) -> Item:
    return Item(item_id=item_id, name=name, total_gold=3000, sell_gold=2100,
                stats=(), tags=(), icon="", recipe=(), epicness=5)


def sample_plan() -> BuildPlan:
    return BuildPlan(
        steps=(
            PlanStep(item(3031, "無盡之刃"), 9, 300.0, 2500.0, 310.5,
                     alternatives=(
                         PlanAlternative(item(6672, "海妖殺手"), 0.996, AlternativeTier.NEAR),
                         PlanAlternative(item(3032, "雲陶狂箭"), 0.925, AlternativeTier.CONSIDER),
                     )),
            PlanStep(item(3006, "狂戰士護脛"), 11, 400.0, 2800.0, 412.25),
        ),
        value=1.0,
        skipped=(item(1018, "靈巧披風"),),
    )


def panel() -> PlanPanel:
    p = PlanPanel()
    p.set_targets(TARGETS, 0.25)
    return p


def test_enabled_only_for_a_champion_with_base_stats():
    p = panel()
    p.set_context(None)
    assert not p.isEnabled()
    p.set_context(GHOST)
    assert not p.isEnabled()
    p.set_context(DRAVEN)
    assert p.isEnabled()


def test_targets_and_default_beta_are_shown():
    p = panel()
    assert p._target_combo.count() == 2
    assert p._target_combo.itemText(0) == "脆皮"
    assert p.current_target_key == "squishy"
    assert p.beta == pytest.approx(0.25)


def test_plan_button_emits_current_target_and_beta():
    p = panel()
    p.set_context(DRAVEN)
    seen: list[tuple[str, float]] = []
    p.plan_requested.connect(lambda key, beta: seen.append((key, beta)))
    p._target_combo.setCurrentIndex(1)
    p._beta_spin.setValue(0.5)
    p._plan_button.click()
    assert seen == [("tank", pytest.approx(0.5))]


def test_show_plan_fills_rows_reports_skipped_and_enables_apply():
    p = panel()
    p.set_context(DRAVEN)
    assert not p._apply_button.isEnabled()
    p.show_plan(sample_plan())
    assert p._table.rowCount() == 2
    assert p._table.item(0, 1).text() == "無盡之刃"
    assert p._table.item(1, 2).text() == "11"
    assert "靈巧披風" in p._skipped_label.text()
    assert p._apply_button.isEnabled()

    fired: list[int] = []
    p.apply_requested.connect(lambda: fired.append(1))
    p._apply_button.click()
    assert fired == [1]


def test_alternatives_column_lists_near_ties_with_their_gap():
    """第一名常只贏 1% 以內 —— 把接近的選擇攤出來（spec 2026-09-16 near-tie §5）。"""
    p = panel()
    p.set_context(DRAVEN)
    p.show_plan(sample_plan())
    text = p._table.item(0, PlanPanel.COL_ALTERNATIVES).text()
    assert "海妖殺手 -0.4%（接近）" in text
    assert "雲陶狂箭 -7.5%（可考慮）" in text


def test_alternatives_cell_keeps_the_full_text_in_a_tooltip():
    """替代欄內容比欄寬長，表格會截斷 —— 滑鼠停留必須看得到全文。"""
    p = panel()
    p.set_context(DRAVEN)
    p.show_plan(sample_plan())
    cell = p._table.item(0, PlanPanel.COL_ALTERNATIVES)
    assert cell.toolTip() == cell.text()
    assert "（可考慮）" in cell.toolTip()


def test_step_without_alternatives_shows_a_dash():
    p = panel()
    p.set_context(DRAVEN)
    p.show_plan(sample_plan())
    assert p._table.item(1, PlanPanel.COL_ALTERNATIVES).text() == "—"


def test_show_none_clears_everything():
    p = panel()
    p.set_context(DRAVEN)
    p.show_plan(sample_plan())
    p.show_plan(None)
    assert p.plan is None
    assert p._table.rowCount() == 0
    assert p._skipped_label.text() == ""
    assert not p._apply_button.isEnabled()


def test_context_change_clears_the_previous_plan():
    p = panel()
    p.set_context(DRAVEN)
    p.show_plan(sample_plan())
    p.set_context(None)
    assert p.plan is None
    assert p._table.rowCount() == 0


def test_honest_boundary_note_names_what_is_not_modelled():
    text = panel()._boundary.text()
    assert "被動" in text and "移速" in text and "吸血" in text


def test_boundary_note_reports_how_many_passives_are_modelled():
    p = panel()
    p.set_modelled_passives(22)
    assert "已計入 22 件裝備被動" in p._boundary.text()
    assert "群體效果" in p._boundary.text()


def test_boundary_note_defaults_to_the_generic_spell_proxy():
    assert "技能：泛用基準" in panel()._boundary.text()


def test_boundary_note_shows_the_skill_status_without_losing_the_passive_count():
    """英雄技能已建模（spec champion-kits §9）—— 不再列為「未計入」。"""
    p = panel()
    p.set_modelled_passives(22)
    p.set_skill_status("技能：已建模（熟練玩家假設，見 config/kits/Draven.toml）")
    text = p._boundary.text()
    assert "已計入 22 件裝備被動" in text
    assert "config/kits/Draven.toml" in text
    assert "英雄技能" not in text
