"""組裝根 —— 唯一認識所有層的地方。

依賴注入全部發生在這裡。其他任何模組都不得跨層 import。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from lolcp.application.use_cases.list_valuations import ListValuations
from lolcp.application.use_cases.sync_game_data import SyncGameData
from lolcp.domain.diagnostics import Diagnostics
from lolcp.domain.pricing import CanonicalDeriver, LeastSquaresDeriver
from lolcp.domain.valuation import LinearValuation
from lolcp.domain.weights import ResourceRule, WeightResolver
from lolcp.infrastructure.cache.patch_cache import PatchCache
from lolcp.infrastructure.http.fetcher import HttpFetcher
from lolcp.infrastructure.http.patch_gateway import HttpPatchGateway
from lolcp.infrastructure.mapping import ItemMapper
from lolcp.infrastructure.repositories.file_champion_repository import (
    FileChampionRepository,
)
from lolcp.infrastructure.repositories.file_item_repository import FileItemRepository
from lolcp.infrastructure.repositories.toml_config import (
    load_anchors,
    load_champion_overrides,
    load_role_defaults,
)

DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "lol-cp"
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


@dataclass
class AppContext:
    sync: SyncGameData
    diagnostics: Diagnostics
    cache: PatchCache
    config_dir: Path


def build_application(
    cache_root: Path = DEFAULT_CACHE_ROOT, config_dir: Path = CONFIG_DIR
) -> AppContext:
    diagnostics = Diagnostics()
    cache = PatchCache(cache_root)
    gateway = HttpPatchGateway(HttpFetcher(timeout=15.0))
    return AppContext(
        sync=SyncGameData(gateway, cache),
        diagnostics=diagnostics,
        cache=cache,
        config_dir=config_dir,
    )


def build_use_cases(context: AppContext, version: str):
    """資料就緒後才能組裝 —— repository 需要知道版本目錄。"""
    patch_dir = context.cache.dir_for(version)
    diagnostics = context.diagnostics
    items = FileItemRepository(patch_dir, ItemMapper(diagnostics))
    champions = FileChampionRepository(patch_dir, diagnostics)
    list_valuations = ListValuations(
        items=items,
        canonical_deriver=CanonicalDeriver(
            load_anchors(context.config_dir / "anchors.toml"), diagnostics
        ),
        least_squares_deriver=LeastSquaresDeriver(diagnostics),
        weight_resolver=WeightResolver(
            role_defaults=load_role_defaults(context.config_dir / "role_defaults.toml"),
            resource_rule=ResourceRule(diagnostics),
            overrides=load_champion_overrides(context.config_dir / "champions"),
            diagnostics=diagnostics,
        ),
        valuation=LinearValuation(),
    )
    return list_valuations, champions.all_champions()


def main() -> int:
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication, QMessageBox

    from lolcp.presentation.main_window import MainWindow
    from lolcp.presentation.sync_worker import SyncWorker

    app = QApplication(sys.argv)
    context = build_application()

    thread = QThread()
    worker = SyncWorker(context.sync)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)

    window: MainWindow | None = None

    def on_finished(result) -> None:
        nonlocal window
        list_valuations, champions = build_use_cases(context, result.version)
        window = MainWindow(list_valuations, champions, context.diagnostics)
        window.on_sync_finished(result)
        window.refresh_button.clicked.connect(lambda: thread.start())
        window.show()
        thread.quit()

    def on_failed(message: str) -> None:
        QMessageBox.critical(None, "無法載入資料", message)
        thread.quit()
        app.quit()

    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    thread.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
