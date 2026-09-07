from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QMessageBox
from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtGui import QPixmap, QIcon
import urllib.request, json

class ModpackDialog(QDialog):
    def __init__(self, parent, core):
        super().__init__(parent)
        self.core=core
        self.setWindowTitle("Get A Modpack — Modrinth")
        self.resize(620,520)
        self.selected=None
        lay=QVBoxLayout(self)
        title=QLabel("Modpacks — Top 20 + search any Modrinth pack"); title.setObjectName("pageSub"); lay.addWidget(title)
        srow=QHBoxLayout()
        self.search=QLineEdit(); self.search.setPlaceholderText("Search modpacks...")
        btn=QPushButton("Search"); btn.clicked.connect(self._search)
        srow.addWidget(self.search,1); srow.addWidget(btn)
        lay.addLayout(srow)
        self.list=QListWidget(); self.list.setIconSize(QSize(40,40))
        lay.addWidget(self.list,1)
        self.list.itemDoubleClicked.connect(lambda it: self._install(it))
        row=QHBoxLayout()
        install=QPushButton("Install Selected"); install.clicked.connect(lambda: self._install(self.list.currentItem()))
        close=QPushButton("Close"); close.clicked.connect(self.reject)
        row.addStretch(); row.addWidget(install); row.addWidget(close)
        lay.addLayout(row)
        self._search("") # top

    def _search(self, _checked=None):
        query=self.search.text().strip()
        self.list.clear()
        self.list.addItem("Loading...")
        class W(QThread):
            done=Signal(list)
            def __init__(self, q): super().__init__(); self.q=q
            def run(self):
                try:
                    from launcher.modplatform.modrinth import search_mods
                    # empty query => top packs
                    hits=search_mods(self.q, categories=None, limit=20, mc_version=None, project_type="modpack")
                    self.done.emit(hits)
                except Exception as e:
                    self.done.emit([])
        # if empty, search top
        w=W(query); w.done.connect(self._on_results); w.start(); self._w=w

    def _on_results(self, hits):
        self.list.clear()
        if not hits:
            self.list.addItem("No modpacks found")
            return
        for h in hits:
            title=h.get("title","?")
            desc=h.get("description","")[:60]
            item=QListWidgetItem(f"{title}  —  {desc}  [{h.get('downloads',0)} dl]")
            item.setData(Qt.UserRole, h)
            # icon async
            icon_url=h.get("icon_url")
            if icon_url:
                try:
                    req=urllib.request.Request(icon_url, headers={"User-Agent":"KLauncher/1.0"})
                    data=urllib.request.urlopen(req, timeout=8).read()
                    pm=QPixmap(); pm.loadFromData(data)
                    if not pm.isNull():
                        item.setIcon(QIcon(pm.scaled(40,40, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                except: pass
            self.list.addItem(item)

    def _install(self, item):
        if not item: return
        h=item.data(Qt.UserRole)
        if not h or not isinstance(h, dict): return
        # fetch best version for pack
        try:
            from launcher.modplatform.modrinth import get_project_versions, download_version_file
            pid=h.get("project_id")
            # pick latest version (modpacks not loader-specific)
            vers=get_project_versions(pid, loaders=None, game_versions=None)
            if not vers:
                QMessageBox.warning(self,"","No versions for this pack"); return
            ver=vers[0]
            # game version from ver
            gvs=ver.get("game_versions",[])
            mc=gvs[0] if gvs else "1.21.1"
            # create data for instance creation
            self.selected={
                "name": h.get("title","Modpack"),
                "version_id": mc,
                "loader": "vanilla", # modpack may bring its own loader via pack file; keep vanilla base for now
                "loader_version": None,
                "mc_version": mc,
                "group": "",
                "modpack": True,
                "pack_id": pid,
                "pack_version": ver,
                "pack_hit": h,
                "icon_url": h.get("icon_url")
            }
            self.accept()
        except Exception as e:
            QMessageBox.warning(self,"Install failed", str(e))

    def get_selected(self):
        return self.selected
