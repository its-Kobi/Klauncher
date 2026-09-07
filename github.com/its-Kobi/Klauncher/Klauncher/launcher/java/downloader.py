from __future__ import annotations
import json, urllib.request, urllib.error, zipfile, shutil, os
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from launcher import paths

ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot"

# Map required major -> Temurin feature version
MAJOR_MAP = {8: 8, 16: 16, 17: 17, 21: 21, 25: 25}

class JavaDownloadWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, required_major: int):
        super().__init__()
        self.required_major = required_major
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            major = MAJOR_MAP.get(self.required_major, self.required_major)
            os_name = "windows"
            arch = "x64"
            url = f"{ADOPTIUM_API.format(major=major)}?architecture={arch}&image_type=jre&os={os_name}&page_size=1&sort_order=DESC&vendor=eclipse"
            self.status.emit(f"Querying Adoptium for Java {major} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "KLauncher/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            if not data:
                self.failed.emit(f"No Adoptium build found for Java {major}")
                return
            binary = data[0].get("binary") or {}
            pkg = binary.get("package") or {}
            dl_url = pkg.get("link")
            if not dl_url:
                self.failed.emit("Adoptium response missing download link")
                return
            dest_dir = paths.get_data_dir() / "java" / f"temurin-{major}"
            dest_dir.mkdir(parents=True, exist_ok=True)
            archive = dest_dir / f"openjdk-{major}.zip"
            self.status.emit(f"Downloading Java {major} ...")
            self._download(dl_url, archive)
            if self._cancel:
                self.failed.emit("Cancelled")
                return
            self.status.emit("Extracting ...")
            with zipfile.ZipFile(archive, 'r') as zf:
                zf.extractall(dest_dir)
            archive.unlink(missing_ok=True)
            # find java.exe
            exe = None
            for p in dest_dir.rglob("java.exe"):
                exe = p
                break
            if not exe:
                self.failed.emit("Java executable not found after extract")
                return
            self.progress.emit(100)
            self.succeeded.emit(str(exe.resolve()))
        except Exception as e:
            self.failed.emit(str(e))

    def _download(self, url: str, dest: Path):
        req = urllib.request.Request(url, headers={"User-Agent": "KLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, 'wb') as out:
            total = int(resp.headers.get("Content-Length", 0))
            got = 0
            while True:
                if self._cancel:
                    break
                chunk = resp.read(8192)
                if not chunk:
                    break
                out.write(chunk)
                got += len(chunk)
                if total:
                    self.progress.emit(int(got/total*100))
