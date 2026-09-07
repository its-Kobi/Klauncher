from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from launcher import paths

class SkinCache(QObject):
    fetched = Signal(str, object)  # uuid, pixmap or None
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.manager.finished.connect(self._on_finished)
        self._pending = {}  # reply -> uuid
        self.cache_dir = paths.get_data_dir() / "cache" / "skins"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(self, uuid: str) -> Path:
        clean = uuid.replace("-","").lower()
        return self.cache_dir / f"{clean}.png"

    def get_cached(self, uuid: str) -> QPixmap | None:
        p = self.cache_path(uuid)
        if p.is_file():
            pm = QPixmap(str(p))
            if not pm.isNull():
                return pm
        return None

    def request(self, uuid: str, username: str):
        clean = uuid.replace("-","").lower() if uuid else ""
        cached = self.get_cached(uuid) if clean else None
        if cached:
            self.fetched.emit(uuid, cached)
            return
        # Try crafatar avatar (already head) - lightweight
        urls = []
        if clean:
            urls.append(f"https://crafatar.com/avatars/{clean}?size=64&overlay")
            urls.append(f"https://crafatar.com/renders/body/{clean}?overlay")
        if username:
            urls.append(f"https://minotar.net/avatar/{username}/64.png")
        if not urls:
            self.fetched.emit(uuid, None)
            return
        url = urls[0]
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", b"KLauncher/1.0")
        reply = self.manager.get(req)
        self._pending[reply] = (uuid, urls[1:] if len(urls)>1 else [])

    def _on_finished(self, reply: QNetworkReply):
        info = self._pending.pop(reply, None)
        if info is None:
            reply.deleteLater()
            return
        uuid, remaining = info
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pm = QPixmap()
            if pm.loadFromData(data):
                # save to cache
                try:
                    pm.save(str(self.cache_path(uuid)), "PNG")
                except:
                    pass
                self.fetched.emit(uuid, pm)
                reply.deleteLater()
                return
        # try next url
        if remaining:
            nxt = remaining[0]
            req = QNetworkRequest(QUrl(nxt))
            req.setRawHeader(b"User-Agent", b"KLauncher/1.0")
            r2 = self.manager.get(req)
            self._pending[r2] = (uuid, remaining[1:])
        else:
            self.fetched.emit(uuid, None)
        reply.deleteLater()

_global_cache: SkinCache | None = None
def get_skin_cache(parent=None) -> SkinCache:
    global _global_cache
    if _global_cache is None:
        _global_cache = SkinCache(parent)
    return _global_cache
