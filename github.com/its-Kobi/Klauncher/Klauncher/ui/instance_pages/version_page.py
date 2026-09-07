from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QDialog, QFormLayout, QComboBox, QLineEdit, QMessageBox, QHBoxLayout, QCheckBox
from PySide6.QtCore import Signal

class NewInstanceDialog(QDialog):
    def __init__(self, parent, core):
        super().__init__(parent)
        self.core = core
        self.setWindowTitle("Add Instance")
        self.resize(460,340)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit("My Instance")
        self.group_edit = QLineEdit("")
        self.loader_combo = QComboBox()
        for k,v in [("vanilla","Vanilla"),("fabric","Fabric"),("forge","Forge"),("quilt","Quilt"),("optifine","OptiFine"),("custom","Custom")]:
            self.loader_combo.addItem(v,k)
        self.mc_combo = QComboBox()
        self.loader_ver_combo = QComboBox()
        self.auto_check = QCheckBox("Auto pick best loader version"); self.auto_check.setChecked(True)
        form.addRow("Name:", self.name_edit)
        form.addRow("Group:", self.group_edit)
        form.addRow("Loader:", self.loader_combo)
        form.addRow("MC Version:", self.mc_combo)
        form.addRow("Loader Version:", self.loader_ver_combo)
        form.addRow("", self.auto_check)
        lay.addLayout(form)
        self.status = QLabel("")
        lay.addWidget(self.status)
        btn_row=QHBoxLayout()
        self.modpack_btn=QPushButton("Get A Modpack"); self.modpack_btn.clicked.connect(self._open_modpack)
        btn_row.addWidget(self.modpack_btn); btn_row.addStretch()
        lay.addLayout(btn_row)
        btn = QPushButton("Create")
        btn.clicked.connect(self._create)
        lay.addWidget(btn)
        self.loader_combo.currentIndexChanged.connect(self._load_mc)
        self.mc_combo.currentIndexChanged.connect(self._load_loader)
        self.auto_check.toggled.connect(lambda c: self.loader_ver_combo.setEnabled(not c))
        self._load_mc()

    def _open_modpack(self):
        from ui.dialogs.modpack_dialog import ModpackDialog
        dlg=ModpackDialog(self, self.core)
        if dlg.exec()==QDialog.Accepted:
            data=dlg.get_selected()
            if data:
                # create instance directly via modpack data
                self._modpack_data=data
                self.accept()

    def _load_mc(self):
        loader = self.loader_combo.currentData()
        self.mc_combo.clear()
        self.loader_ver_combo.clear()
        self.status.setText("Fetching MC versions...")
        from PySide6.QtCore import QThread, Signal
        class W(QThread):
            done=Signal(list)
            def __init__(self, l): super().__init__(); self.l=l
            def run(self):
                try:
                    from launcher.providers.registry import get_provider
                    self.done.emit(get_provider(self.l).fetch_minecraft_versions())
                except: self.done.emit([])
        w=W(loader)
        w.done.connect(lambda vers: (self.mc_combo.addItems(vers[:100]), self.status.setText(f"{len(vers)} versions")) )
        w.start()
        self._w=w

    def _load_loader(self):
        loader=self.loader_combo.currentData()
        if loader not in ("fabric","quilt","forge"): 
            self.loader_ver_combo.setVisible(loader in ("fabric","quilt","forge"))
            self.auto_check.setVisible(loader in ("fabric","quilt","forge"))
            return
        self.loader_ver_combo.setVisible(True); self.auto_check.setVisible(True)
        mc=self.mc_combo.currentText()
        if not mc: return
        self.loader_ver_combo.clear()
        self.status.setText("Fetching loader versions (auto best)...")
        from PySide6.QtCore import QThread, Signal
        class W(QThread):
            done=Signal(list)
            def __init__(self,l,mc): super().__init__(); self.l=l; self.mc=mc
            def run(self):
                try:
                    from launcher.providers.registry import get_provider
                    self.done.emit(get_provider(self.l).fetch_loader_versions(self.mc))
                except: self.done.emit([])
        w=W(loader,mc)
        def on_done(vers):
            self.loader_ver_combo.addItems(vers[:30])
            if vers and self.auto_check.isChecked():
                self.loader_ver_combo.setCurrentIndex(0)
                self.status.setText(f"Auto-picked {vers[0]} for {mc}")
            else:
                self.status.setText(f"{len(vers)} loader versions")
        w.done.connect(on_done)
        w.start()
        self._lw=w

    def _create(self):
        if hasattr(self, '_modpack_data') and self._modpack_data:
            self.accept(); return
        if not self.name_edit.text().strip():
            QMessageBox.warning(self,"","Name required"); return
        if not self.mc_combo.currentText():
            QMessageBox.warning(self,"","Pick MC version"); return
        self.accept()

    def get_data(self):
        if hasattr(self, '_modpack_data') and self._modpack_data:
            return self._modpack_data
        loader=self.loader_combo.currentData()
        mc=self.mc_combo.currentText()
        # auto best if checked
        if self.auto_check.isChecked() and loader in ("fabric","quilt","forge"):
            lv=self.loader_ver_combo.itemText(0) if self.loader_ver_combo.count()>0 else self.loader_ver_combo.currentText()
        else:
            lv=self.loader_ver_combo.currentText() if loader in ("fabric","quilt","forge") else None
        version_id = mc if loader=="vanilla" else (f"fabric-loader-{lv}-{mc}" if loader=="fabric" else f"quilt-loader-{lv}-{mc}" if loader=="quilt" else f"forge-{mc}-{lv}" if loader=="forge" else mc)
        return {"name": self.name_edit.text().strip(), "version_id": version_id, "loader": loader, "loader_version": lv, "mc_version": mc, "group": self.group_edit.text().strip()}

class VersionPage(QWidget):
    def __init__(self, instance, parent=None):
        super().__init__(parent)
        self.instance=instance
        lay=QVBoxLayout(self)
        lay.addWidget(QLabel(f"Version: {instance.version_id}"))
        lay.addWidget(QLabel(f"Loader: {instance.loader} {instance.loader_version or ''}"))
        lay.addWidget(QLabel(f"ID: {instance.id}"))
        lay.addStretch()
