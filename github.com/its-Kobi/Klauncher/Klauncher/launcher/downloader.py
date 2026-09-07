import hashlib
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QFile, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

class Downloader(QObject):
    """Asynchronous file downloader with retries, timeout, and SHA1 verification."""

    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.current_reply: Optional[QNetworkReply] = None
        self.current_file: Optional[QFile] = None
        self.destination: Optional[Path] = None
        self.expected_sha1: Optional[str] = None
        self.retries = 3
        self.timeout_ms = 15000
        self._cancelled = False

    def download(self, url: str, destination: Path,
                 expected_sha1: Optional[str] = None,
                 retries: int = 3, timeout_ms: int = 15000) -> None:
        self.destination = destination
        self.expected_sha1 = expected_sha1
        self.retries = retries
        self.timeout_ms = timeout_ms
        self._cancelled = False
        self._start_request(url, destination)

    def cancel(self) -> None:
        self._cancelled = True
        if self.current_reply:
            self.current_reply.abort()

    def _start_request(self, url: str, destination: Path) -> None:
        self.current_file = QFile(str(destination))
        if not self.current_file.open(QFile.WriteOnly):
            self.error.emit(f"Cannot open file for writing: {destination}")
            return

        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(self.timeout_ms)
        self.current_reply = self.manager.get(request)
        self.current_reply.downloadProgress.connect(self._on_download_progress)
        self.current_reply.readyRead.connect(self._on_ready_read)
        # Connect without passing reply argument
        self.current_reply.finished.connect(self._on_reply_finished)

    def _on_ready_read(self) -> None:
        if self.current_reply and self.current_file:
            self.current_file.write(self.current_reply.readAll())

    def _on_download_progress(self, bytes_received: int, bytes_total: int) -> None:
        if bytes_total > 0:
            percent = int((bytes_received / bytes_total) * 100)
            self.progress.emit(percent)

    def _on_reply_finished(self) -> None:
        reply = self.current_reply
        if not reply:
            return

        if self._cancelled:
            self._cleanup()
            self.error.emit("Download cancelled")
            return

        if reply.error() != QNetworkReply.NoError:
            err_str = reply.errorString()
            self._cleanup()
            if self.retries > 0:
                self.retries -= 1
                url = reply.url().toString()
                self._start_request(url, self.destination)
            else:
                self.error.emit(f"Download failed: {err_str}")
            return

        if self.current_file:
            self.current_file.close()

        if self.expected_sha1:
            if not self._verify_sha1(self.destination, self.expected_sha1):
                self._cleanup()
                self.error.emit("SHA1 hash verification failed")
                return

        self._cleanup()
        self.finished.emit(str(self.destination))

    def _cleanup(self) -> None:
        if self.current_file:
            self.current_file.close()
            self.current_file = None
        if self.current_reply:
            self.current_reply.deleteLater()
            self.current_reply = None

    @staticmethod
    def _verify_sha1(file_path: Path, expected_sha1: str) -> bool:
        sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha1.update(chunk)
        return sha1.hexdigest() == expected_sha1