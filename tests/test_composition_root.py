"""組裝根與分層驗證。"""

import ast
import pathlib

import pytest

from lolcp.main import build_application, build_use_cases

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CONFIG = pathlib.Path(__file__).parent.parent / "config"
SRC = pathlib.Path(__file__).parent.parent / "src" / "lolcp"  # 錨定絕對路徑，cwd 無關


def test_build_application_does_not_touch_the_network(tmp_path):
    context = build_application(cache_root=tmp_path, config_dir=CONFIG)
    assert context.cache.latest_complete() is None
    assert context.diagnostics.summary_line() == "無異常"


def test_build_use_cases_produces_a_working_pipeline(tmp_path):
    """用 fixture 當快取目錄，端到端算出 CP值。"""
    cache_root = tmp_path
    (cache_root / "16.15.1").mkdir(parents=True)
    for f in (FIXTURES / "16.15.1").iterdir():
        (cache_root / "16.15.1" / f.name).write_bytes(f.read_bytes())
    (cache_root / "16.15.1" / ".complete").write_text("", encoding="utf-8")

    context = build_application(cache_root=cache_root, config_dir=CONFIG)
    bundle = build_use_cases(context, "16.15.1")
    list_valuations, champions = bundle.list_valuations, bundle.champions

    comparisons = list_valuations.execute(None)
    assert comparisons
    ie = next(c for c in comparisons if c.item.item_id == 3031)
    assert ie.canonical.ratio * 100 == pytest.approx(103.6, abs=0.05)
    assert any(c.key == "Draven" for c in champions)

    assert len(bundle.item_effects) == 22
    assert context.diagnostics.unbound_item_effects == {}
    assert set(bundle.champion_kits) == {"Draven", "Kayle", "Samira"}
    assert context.diagnostics.unbound_champion_kits == {}
    assert context.diagnostics.missing_champion_spells == ()

    draven = next(c for c in champions if c.key == "Draven")
    plan = bundle.plan_build.execute(draven, "squishy", None, ())
    assert len(plan.steps) == 6


def test_only_main_imports_presentation():
    """組裝根之外，任何模組都不得 import presentation。"""
    scanned = 0
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "main.py" or "presentation" in path.parts:
            continue
        scanned += 1
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mod = node.module if isinstance(node, ast.ImportFrom) else None
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
            for target in filter(None, [mod, *names]):
                if "presentation" in target:
                    offenders.append(f"{path}: {target}")
    assert scanned > 0, "掃描不到任何檔案 —— 路徑錨定失效，測試在空轉"
    assert offenders == []


def test_domain_never_imports_qt():
    paths = list((SRC / "domain").rglob("*.py"))
    assert paths, "掃描不到任何檔案 —— 路徑錨定失效，測試在空轉"
    offenders = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if "PySide6" in source:
            offenders.append(str(path))
    assert offenders == []
