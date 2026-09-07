from __future__ import annotations
from PySide6.QtCore import QObject, Signal, QThread, QRunnable, QThreadPool
from typing import Callable, List, Optional

class Task(QObject):
    progress_changed = Signal(int)
    status_changed = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, name: str = ""):
        super().__init__()
        self.name = name
        self._cancelled = False
        self._running = False

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        raise NotImplementedError

    def execute(self):
        self._running = True
        try:
            result = self.run()
            if not self._cancelled:
                self.succeeded.emit(result)
        except Exception as e:
            if not self._cancelled:
                self.failed.emit(str(e))
        finally:
            self._running = False
            self.finished.emit()

class TaskThread(QThread):
    progress_changed = Signal(int)
    status_changed = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished_task = Signal()

    def __init__(self, task: Task):
        super().__init__()
        self.task = task
        task.progress_changed.connect(self.progress_changed)
        task.status_changed.connect(self.status_changed)
        task.succeeded.connect(self.succeeded)
        task.failed.connect(self.failed)
        task.finished.connect(self.finished_task)

    def run(self):
        self.task.execute()

    def cancel(self):
        self.task.cancel()

class SequentialTask(Task):
    def __init__(self, name: str, subtasks: List[Task]):
        super().__init__(name)
        self.subtasks = subtasks

    def run(self):
        total = len(self.subtasks)
        for i, t in enumerate(self.subtasks):
            if self._cancelled:
                raise Exception("Cancelled")
            t.progress_changed.connect(lambda p, idx=i: self.progress_changed.emit(int((idx + p/100)/total*100)))
            t.status_changed.connect(self.status_changed.emit)
            t.run()
            if self._cancelled:
                raise Exception("Cancelled")

class ParallelTask(Task):
    def __init__(self, name: str, subtasks: List[Task], max_threads: int = 4):
        super().__init__(name)
        self.subtasks = subtasks
        self.max_threads = max_threads

    def run(self):
        pool = QThreadPool.globalInstance()
        # Simplified sequential for now with progress aggregation
        total = len(self.subtasks)
        for i, t in enumerate(self.subtasks):
            if self._cancelled:
                break
            t.run()
            self.progress_changed.emit(int((i+1)/total*100))
