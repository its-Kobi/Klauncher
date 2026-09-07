from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QLineEdit, QMessageBox
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
import urllib.request
from pathlib import Path

class BrowsePage(QWidget):
    """Generic Modrinth browse for mod/resourcepack/shader/datapack with version/loader filtering and drag to instance tiles"""
    def __init__(self, instance, project_type="mod", title="Browse", parent=None):
        super().__init__(parent)
        self.instance=instance
        self.ptype=project_type
        lay=QVBoxLayout(self)
        # Vanilla gating
        if project_type=="mod" and instance.loader=="vanilla":
            msg=QLabel("This instance has no mod loader installed. Install Fabric/Forge/Quilt first to use mods.")
            msg.setWordWrap(True)
            lay.addWidget(msg)
            btn=QPushButton("Install Loader")
            btn.clicked.connect(self._install_loader)
            lay.addWidget(btn)
            lay.addStretch()
            return
        if project_type=="shader" and instance.loader=="vanilla":
            # check if optifine? allow if instance has optifine loader else block
            if instance.loader not in ("optifine",):
                msg=QLabel("Shader packs require a shader-compatible setup (Iris/OptiFine or Fabric/Forge with Iris). Vanilla without a loader may not support shaders.")
                msg.setWordWrap(True)
                lay.addWidget(msg)
                # still allow browsing but warn
        # existing files list
        folder_map={"mod":"mods","resourcepack":"resourcepacks","shader":"shaderpacks","datapack":"datapacks"}
        self.folder = folder_map.get(project_type,"mods")
        self.list_label=QLabel(f"Installed {title}:")
        lay.addWidget(self.list_label)
        self.file_list=QListWidget()
        lay.addWidget(self.file_list,1)
        self.refresh_files()
        # search row
        lay.addWidget(QLabel(f"Browse {title} on Modrinth (filtered to {instance.version_id} / {instance.loader}):"))
        srow=QHBoxLayout()
        self.search_edit=QLineEdit(); self.search_edit.setPlaceholderText(f"Search {title}...")
        sbtn=QPushButton("Search"); sbtn.clicked.connect(self._search)
        sbtn.setIcon(self._icon("search"))
        srow.addWidget(self.search_edit,1); srow.addWidget(sbtn)
        lay.addLayout(srow)
        self.results=QListWidget()
        self.results.setMaximumHeight(220)
        self.results.setDragEnabled(True)
        self.results.setDragDropMode(QListWidget.DragOnly)
        self.results.setIconSize(QSize(24,24))
        lay.addWidget(self.results)
        self.results.itemDoubleClicked.connect(self._install_result)
        # drag mime
        self.results.startDrag = self._start_drag
        # show top on open — not just search
        from PySide6.QtCore import QTimer
        QTimer.singleShot(120, lambda: self._search(top=True))

    def _icon(self, act):
        from launcher.icons import get_action_icon
        return get_action_icon(act, self)

    def _install_loader(self):
        QMessageBox.information(self,"Loader","Create a new instance with Fabric/Forge/Quilt, or edit Version tab to add a loader.")

    def refresh_files(self):
        if not hasattr(self,'file_list'): return
        self.file_list.clear()
        p=self.instance.game_dir / self.folder
        if not p.exists(): return
        for f in p.iterdir():
            if f.is_file():
                self.file_list.addItem(f.name)

    def _search(self, top=False):
        q=self.search_edit.text().strip() if not top else ""
        # empty q with top=True -> show top trending (like modpacks dialog)
        from launcher.modplatform.modrinth import search_mods
        from launcher.version_metadata import _parse_minecraft_version
        parsed=_parse_minecraft_version(self.instance.version_id)
        mc = f"{parsed[0]}.{parsed[1]}.{parsed[2]}" if parsed and parsed[2] else (f"{parsed[0]}.{parsed[1]}" if parsed else None)
        loader = self.instance.loader if self.instance.loader in ("fabric","forge","quilt") else None
        if self.ptype in ("resourcepack","datapack"):
            loader=None
        # for top list, don't filter by mc to get popular
        search_q = q if q else ""
        search_mc = mc if q else None
        try:
            hits=search_mods(search_q, categories=loader or "fabric", limit=15, mc_version=search_mc, project_type=self.ptype)
            if not hits and search_mc:
                hits=search_mods(search_q, categories=loader if self.ptype in ("mod","shader") else None, limit=15, mc_version=None, project_type=self.ptype)
            if not hits and search_q:
                hits=search_mods(search_q, categories=None, limit=15, mc_version=None, project_type=self.ptype)
        except Exception as e:
            try:
                hits=search_mods(search_q, categories=None, limit=15, mc_version=None, project_type=self.ptype)
            except Exception as e2:
                QMessageBox.warning(self,"Search",str(e2)); return
        self.results.clear()
        if not hits:
            self.results.addItem("No results — try broader query")
            return
        for h in hits:
            if not isinstance(h, dict): continue
            item=QListWidgetItem(f"{h.get('title','?')} — {h.get('description','')[:50]}  [{h.get('downloads',0)} dl]")
            # small Modrinth icon
            icon_url=h.get("icon_url")
            if icon_url:
                try:
                    req=urllib.request.Request(icon_url, headers={"User-Agent":"KLauncher/1.0"})
                    data=urllib.request.urlopen(req, timeout=6).read()
                    pm=QPixmap(); pm.loadFromData(data)
                    if not pm.isNull():
                        item.setIcon(QIcon(pm.scaled(24,24, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                except: pass
            item.setData(Qt.UserRole, h)
            self.results.addItem(item)

    def _install_result(self, item):
        proj=item.data(Qt.UserRole)
        # placeholder has no data -> ignore
        if not proj or isinstance(proj, str) and proj.startswith("No results"):
            return
        # handle stringified dict
        if isinstance(proj, str):
            try:
                import json
                proj=json.loads(proj)
            except:
                QMessageBox.warning(self,"Error","Invalid mod data"); return
        self._do_install(proj)

    def _do_install(self, proj):
        if not proj or (isinstance(proj, str) and proj.startswith("No results")):
            return
        if isinstance(proj, str):
            try:
                import json
                proj=json.loads(proj)
            except:
                QMessageBox.warning(self,"Error",f"Invalid data: {str(proj)[:100]}"); return
        if not isinstance(proj, dict):
            QMessageBox.warning(self,"Error","Invalid data"); return
        from launcher.modplatform.modrinth import check_compat, get_project_versions, download_version_file
        try:
            ok,msg=check_compat(proj, self.instance)
        except Exception as e:
            QMessageBox.warning(self,"Check",str(e)); return
        if not ok:
            QMessageBox.warning(self,"Incompatible",msg); return
        if "Warning" in msg:
            if QMessageBox.question(self,"Warning",msg+"\nInstall anyway?")!=QMessageBox.Yes:
                return
        from launcher.version_metadata import _parse_minecraft_version
        parsed=_parse_minecraft_version(self.instance.version_id)
        mc = f"{parsed[0]}.{parsed[1]}.{parsed[2]}" if parsed and parsed[2] else (f"{parsed[0]}.{parsed[1]}" if parsed else None)
        loader = self.instance.loader if self.instance.loader in ("fabric","forge","quilt") else None
        if self.ptype in ("resourcepack","datapack"):
            loader=None
        try:
            vers=get_project_versions(proj["project_id"], loaders=[loader] if loader else None, game_versions=[mc] if mc else None)
            if not vers and mc:
                # strict version required - do NOT fallback to wrong MC, show error instead
                QMessageBox.warning(self,"No compatible version", f"No {proj.get('title','mod')} version for {mc} + {loader or 'any loader'}.\nThis instance is {self.instance.version_id} [{self.instance.loader}].\nTry a different mod version or update the instance MC version.")
                return
        except Exception as e:
            QMessageBox.warning(self,"Error",str(e)); return
        if not vers:
            QMessageBox.warning(self,"","No compatible versions for this instance"); return
        from launcher.modplatform.modrinth import pick_best_version
        v=pick_best_version(vers, mc, loader)
        if not v:
            QMessageBox.warning(self,"","No suitable version found"); return
        # diff preview with actual filename + MC
        from launcher.moddiff import diff_mods
        fn=v.get("files",[{}])[0].get("filename","?")
        old=[(self.file_list.item(i).text(),"") for i in range(self.file_list.count())]
        preview_new=old+[(proj["title"]+f" ({fn} for {mc})","new")]
        added,removed,bumped=diff_mods(old, preview_new)
        if added:
            from PySide6.QtWidgets import QDialog, QTextEdit, QDialogButtonBox
            d=QDialog(self); d.setWindowTitle("Update Preview — Diff"); lay2=QVBoxLayout(d)
            txt=QTextEdit(); txt.setReadOnly(True)
            lines=[f"+ Add {n}" for n,_ in added] + [f"- Remove {n}" for n,_ in removed] + [f"~ Bump {n}" for n,_,_ in bumped]
            txt.setText("\n".join(lines)+f"\n\nTarget: {self.instance.version_id} [{self.instance.loader}] → {mc} + {loader or 'any'}")
            lay2.addWidget(QLabel(f"Installing {proj['title']} ({v.get('version_number','')}) for {mc}:"))
            lay2.addWidget(txt)
            bb=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); lay2.addWidget(bb)
            d.resize(460,280)
            if d.exec()!=QDialog.Accepted: return
        try:
            dest_dir=self.instance.game_dir / self.folder
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest=download_version_file(v, dest_dir)
            QMessageBox.information(self,"Installed",f"Installed {dest.name} → {self.folder}/")
            self.refresh_files()
        except Exception as e:
            QMessageBox.warning(self,"Download",str(e))

    def _start_drag(self, actions):
        from PySide6.QtGui import QDrag
        from PySide6.QtCore import QMimeData
        item=self.results.currentItem()
        if not item: return
        proj=item.data(Qt.UserRole)
        if not proj: return
        mime=QMimeData()
        # encode project for drop onto instance tile
        import json
        mime.setText(f"modrinth:{proj['project_id']}:{self.ptype}")
        # also store full for fallback
        mime.setData("application/x-modrinth", json.dumps(proj).encode())
        drag=QDrag(self.results)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)
