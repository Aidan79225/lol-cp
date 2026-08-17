"""分層依賴方向的機械化驗證。

原本是計畫 Task 13 Step 6 的手動 AST 掃描片段，只在有人記得跑時才執行；
升格為常駐測試後每次 pytest 都強制執行。

規則（主 spec §4.1）：
  domain      不得 import application / infrastructure / presentation
  application 不得 import infrastructure / presentation
（presentation 只能被 main.py import —— 由 test_composition_root 守著。）
"""

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).parent.parent.parent / "src" / "lolcp"

LAYER_RULES = [
    ("domain", ("infrastructure", "application", "presentation")),
    ("application", ("infrastructure", "presentation")),
]


def imported_targets(tree: ast.AST):
    """萃取所有 import 目標 —— 含 ImportFrom 的模組與 names 兩者。

    只掃 module 會漏掉 `from lolcp import infrastructure` 這種寫法
    （module 是 "lolcp"，違規藏在 name 裡）。
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


@pytest.mark.parametrize("layer,forbidden", LAYER_RULES, ids=lambda x: x if isinstance(x, str) else "")
def test_layer_never_imports_outward(layer, forbidden):
    paths = list((SRC / layer).rglob("*.py"))
    assert paths, f"掃描不到 {layer} 的任何檔案 —— 路徑錨定失效，測試在空轉"
    offenders = [
        f"{path}: {target}"
        for path in paths
        for target in imported_targets(ast.parse(path.read_text(encoding="utf-8")))
        if any(x in target for x in forbidden)
    ]
    assert offenders == [], f"違反依賴方向：{offenders}"
