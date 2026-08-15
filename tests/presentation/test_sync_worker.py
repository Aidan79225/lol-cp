import pytest

from lolcp.application.use_cases.sync_game_data import (
    NoDataAvailableError,
    SyncResult,
)
from lolcp.presentation.sync_worker import SyncWorker

pytestmark = pytest.mark.usefixtures("qapp")


class FakeSync:
    def __init__(self, result=None, error=None):
        self._result = result or SyncResult("16.15.1", offline=False, downloaded=True)
        self._error = error

    def execute(self, on_progress=None):
        if on_progress:
            on_progress(50, 100)
            on_progress(100, 100)
        if self._error:
            raise self._error
        return self._result


def test_worker_forwards_progress_as_a_signal():
    worker = SyncWorker(FakeSync())
    seen: list[tuple[int, int]] = []
    worker.progress.connect(lambda done, total: seen.append((done, total)))
    worker.run()
    assert seen == [(50, 100), (100, 100)]


def test_worker_emits_finished_with_the_sync_result():
    result = SyncResult("16.16.1", offline=True, downloaded=False)
    worker = SyncWorker(FakeSync(result=result))
    received: list[object] = []
    worker.finished.connect(received.append)
    worker.run()
    assert received == [result]


def test_worker_emits_failed_instead_of_raising():
    worker = SyncWorker(FakeSync(error=NoDataAvailableError("無快取")))
    failures: list[str] = []
    worker.failed.connect(failures.append)
    worker.run()  # 不應拋出
    assert failures and "無快取" in failures[0]


def test_worker_does_not_emit_finished_on_failure():
    worker = SyncWorker(FakeSync(error=NoDataAvailableError("boom")))
    received: list[object] = []
    worker.finished.connect(received.append)
    worker.run()
    assert received == []
