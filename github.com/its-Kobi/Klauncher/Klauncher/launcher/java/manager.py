from __future__ import annotations
from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import QObject, Signal, QThread
from launcher.java_detector import JavaInstallation, discover_java_installations, get_java_version, parse_java_major
from launcher.java.matcher import java_compatible, required_java_for_version
from launcher.java.downloader import JavaDownloadWorker
from launcher import paths

class JavaManager(QObject):
    javas_changed = Signal(list)
    detection_finished = Signal(list)
    download_progress = Signal(int)
    download_status = Signal(str)
    download_finished = Signal(str)
    download_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._installs: List[JavaInstallation] = []
        self._worker = None
        self._dl_worker: Optional[JavaDownloadWorker] = None

    def detect(self, use_cache=False):
        from launcher.java_detector import discover_java_installations as disc
        # include auto-downloaded
        extra = []
        java_dir = paths.get_data_dir() / "java"
        if java_dir.exists():
            for exe in java_dir.rglob("java.exe"):
                extra.append(str(exe))
        installs = disc(extra_paths=extra if extra else None, use_cache=False)
        self._installs = installs
        self.detection_finished.emit(installs)
        self.javas_changed.emit(installs)
        return installs

    def list(self) -> List[JavaInstallation]:
        if not self._installs:
            self.detect()
        return list(self._installs)

    def add_manual(self, path: str) -> Optional[JavaInstallation]:
        p = Path(path)
        if not p.exists():
            return None
        ver = get_java_version(str(p))
        maj = parse_java_major(ver)
        inst = JavaInstallation(path=str(p.resolve()), version_string=ver or "", major=maj)
        # persist in config
        try:
            from launcher import paths as pp
            import json
            cfg = pp.get_data_dir() / "config.json"
            data = {}
            if cfg.exists():
                data = json.loads(cfg.read_text(encoding="utf-8"))
            manual = data.get("manual_java_paths", [])
            if str(p.resolve()) not in manual:
                manual.append(str(p.resolve()))
                data["manual_java_paths"] = manual
                cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except:
            pass
        self._installs.append(inst)
        self.javas_changed.emit(self._installs)
        return inst

    def find_compatible(self, required: int) -> Optional[JavaInstallation]:
        for j in self.list():
            if java_compatible(j.major, required):
                # prefer exact match first
                if j.major == required:
                    return j
        for j in self.list():
            if java_compatible(j.major, required):
                return j
        return None

    def download_java(self, required: int):
        if self._dl_worker and self._dl_worker.isRunning():
            return
        self._dl_worker = JavaDownloadWorker(required)
        self._dl_worker.progress.connect(self.download_progress)
        self._dl_worker.status.connect(self.download_status)
        self._dl_worker.succeeded.connect(self._on_dl_ok)
        self._dl_worker.failed.connect(self.download_failed)
        self._dl_worker.start()

    def _on_dl_ok(self, exe_path: str):
        self.detect()
        self.download_finished.emit(exe_path)

    def cancel_download(self):
        if self._dl_worker:
            self._dl_worker.cancel()

    def validate_for_launch(self, required: int, chosen_path: Optional[str]) -> tuple[bool, str]:
        if not chosen_path:
            compat = self.find_compatible(required)
            if compat:
                return True, ""
            return False, f"This instance requires Java {required}. No compatible Java found. Click 'Download Java {required}'."
        # check chosen path major
        ver = get_java_version(chosen_path)
        maj = parse_java_major(ver)
        if java_compatible(maj, required):
            return True, ""
        return False, f"Selected Java {maj or 'unknown'} ({ver or chosen_path}) is not compatible with required Java {required}. Please select Java {required}+ or download it."
