from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem, QLineEdit, QMessageBox, QFileDialog
from PySide6.QtCore import Qt, QSize
from launcher.mods.manager import ModManager
from launcher.modplatform.modrinth import search_mods, get_project_versions, download_version_file, check_compat

class ModsPage(QWidget):
    def __init__(self, instance, parent=None):
        super().__init__(parent)
        self.instance=instance
        self.manager=ModManager(instance)
        lay=QVBoxLayout(self)
        lay.addWidget(QLabel(f"Mods for {instance.name} - {instance.version_id}"))
        self.list=QListWidget()
        lay.addWidget(self.list,1)
        btns=QHBoxLayout()
        add=QPushButton("Add JAR")
        from launcher.icons import get_action_icon
        add.setIcon(get_action_icon("import"))
        tog=QPushButton("Toggle")
        tog.setIcon(get_action_icon("refresh"))
        dele=QPushButton("Delete")
        dele.setIcon(get_action_icon("delete"))
        diff_btn=QPushButton("Preview Diff")
        diff_btn.setIcon(get_action_icon("diff"))
        diff_btn.clicked.connect(self._preview_diff)
        btns.addWidget(add); btns.addWidget(tog); btns.addWidget(dele); btns.addWidget(diff_btn); btns.addStretch()
        lay.addLayout(btns)
        # Modrinth search
        lay.addWidget(QLabel("Modrinth Search (Fabric/Forge aware):"))
        srow=QHBoxLayout()
        self.search_edit=QLineEdit()
        self.search_edit.setPlaceholderText("Search mods...")
        sbtn=QPushButton("Search")
        sbtn.clicked.connect(self._search)
        srow.addWidget(self.search_edit,1); srow.addWidget(sbtn)
        lay.addLayout(srow)
        self.results=QListWidget()
        self.results.setMaximumHeight(220)
        self.results.setIconSize(QSize(24,24))
        lay.addWidget(self.results)
        self.results.itemDoubleClicked.connect(self._install_result)
        self.refresh()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(150, lambda: self._search(top=True))

    def refresh(self):
        self.list.clear()
        for mod in self.manager.list_mods():
            item=QListWidgetItem(f"{'[x]' if mod.enabled else '[ ]'} {mod.name}")
            item.setData(Qt.UserRole, mod)
            self.list.addItem(item)

    def _add(self):
        fp,_=QFileDialog.getOpenFileName(self,"Pick JAR","", "JAR (*.jar)")
        if fp:
            from pathlib import Path
            ok,msg=self.manager.check_compat(Path(fp).name, self.instance)
            if not ok:
                QMessageBox.warning(self,"Incompatible",msg)
                return
            self.manager.add_from_path(Path(fp))
            self.refresh()

    def _toggle(self):
        item=self.list.currentItem()
        if not item: return
        mod=item.data(Qt.UserRole)
        self.manager.set_enabled(mod, not mod.enabled)
        self.refresh()

    def _del(self):
        item=self.list.currentItem()
        if not item: return
        mod=item.data(Qt.UserRole)
        self.manager.delete(mod)
        self.refresh()

    def _search(self, top=False):
        q=self.search_edit.text().strip() if not top else ""
        from launcher.version_metadata import _parse_minecraft_version
        parsed=_parse_minecraft_version(self.instance.version_id)
        mc = f"{parsed[0]}.{parsed[1]}.{parsed[2]}" if parsed and parsed[2] else (f"{parsed[0]}.{parsed[1]}" if parsed else None)
        loader=self.instance.loader if self.instance.loader in ("fabric","forge","quilt") else None
        search_q=q if q else ""
        search_mc=mc if q else None
        try:
            hits=search_mods(search_q, categories=loader or "fabric", limit=15, mc_version=search_mc, project_type="mod")
            if not hits and search_mc:
                hits=search_mods(search_q, categories=loader or "fabric", limit=15, mc_version=None, project_type="mod")
            if not hits and search_q:
                hits=search_mods(search_q, categories=None, limit=15, mc_version=None, project_type="mod")
        except Exception as e:
            try:
                hits=search_mods(search_q, categories=None, limit=15, mc_version=None, project_type="mod")
            except Exception as e2:
                QMessageBox.warning(self,"Search",str(e2)); return
        self.results.clear()
        if not hits:
            it=QListWidgetItem("No results — try broader query"); it.setFlags(it.flags() & ~Qt.ItemIsEnabled); self.results.addItem(it); return
        import urllib.request as _ur
        from PySide6.QtGui import QPixmap, QIcon
        for h in hits:
            if not isinstance(h, dict): continue
            item=QListWidgetItem(f"{h.get('title','?')} — {h.get('description','')[:50]}  [{h.get('downloads',0)} dl]")
            icon_url=h.get("icon_url")
            if icon_url:
                try:
                    req=_ur.Request(icon_url, headers={"User-Agent":"KLauncher/1.0"})
                    data=_ur.urlopen(req, timeout=6).read()
                    pm=QPixmap(); pm.loadFromData(data)
                    if not pm.isNull():
                        item.setIcon(QIcon(pm.scaled(24,24, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                except: pass
            item.setData(Qt.UserRole, h)
            self.results.addItem(item)

    def _install_result(self, item):
        proj=item.data(Qt.UserRole)
        if not proj or (isinstance(proj, str) and proj.startswith("No results")):
            return
        if isinstance(proj, str):
            try:
                import json
                proj=json.loads(proj)
            except:
                QMessageBox.warning(self,"Error",f"Invalid mod data: {str(proj)[:100]}"); return
        if not isinstance(proj, dict):
            QMessageBox.warning(self,"Error","Invalid mod data"); return
        # ensure required keys
        if "project_id" not in proj or "title" not in proj:
            # try fallback: maybe hits dict uses project_id differently
            try:
                proj["project_id"]=proj.get("project_id") or proj.get("id")
            except: pass
        ok,msg=check_compat(proj, self.instance)
        if not ok:
            QMessageBox.warning(self,"Incompatible",msg)
            return
        if "Warning" in msg:
            if QMessageBox.question(self,"Warning",msg+"\nInstall anyway?")!=QMessageBox.Yes:
                return
        try:
            from launcher.version_metadata import _parse_minecraft_version
            parsed=_parse_minecraft_version(self.instance.version_id)
            mc = f"{parsed[0]}.{parsed[1]}.{parsed[2]}" if parsed and parsed[2] else (f"{parsed[0]}.{parsed[1]}" if parsed else None)
            loader=self.instance.loader if self.instance.loader in ("fabric","forge","quilt") else None
            vers=get_project_versions(proj["project_id"], loaders=[loader] if loader else None, game_versions=[mc] if mc else None)
            if not vers and mc:
                QMessageBox.warning(self,"No compatible version", f"No {proj.get('title','mod')} version for {mc} + {loader or 'any'}.\nInstance is {self.instance.version_id} [{self.instance.loader}]."); return
        except Exception as e:
            QMessageBox.warning(self,"Error",str(e)); return
        if not vers:
            QMessageBox.warning(self,"","No compatible versions for this instance (try different version)"); return
        from launcher.modplatform.modrinth import pick_best_version
        ver=pick_best_version(vers, mc, loader)
        try:
            from launcher.moddiff import diff_mods
            old=[(m.name,"") for m in self.manager.list_mods()]
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit
            preview_old=list(old)
            fn=ver.get("files",[{}])[0].get("filename","?") if ver else "?"
            preview_new=preview_old+[(proj.get("title","?")+f" ({fn} for {mc})","new")]
            added,removed,bumped=diff_mods(preview_old, preview_new)
            if added or removed or bumped:
                d=QDialog(self); d.setWindowTitle("Update Preview — Diff")
                lay2=QVBoxLayout(d)
                txt=QTextEdit(); txt.setReadOnly(True)
                lines=[]
                for n,vv in added: lines.append(f"+ Add {n} {vv}")
                for n,vv in removed: lines.append(f"- Remove {n} {vv}")
                for n,a,b in bumped: lines.append(f"~ Bump {n} {a} → {b}")
                txt.setText("\n".join(lines) if lines else "No changes")
                lay2.addWidget(QLabel(f"Installing {proj.get('title','?')} ({ver.get('version_number','')} for {mc}) will:"))
                lay2.addWidget(txt)
                from PySide6.QtWidgets import QDialogButtonBox
                bb=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); lay2.addWidget(bb)
                d.resize(460,280)
                if d.exec()!=QDialog.Accepted:
                    return
            dest=download_version_file(ver, self.manager.mods_dir())
            QMessageBox.information(self,"Installed",f"Installed {dest.name}")
            self.refresh()
        except Exception as e:
            import traceback
            QMessageBox.warning(self,"Download",str(e)+"\n"+traceback.format_exc()[:500])

    def _preview_diff(self):
        # simple diff of current vs file system after hypothetical update
        from launcher.moddiff import diff_mods
        mods=[(m.name, "") for m in self.manager.list_mods()]
        # fake: no pending update, show empty
        added,removed,bumped=diff_mods(mods, mods)
        msg="No pending changes. Use Modrinth search to install and preview diff before confirming." if not added else str(added)
        QMessageBox.information(self,"Diff Preview", msg)
