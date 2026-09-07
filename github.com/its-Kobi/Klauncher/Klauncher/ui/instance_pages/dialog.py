from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QPushButton, QHBoxLayout, QWidget, QLabel, QTextEdit, QSpinBox, QLineEdit, QFormLayout, QFileDialog, QListWidget
from PySide6.QtCore import Qt
from pathlib import Path
from ui.instance_pages.version_page import VersionPage
from ui.instance_pages.mods_page import ModsPage

class GenericFolderPage(QWidget):
    def __init__(self, instance, folder_name):
        super().__init__()
        from PySide6.QtWidgets import QListWidget
        lay=QVBoxLayout(self)
        self.path = instance.game_dir / folder_name
        self.path.mkdir(parents=True, exist_ok=True)
        lay.addWidget(QLabel(f"{folder_name} - {self.path}"))
        self.list=QListWidget()
        lay.addWidget(self.list,1)
        btn=QPushButton("Open Folder")
        from launcher.icons import get_action_icon
        btn.setIcon(get_action_icon("folder", self))
        btn.clicked.connect(lambda: __import__("PySide6.QtGui", fromlist=["QDesktopServices"]).QDesktopServices.openUrl(__import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl.fromLocalFile(str(self.path.resolve()))))
        delbtn=QPushButton("Refresh")
        delbtn.setIcon(get_action_icon("refresh", self))
        delbtn.clicked.connect(self.refresh)
        row=QHBoxLayout(); row.addWidget(btn); row.addWidget(delbtn); row.addStretch()
        lay.addLayout(row)
        self.refresh()
    def refresh(self):
        self.list.clear()
        for p in self.path.iterdir():
            self.list.addItem(p.name)

class NotesPage(QWidget):
    def __init__(self, instance):
        super().__init__()
        self.inst=instance
        lay=QVBoxLayout(self)
        lay.addWidget(QLabel("Notes"))
        self.edit=QTextEdit()
        self.edit.setText(instance.notes)
        lay.addWidget(self.edit,1)
        save=QPushButton("Save")
        from launcher.icons import get_action_icon
        save.setIcon(get_action_icon("edit", self))
        save.clicked.connect(self._save)
        lay.addWidget(save)
    def _save(self):
        self.inst.notes=self.edit.toPlainText()
        self.inst.save()

class SettingsOverridePage(QWidget):
    def __init__(self, instance):
        super().__init__()
        self.inst=instance
        lay=QFormLayout(self)
        self.ram=QSpinBox(); self.ram.setRange(1,32); self.ram.setValue(int(instance.settings_overrides.get("ram_gb",2)))
        self.jvm=QLineEdit(instance.settings_overrides.get("custom_jvm_args",""))
        self.java=QLineEdit(instance.settings_overrides.get("java_path",""))
        browse=QPushButton("Browse")
        from launcher.icons import get_action_icon
        browse.setIcon(get_action_icon("folder", self))
        browse.clicked.connect(lambda: self.java.setText(QFileDialog.getOpenFileName(self,"Java","", "java.exe (*.exe)")[0]))
        row=QHBoxLayout(); row.addWidget(self.java,1); row.addWidget(browse)
        lay.addRow("RAM GB:", self.ram)
        lay.addRow("JVM Args:", self.jvm)
        lay.addRow("Java Path:", row)
        save=QPushButton("Save Overrides")
        save.setIcon(get_action_icon("edit", self))
        save.clicked.connect(self._save)
        lay.addRow(save)
    def _save(self):
        self.inst.settings_overrides["ram_gb"]=self.ram.value()
        self.inst.settings_overrides["custom_jvm_args"]=self.jvm.text().strip()
        self.inst.settings_overrides["java_path"]=self.java.text().strip()
        if not self.inst.settings_overrides["java_path"]:
            self.inst.settings_overrides.pop("java_path",None)
        self.inst.save()

class LogPage(QWidget):
    def __init__(self, instance, core):
        super().__init__()
        lay=QVBoxLayout(self)
        lay.addWidget(QLabel("Game Log (live)"))
        self.view=QTextEdit(); self.view.setReadOnly(True)
        lay.addWidget(self.view,1)
        try:
            core.log_message.connect(lambda m: self.view.append(m))
            core.minecraft_launcher.log_message.connect(lambda m: self.view.append(m))
        except: pass
        kill=QPushButton("Kill Process")
        from launcher.icons import get_action_icon
        kill.setIcon(get_action_icon("delete", self))
        kill.clicked.connect(lambda: core.minecraft_launcher.cancel_launch() if hasattr(core,'minecraft_launcher') else None)
        lay.addWidget(kill)

class HistoryPage(QWidget):
    def __init__(self, instance):
        super().__init__()
        lay=QVBoxLayout(self)
        lay.addWidget(QLabel("Launch History — date/time, duration, crashed"))
        self.view=QTextEdit(); self.view.setReadOnly(True)
        lay.addWidget(self.view,1)
        hist_path=instance.path / "launch_history.json"
        import json
        if hist_path.exists():
            try:
                hist=json.loads(hist_path.read_text(encoding="utf-8"))
                lines=[f"{h['time']} — {h['duration']}s — {'CRASH' if h.get('crashed') else 'OK'} (exit {h.get('exit_code')})" for h in hist[-20:]]
                self.view.setText("\n".join(lines) if lines else "No launches yet.")
            except: self.view.setText("No history")
        else:
            self.view.setText("No launches yet.")

# --- ServersPage: add servers via name+ip → servers.dat (fun final feature) ---
import gzip, struct
def _load_servers_dat(path: Path):
    if not path.exists():
        return []
    try:
        with gzip.open(path, 'rb') as f:
            data=f.read()
        # minimal NBT parser for servers.dat
        pos=0
        def r_byte(): nonlocal pos; v=data[pos]; pos+=1; return v
        def r_short(): nonlocal pos; v=struct.unpack('>h', data[pos:pos+2])[0]; pos+=2; return v
        def r_ushort(): nonlocal pos; v=struct.unpack('>H', data[pos:pos+2])[0]; pos+=2; return v
        def r_string():
            l=r_ushort()
            nonlocal pos
            s=data[pos:pos+l].decode('utf-8'); pos+=l
            return s
        # root compound
        if r_byte()!=10: return []
        r_string() # name ""
        servers=[]
        while True:
            t=r_byte()
            if t==0: break
            name=r_string()
            if t==9 and name=="servers":
                elem_type=r_byte(); length=struct.unpack('>i', data[pos:pos+4])[0]; pos+=4
                for _ in range(length):
                    # each element is compound without header? Actually List of Compound stores compounds without name/type
                    entry={}
                    while True:
                        tt=r_byte()
                        if tt==0: break
                        nn=r_string()
                        if tt==8:
                            entry[nn]=r_string()
                        elif tt==1:
                            entry[nn]=r_byte()
                        else:
                            # skip unknown
                            if tt==3: pos+=4
                            elif tt==4: pos+=8
                            else: break
                    servers.append(entry)
            else:
                # skip
                if t==8: r_string()
                elif t==1: r_byte()
                elif t==3: pos+=4
                elif t==9: # unknown list
                    et=r_byte(); l=struct.unpack('>i', data[pos:pos+4])[0]; pos+=4; pos+=l
                else: break
        return servers
    except Exception:
        return []

def _save_servers_dat(path: Path, servers):
    import gzip, struct
    path.parent.mkdir(parents=True, exist_ok=True)
    out=bytearray()
    def w_byte(v): out.append(v & 0xFF)
    def w_short(v): out.extend(struct.pack('>h', v))
    def w_ushort(v): out.extend(struct.pack('>H', v))
    def w_int(v): out.extend(struct.pack('>i', v))
    def w_string(s):
        b=s.encode('utf-8'); w_ushort(len(b)); out.extend(b)
    w_byte(10); w_string("") # root
    w_byte(9); w_string("servers"); w_byte(10); w_int(len(servers))
    for srv in servers:
        # compound entries
        if "name" in srv:
            w_byte(8); w_string("name"); w_string(str(srv["name"]))
        if "ip" in srv:
            w_byte(8); w_string("ip"); w_string(str(srv["ip"]))
        # optional hidden
        w_byte(0)
    w_byte(0) # root end
    with gzip.open(path, 'wb') as f:
        f.write(bytes(out))

class ServersPage(QWidget):
    def __init__(self, instance):
        super().__init__()
        self.inst=instance
        self.path=instance.game_dir / "servers.dat"
        lay=QVBoxLayout(self)
        lay.addWidget(QLabel("Servers — add by name + IP, appears in Multiplayer"))
        form=QHBoxLayout()
        self.name_edit=QLineEdit(); self.name_edit.setPlaceholderText("Server name (e.g. Hypixel)")
        self.ip_edit=QLineEdit(); self.ip_edit.setPlaceholderText("IP (e.g. mc.hypixel.net)")
        form.addWidget(self.name_edit,1); form.addWidget(self.ip_edit,1)
        add=QPushButton("Add"); add.setObjectName("playButton")
        from launcher.icons import get_action_icon
        add.setIcon(get_action_icon("download", self))
        add.clicked.connect(self._add)
        form.addWidget(add)
        lay.addLayout(form)
        self.list=QListWidget()
        from PySide6.QtWidgets import QListWidget as _L
        lay.addWidget(self.list,1)
        btns=QHBoxLayout()
        dele=QPushButton("Remove Selected"); dele.setObjectName("ghostButton"); dele.setIcon(get_action_icon("delete", self)); dele.clicked.connect(self._remove)
        imp=QPushButton("Open servers.dat folder"); imp.setIcon(get_action_icon("folder", self)); imp.clicked.connect(lambda: __import__("PySide6.QtGui", fromlist=["QDesktopServices"]).QDesktopServices.openUrl(__import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl.fromLocalFile(str(self.path.parent.resolve()))))
        btns.addWidget(dele); btns.addWidget(imp); btns.addStretch()
        lay.addLayout(btns)
        self._load()

    def _load(self):
        self.list.clear()
        for srv in _load_servers_dat(self.path):
            self.list.addItem(f"{srv.get('name','?')} — {srv.get('ip','?')}")

    def _add(self):
        name=self.name_edit.text().strip()
        ip=self.ip_edit.text().strip()
        if not name or not ip:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self,"Missing","Fill both name and IP"); return
        if ":" not in ip and "." not in ip:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self,"Invalid IP","IP should be like play.example.com or 1.2.3.4:25565"); return
        servers=_load_servers_dat(self.path)
        servers.append({"name":name, "ip":ip})
        _save_servers_dat(self.path, servers)
        self.name_edit.clear(); self.ip_edit.clear()
        self._load()

    def _remove(self):
        row=self.list.currentRow()
        if row<0: return
        servers=_load_servers_dat(self.path)
        if 0 <= row < len(servers):
            servers.pop(row)
            _save_servers_dat(self.path, servers)
            self._load()

class InstanceSettingsDialog(QDialog):
    def __init__(self, instance, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{instance.name} - Settings")
        self.resize(860,600)
        lay=QVBoxLayout(self)
        tabs=QTabWidget()
        from launcher.application import get_app
        app=get_app()
        tabs.addTab(VersionPage(instance), "Version")
        tabs.addTab(ModsPage(instance), "Mods")
        # 4 content types with Modrinth browse + version/loader filtering, vanilla gating already inside BrowsePage
        from ui.instance_pages.browse_page import BrowsePage
        tabs.addTab(BrowsePage(instance, "resourcepack", "Resource Packs"), "Resource Packs")
        tabs.addTab(BrowsePage(instance, "shader", "Shader Packs"), "Shader Packs")
        tabs.addTab(BrowsePage(instance, "datapack", "Datapacks"), "Datapacks")
        tabs.addTab(GenericFolderPage(instance, "saves"), "Worlds")
        tabs.addTab(GenericFolderPage(instance, "screenshots"), "Screenshots")
        tabs.addTab(ServersPage(instance), "Servers")
        tabs.addTab(NotesPage(instance), "Notes")
        tabs.addTab(SettingsOverridePage(instance), "Settings")
        tabs.addTab(LogPage(instance, app), "Log")
        tabs.addTab(HistoryPage(instance), "History")
        lay.addWidget(tabs,1)
        close=QPushButton("Close")
        from launcher.icons import get_action_icon
        close.setIcon(get_action_icon("delete", self))
        close.clicked.connect(self.accept)
        lay.addWidget(close, alignment=Qt.AlignRight)
