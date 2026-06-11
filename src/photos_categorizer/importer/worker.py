import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from photos_categorizer.importer.importer import process_file, scan_folder
from photos_categorizer.tagging.engine import TaggingEngine

_MAX_THREADS = 4


class WorkerSignals(QObject):
    file_done = Signal(object)  # FileResult
    error = Signal(str)


class ImportTask(QRunnable):
    def __init__(self, path: Path, engine: TaggingEngine) -> None:
        super().__init__()
        self.signals = WorkerSignals()
        self._path = path
        self._engine = engine

    def run(self) -> None:
        try:
            result = process_file(self._path, self._engine)
            self.signals.file_done.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(f"{self._path.name}: {exc}")


class ImportSession(QObject):
    """Coordinates a batch import: queues tasks, aggregates signals, tracks completion."""

    file_done = Signal(object)  # FileResult — connect to PhotoImporter.persist + UI update
    error = Signal(str)
    all_finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._total = 0
        self._done = 0
        self._lock = threading.Lock()

    def start(self, folder: Path, engine: TaggingEngine) -> int:
        """Queue all images in folder for import. Returns total file count."""
        paths = scan_folder(folder)
        with self._lock:
            self._total = len(paths)
            self._done = 0

        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(_MAX_THREADS)

        for path in paths:
            task = ImportTask(path, engine)
            task.signals.file_done.connect(self._on_file_done)
            task.signals.error.connect(self._on_error)
            pool.start(task)

        if not paths:
            self.all_finished.emit()

        return len(paths)

    @Slot(object)
    def _on_file_done(self, result: object) -> None:
        self.file_done.emit(result)
        self._advance()

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self.error.emit(msg)
        self._advance()

    def _advance(self) -> None:
        with self._lock:
            self._done += 1
            finished = self._done >= self._total
        if finished:
            self.all_finished.emit()
