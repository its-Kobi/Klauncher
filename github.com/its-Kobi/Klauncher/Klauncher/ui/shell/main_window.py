from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QDesktopServices, QFontDatabase, QIcon, QPixmap
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QComboBox, QStackedWidget, QMenu, QMessageBox, QFileDialog, QInputDialog, QDialog, QTextEdit, QProgressBar, QLineEdit, QGraphicsOpacityEffect)
from launcher.application import get_app
from launcher.icons import get_action_icon
from launcher.theme import get_theme
from launcher.assets import get_icon
from ui.shell.instance_view import InstanceView

def _display_name(version_id: str) -> str:
    # Clean: fabric_loader_0.14.22-1.20.1 -> Fabric Loader 1.20.1
    # Use target registry if possible
    try:
        from launcher.version_metadata import _parse_minecraft_version
        from launcher.targets.registry import detect_target
        import json
        # fallback parse
        low = version_id.lower()
        # extract mc part
        parsed = _parse_minecraft_version(version_id)
        mc = f"{parsed[0]}.{parsed[1]}" + (f".{parsed[2]}" if parsed and parsed[2] else "") if parsed else version_id
        if "fabric" in low: return f"Fabric Loader {mc}"
        if "quilt" in low: return f"Quilt Loader {mc}"
        if "forge" in low: return f"Forge {mc}"
        if "optifine" in low: return f"OptiFine {mc}"
        # try target display
        # loader version not needed in title
        return mc if mc!=version_id else version_id
    except:
        return version_id

def _enable_black_titlebar(win):
    try:
        import ctypes
        hwnd=int(win.winId())
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win11 20, Win10 19)
        for attr in (20, 19):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
                break
            except: pass
        # also border black
        try:
            # DWMWA_CAPTION_COLOR = 35 (Win11) - set to black #000000
            DWMWA_CAPTION_COLOR=35
            col=0x00000000
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(ctypes.c_int(col)), ctypes.sizeof(ctypes.c_int))
        except: pass
    except: pass

def _load_minecraft_font():
    try:
        from launcher import paths
        # try bundled font
        for p in [paths.get_base_dir() / "Assets" / "MinecraftTen-VGORe.ttf", paths.get_base_dir() / "assets" / "fonts" / "minecraft.ttf"]:
            if p.exists():
                QFontDatabase.addApplicationFont(str(p))
                return
    except: pass

class LeftRail(QFrame):
    from PySide6.QtCore import Signal
    nav = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(56)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6,10,6,10)
        lay.setSpacing(6)
        self.btns = {}
        def _accent_icon(act):
            try:
                from launcher.theme import get_theme as _gt
                _t=_gt(); _acc_text=_t.effective_text(_t.accent, "#ffffff")
                white_ic=get_action_icon(act, None, color="#eef2fb")
                accent_ic=get_action_icon(act, None, color=_acc_text)
                ic=QIcon()
                ic.addPixmap(white_ic.pixmap(QSize(22,22)), QIcon.Normal, QIcon.Off)
                ic.addPixmap(accent_ic.pixmap(QSize(22,22)), QIcon.Normal, QIcon.On)
                ic.addPixmap(accent_ic.pixmap(QSize(22,22)), QIcon.Active, QIcon.On)
                return ic
            except:
                return get_action_icon(act, self)
        items = [("launch","Launch"),("accounts","Accounts"),("instances","Instances")]
        for act, tip in items:
            b = QPushButton()
            b.setToolTip(tip)
            b.setFixedSize(40,40)
            b.setIcon(_accent_icon(act))
            b.setIconSize(QSize(22,22))
            b.setCheckable(True)
            b.setObjectName("ghostButton")
            b.clicked.connect(lambda _, a=act: self.nav.emit(a))
            self.btns[act]=b
            lay.addWidget(b)
        lay.addStretch()
        b = QPushButton()
        b.setToolTip("Settings")
        b.setFixedSize(40,40)
        b.setIcon(_accent_icon("settings"))
        b.setIconSize(QSize(22,22))
        b.setCheckable(True)
        b.setObjectName("ghostButton")
        b.clicked.connect(lambda: self.nav.emit("settings"))
        self.btns["settings"]=b
        lay.addWidget(b)
    def set_active(self, act):
        for k,b in self.btns.items():
            b.setChecked(k==act)
            # subtle pulse animation
            if k==act and get_theme().animations:
                eff = QGraphicsOpacityEffect(b)
                b.setGraphicsEffect(eff)
                anim = QPropertyAnimation(eff, b"opacity", b)
                anim.setDuration(180); anim.setStartValue(0.6); anim.setEndValue(1.0); anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.finished.connect(lambda bb=b: bb.setGraphicsEffect(None))
                anim.start(QPropertyAnimation.DeleteWhenStopped)
                b._anim = anim

class TopBar(QFrame):
    def __init__(self, core, app, parent=None):
        super().__init__(parent)
        self.core=core; self.app=app
        self.setObjectName("panel")
        self.setFixedHeight(52)
        lay=QHBoxLayout(self)
        lay.setContentsMargins(8,6,8,6)
        lay.setSpacing(8)
        self.btn_back=QPushButton(); self.btn_back.setIcon(get_action_icon("back", self)); self.btn_back.setFixedSize(30,30); self.btn_back.setObjectName("ghostButton"); lay.addWidget(self.btn_back)
        self.btn_fwd=QPushButton(); self.btn_fwd.setIcon(get_action_icon("forward", self)); self.btn_fwd.setFixedSize(30,30); self.btn_fwd.setObjectName("ghostButton"); lay.addWidget(self.btn_fwd)
        logo=QLabel()
        ic=get_icon("Klauncher_logo")
        if not ic.isNull(): logo.setPixmap(ic.pixmap(QSize(28,28)))
        lay.addWidget(logo)
        title=QLabel("KLauncher"); title.setObjectName("cardTitle"); lay.addWidget(title)
        lay.addSpacing(12)
        lay.addWidget(QLabel("Instance:"))
        self.inst_combo=QComboBox(); self.inst_combo.setMinimumWidth(200); self.inst_combo.setPlaceholderText("No instance selected"); lay.addWidget(self.inst_combo)
        lay.addSpacing(8)
        lay.addWidget(QLabel("Account:"))
        self.acc_combo=QComboBox(); self.acc_combo.setMinimumWidth(180); lay.addWidget(self.acc_combo)
        lay.addStretch()

class CentralLaunchView(QWidget):
    from PySide6.QtCore import Signal
    launch_clicked = Signal()
    launch_options = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        lay=QVBoxLayout(self)
        lay.setContentsMargins(32,32,32,32)
        lay.setSpacing(12)
        lay.addStretch()
        self.head = QLabel()
        self.head.setFixedSize(96,96)
        self.head.setAlignment(Qt.AlignCenter)
        self.head.setStyleSheet("background:#1e2433; border-radius:18px; border:1px solid #222a3a; font-size:36px;")
        lay.addWidget(self.head, alignment=Qt.AlignHCenter)
        self.name_label=QLabel("No account selected"); self.name_label.setObjectName("pageTitle"); self.name_label.setAlignment(Qt.AlignHCenter); lay.addWidget(self.name_label)
        self.sub_label=QLabel("Select an instance and account to launch"); self.sub_label.setObjectName("pageSub"); self.sub_label.setAlignment(Qt.AlignHCenter); lay.addWidget(self.sub_label)
        row=QHBoxLayout(); row.addStretch()
        # accent-aware icon: off-white accent → black icon for readability
        try:
            from launcher.theme import get_theme as _gt
            _t=_gt(); _acc_text=_t.effective_text(_t.accent, "#ffffff")
        except: _acc_text="#ffffff"
        self.launch_btn=QPushButton("  LAUNCH"); self.launch_btn.setObjectName("playButton"); self.launch_btn.setFixedHeight(52); self.launch_btn.setFixedWidth(320); self.launch_btn.setIcon(get_action_icon("launch", color=_acc_text)); self.launch_btn.clicked.connect(self.launch_clicked.emit); row.addWidget(self.launch_btn)
        self.drop_btn=QPushButton("▼"); self.drop_btn.setObjectName("secondaryButton"); self.drop_btn.setFixedSize(40,52); self.drop_btn.clicked.connect(self.launch_options.emit); row.addWidget(self.drop_btn)
        row.addStretch(); lay.addLayout(row)
        self.status=QLabel(""); self.status.setObjectName("caption"); self.status.setAlignment(Qt.AlignHCenter); lay.addWidget(self.status)
        lay.addStretch()
        self.progress=QProgressBar(); self.progress.setVisible(False); self.progress.setFixedHeight(6); self.progress.setTextVisible(False); lay.addWidget(self.progress)
        # logs on main tab (toggleable)
        self.log_view=QTextEdit(); self.log_view.setObjectName("logView"); self.log_view.setReadOnly(True); self.log_view.setFixedHeight(140); self.log_view.setVisible(False); lay.addWidget(self.log_view)
        # pulse animation
        self._pulse_anim=None

    def set_account(self, username, uuid):
        if username:
            self.name_label.setText(username)
            try:
                from launcher.skin_cache import get_skin_cache
                from PySide6.QtGui import QPixmap
                cache=get_skin_cache()
                pm=cache.get_cached(uuid) if uuid else None
                if pm and not pm.isNull():
                    scaled=pm.scaled(96,96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.head.setPixmap(scaled)
                    self.head.setText("")
                else:
                    self.head.setText(username[0].upper())
                    self.head.setPixmap(QPixmap())
                    if uuid:
                        def _on_fetch(u,p):
                            if u==uuid and p and not p.isNull():
                                self.head.setPixmap(p.scaled(96,96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                                self.head.setText("")
                                try: cache.fetched.disconnect(_on_fetch)
                                except: pass
                        cache.fetched.connect(_on_fetch)
                        cache.request(uuid, username)
            except:
                self.head.setText(username[0].upper())
        else:
            self.name_label.setText("No account selected")
            self.head.setText("")
            from PySide6.QtGui import QPixmap
            self.head.setPixmap(QPixmap())

    def set_instance(self, inst):
        if inst:
            disp=_display_name(inst.version_id)
            self.launch_btn.setText(f"  LAUNCH  {disp}")
            self.sub_label.setText(f"{inst.name}  •  {inst.loader}")
        else:
            self.launch_btn.setText("  LAUNCH")
            self.sub_label.setText("Select an instance and account to launch")

    def set_empty(self, text="Select an instance from the Instances view to start"):
        self.sub_label.setText(text)

    def set_running(self, running: bool):
        if running:
            self.launch_btn.setText("  STOP")
            self.launch_btn.setStyleSheet("background:#e64242; color:white;")
            # pulse
            if get_theme().animations:
                eff=QGraphicsOpacityEffect(self.launch_btn)
                self.launch_btn.setGraphicsEffect(eff)
                anim=QPropertyAnimation(eff, b"opacity", self)
                anim.setDuration(600); anim.setStartValue(1.0); anim.setEndValue(0.7); anim.setLoopCount(-1); anim.setEasingCurve(QEasingCurve.InOutQuad)
                anim.start(QPropertyAnimation.DeleteWhenStopped)
                self._pulse_anim=anim
        else:
            self.launch_btn.setText("  LAUNCH" + (f"  {_display_name(self.parent().parent().selected_instance.version_id)}" if hasattr(self.parent().parent(), 'selected_instance') and self.parent().parent().selected_instance else ""))
            self.launch_btn.setStyleSheet("")
            if self._pulse_anim:
                try: self._pulse_anim.stop()
                except: pass
                self.launch_btn.setGraphicsEffect(None)
                self._pulse_anim=None

    def set_logs_visible(self, visible: bool):
        self.log_view.setVisible(visible)
        if visible and get_theme().animations:
            eff=QGraphicsOpacityEffect(self.log_view)
            self.log_view.setGraphicsEffect(eff)
            anim=QPropertyAnimation(eff, b"opacity", self.log_view)
            anim.setDuration(220); anim.setStartValue(0); anim.setEndValue(1); anim.start(QPropertyAnimation.DeleteWhenStopped)
            self.log_view._anim=anim

# Accounts as embedded page (not dialog)
class AccountsPage(QWidget):
    from PySide6.QtCore import Signal
    account_changed = Signal()
    def __init__(self, core, app, parent=None):
        super().__init__(parent)
        self.core=core; self.app=app
        lay=QVBoxLayout(self); lay.setContentsMargins(12,12,12,12); lay.setSpacing(12)
        lay.addWidget(QLabel("Accounts"))
        from ui import ProfilesPage
        self.page=ProfilesPage()
        self.page.profile_created.connect(lambda u: (self.core.create_profile(u), self.refresh()))
        self.page.profile_deleted.connect(lambda uid: (self.core.delete_profile(uid), self.refresh()))
        self.page.profile_selected.connect(lambda uid: self.account_changed.emit())
        self.page.microsoft_login_requested.connect(self._ms_login)
        self.page.microsoft_logout_requested.connect(lambda uid: (self.core.logout_microsoft(uid), self.refresh()))
        self.page.microsoft_selected.connect(lambda uid: self.account_changed.emit())
        lay.addWidget(self.page,1)
        self.refresh()
        # connect signals for secure Microsoft ownership check
        try:
            self.core.microsoft_login_succeeded.connect(lambda acc: self.refresh())
            self.core.microsoft_login_failed.connect(self._ms_failed)
        except: pass

    def refresh(self):
        try:
            self.page.set_profiles(self.core.list_profiles())
            self.page.set_microsoft_accounts(self.core.list_microsoft_accounts())
        except: pass
        self.account_changed.emit()

    def _ms_login(self):
        # start login, show device dialog handled in core, but also ensure ownership error is shown secure
        self.core.start_microsoft_login()

    def _ms_failed(self, msg):
        if "does not own" in msg or "Minecraft account required" in msg:
            QMessageBox.warning(self, "No Minecraft License", "This Microsoft account does not own Minecraft Java Edition.\nYou cannot play with it.\nPlease purchase Minecraft or use an account that owns the game.\n(KLauncher never stores your password — auth is via Microsoft OAuth2.)")
        else:
            QMessageBox.warning(self, "Microsoft Login Failed", msg)

class MainWindow(QMainWindow):
    def __init__(self, core=None):
        super().__init__()
        _load_minecraft_font()
        self.app=get_app()
        self.core=core or self.app
        self.setWindowTitle("KLauncher")
        self.resize(1280, 760)
        self.setStyleSheet(get_theme().qss())
        _enable_black_titlebar(self)
        self.selected_instance=None
        self._tray=None
        self._build_ui()
        self._connect()
        self.refresh_instances()
        self.refresh_accounts()
        QTimer.singleShot(400, self._initial)

    def showEvent(self, e):
        super().showEvent(e)
        _enable_black_titlebar(self)

    def _build_ui(self):
        central=QWidget(); central.setObjectName("appBg"); self.setCentralWidget(central)
        outer=QVBoxLayout(central); outer.setContentsMargins(6,6,6,6); outer.setSpacing(6)
        self.top_bar=TopBar(self.core, self.app); outer.addWidget(self.top_bar)
        mid=QHBoxLayout(); mid.setContentsMargins(0,0,0,0); mid.setSpacing(6)
        self.left_rail=LeftRail(); mid.addWidget(self.left_rail)
        self.stack=QStackedWidget()
        self.launch_view=CentralLaunchView()
        self.instance_view=InstanceView()
        self.instances_page=QWidget()
        ip_lay=QVBoxLayout(self.instances_page); ip_lay.setContentsMargins(8,8,8,8)
        filter_row=QHBoxLayout()
        filter_row.addWidget(QLabel("Group:"))
        self.group_combo=QComboBox(); self.group_combo.addItem("All"); self.group_combo.currentTextChanged.connect(self._filter_instances); filter_row.addWidget(self.group_combo)
        self.search_edit=QLineEdit(); self.search_edit.setPlaceholderText("Search instances..."); self.search_edit.textChanged.connect(self._filter_instances); filter_row.addWidget(self.search_edit,1)
        self.btn_grid=QPushButton(); self.btn_grid.setIcon(get_action_icon("instances", self)); self.btn_grid.setCheckable(True); self.btn_grid.setChecked(True); self.btn_grid.clicked.connect(lambda: self.instance_view.set_grid_mode(self.btn_grid.isChecked())); filter_row.addWidget(self.btn_grid)
        self.btn_add=QPushButton("Add Instance"); self.btn_add.setIcon(get_action_icon("download", self)); self.btn_add.setObjectName("playButton"); self.btn_add.clicked.connect(self._add_instance); filter_row.addWidget(self.btn_add)
        # load default .minecraft button
        self.btn_load_mc=QPushButton("Load default .minecraft versions"); self.btn_load_mc.setIcon(get_action_icon("download", self)); self.btn_load_mc.setObjectName("secondaryButton"); self.btn_load_mc.clicked.connect(self._load_default_mc); filter_row.addWidget(self.btn_load_mc)
        ip_lay.addLayout(filter_row)
        ip_lay.addWidget(self.instance_view,1)
        inst_actions=QHBoxLayout()
        for act,tip in [("play_instance","Launch"),("edit","Edit"),("copy","Copy"),("export","Export"),("delete","Delete"),("folder","Folder"),("health","Health Check")]:
            b=QPushButton(); b.setToolTip(tip); b.setIcon(get_action_icon(act, self)); b.setFixedSize(36,36); b.setObjectName("ghostButton"); b.clicked.connect(lambda _,a=act: self._instance_action(a)); inst_actions.addWidget(b)
        inst_actions.addStretch(); ip_lay.addLayout(inst_actions)
        # Accounts page embedded
        self.accounts_page=AccountsPage(self.core, self.app)
        self.accounts_page.account_changed.connect(self.refresh_accounts)
        self.stack.addWidget(self.launch_view)      #0
        self.stack.addWidget(self.instances_page)   #1
        self.stack.addWidget(self.accounts_page)    #2
        mid.addWidget(self.stack,1)
        outer.addLayout(mid,1)
        from PySide6.QtWidgets import QStatusBar
        sb=QStatusBar(); self.setStatusBar(sb)
        self.lbl_sel=QLabel("No instance selected"); self.lbl_time=QLabel(""); sb.addWidget(self.lbl_sel,1); sb.addPermanentWidget(self.lbl_time)
        self.left_rail.set_active("launch")
        self.setAcceptDrops(True)
        # tray
        self._init_tray()
        # logs visibility setting
        self._apply_logs_setting()

    def _init_tray(self):
        from PySide6.QtWidgets import QSystemTrayIcon, QMenu
        try:
            self._tray = QSystemTrayIcon(self)
            ic=get_icon("Klauncher_logo")
            if not ic.isNull(): self._tray.setIcon(ic)
            menu=QMenu()
            menu.addAction("Show", self.showNormal)
            menu.addAction("Quit", self.close)
            self._tray.setContextMenu(menu)
        except: pass

    def _apply_logs_setting(self):
        show = bool(self.app.config.get("show_logs_on_main", False))
        self.launch_view.set_logs_visible(show)

    def _connect(self):
        self.left_rail.nav.connect(self._on_nav)
        self.launch_view.launch_clicked.connect(self._on_launch_btn)
        self.launch_view.launch_options.connect(self._launch_options)
        self.instance_view.instance_selected.connect(self._on_select)
        self.instance_view.instance_launch_requested.connect(self._launch_inst)
        self.instance_view.instance_context.connect(self._on_context)
        self.top_bar.inst_combo.currentIndexChanged.connect(self._on_top_inst_changed)
        self.top_bar.acc_combo.currentIndexChanged.connect(self._on_acc_changed)
        self.app.instance_manager.instances_changed.connect(self.refresh_instances)
        try:
            self.app.minecraft_launcher.process_started.connect(self._on_process_started)
            self.app.minecraft_launcher.process_finished.connect(self._on_process_finished)
            self.app.minecraft_launcher.launch_failed.connect(lambda m: QMessageBox.critical(self,"Launch failed",m))
            self.app.minecraft_launcher.log_message.connect(self._on_log)
        except: pass
        # Microsoft OAuth2 device flow — must open browser
        try:
            self.core.microsoft_code_ready.connect(self._on_microsoft_code)
            self.core.microsoft_login_succeeded.connect(self._on_microsoft_success)
            self.core.microsoft_login_failed.connect(self._on_microsoft_failed)
            self.core.microsoft_accounts_changed.connect(self.refresh_accounts)
            self.core.profiles_updated.connect(self.refresh_accounts)
        except: pass
        self._ms_dialog=None

    def _add_instance(self):
        from ui.instance_pages.version_page import NewInstanceDialog
        dlg=NewInstanceDialog(self, self.core)
        if dlg.exec()==QDialog.Accepted:
            data=dlg.get_data()
            # modpack flow
            if data.get("modpack"):
                try:
                    import urllib.request, zipfile, shutil
                    from pathlib import Path as _P
                    pack_hit=data.get("pack_hit") or {}
                    icon_url=data.get("icon_url")
                    ver=data.get("pack_version") or {}
                    # create instance
                    inst=self.app.instance_manager.create(data["name"], data["version_id"], data.get("loader","vanilla"), data.get("loader_version"), "custom", data.get("group",""))
                    # icon
                    if icon_url:
                        try:
                            ico_path=inst.path / "icon.png"
                            req=urllib.request.Request(icon_url, headers={"User-Agent":"KLauncher/1.0"})
                            with urllib.request.urlopen(req, timeout=10) as r, open(ico_path,'wb') as out:
                                out.write(r.read())
                            inst.icon=str(ico_path)
                            inst.save()
                        except: pass
                    # download pack file
                    files=ver.get("files",[])
                    if files:
                        f=files[0]; url=f.get("url"); name=f.get("filename","pack.mrpack")
                        dest=inst.path / name
                        req=urllib.request.Request(url, headers={"User-Agent":"KLauncher/1.0"})
                        with urllib.request.urlopen(req, timeout=60) as r, open(dest,'wb') as out:
                            while True:
                                ch=r.read(8192)
                                if not ch: break
                                out.write(ch)
                        # if mrpack zip, extract overrides
                        if name.endswith(".mrpack") or str(dest).endswith(".zip"):
                            try:
                                with zipfile.ZipFile(dest) as z:
                                    # modrinth index
                                    for m in z.namelist():
                                        if m.startswith("overrides/"):
                                            rel=m[len("overrides/"):]
                                            if not rel: continue
                                            target=inst.game_dir / rel
                                            if m.endswith("/"):
                                                target.mkdir(parents=True, exist_ok=True)
                                            else:
                                                target.parent.mkdir(parents=True, exist_ok=True)
                                                with z.open(m) as src, open(target,'wb') as dst:
                                                    shutil.copyfileobj(src, dst)
                                    # also handle client-overrides
                                    for m in z.namelist():
                                        if m.startswith("client-overrides/"):
                                            rel=m[len("client-overrides/"):]
                                            target=inst.game_dir / rel
                                            if m.endswith("/"):
                                                target.mkdir(parents=True, exist_ok=True)
                                            else:
                                                target.parent.mkdir(parents=True, exist_ok=True)
                                                with z.open(m) as src, open(target,'wb') as dst:
                                                    shutil.copyfileobj(src, dst)
                            except: pass
                    QMessageBox.information(self,"Modpack Installed", f"{inst.name} installed. Mods/resourcepacks extracted to {inst.game_dir}")
                except Exception as e:
                    QMessageBox.warning(self,"Modpack failed", str(e))
                return
            # normal instance
            loader=data["loader"]; mc=data["mc_version"]; lv=data.get("loader_version")
            # use local assets: optifine_icon.png and CustomClients.png
            if loader=="optifine":
                icon_name="optifine_icon"
            elif loader=="custom":
                icon_name="CustomClients"
            else:
                icon_name=data.get("icon","vanilla")
                # map loader to local asset name
                if loader in ("fabric","forge","quilt","vanilla"):
                    icon_name=loader
            inst=self.app.instance_manager.create(data["name"], data["version_id"], loader, lv, icon_name, data.get("group",""))
            if loader in ("fabric","quilt","forge") and lv:
                try:
                    if loader=="fabric": self.core.version_manager.install_loader("fabric", mc, lv)
                    elif loader=="quilt": self.core.version_manager.install_loader("quilt", mc, lv)
                    elif loader=="forge":
                        QMessageBox.information(self,"Forge","Forge will be fetched on first launch if needed.")
                except: pass
            QMessageBox.information(self,"Instance Created", f"{inst.name} created.")

    def _initial(self):
        try: self.core.fetch_versions()
        except: pass
        try: self.app.java_manager.detect()
        except: pass

    def _on_nav(self, act):
        # animated stack switch
        target = {"launch":0,"instances":1,"accounts":2}.get(act, None)
        if target is not None:
            self._animate_to(target)
            self.left_rail.set_active(act)
        elif act=="settings":
            self._open_global_settings()

    def _animate_to(self, idx):
        if idx==self.stack.currentIndex(): return
        if get_theme().animations:
            cur=self.stack.currentWidget()
            eff=QGraphicsOpacityEffect(cur)
            cur.setGraphicsEffect(eff)
            anim=QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(140); anim.setStartValue(1.0); anim.setEndValue(0.0)
            def done():
                cur.setGraphicsEffect(None)
                self.stack.setCurrentIndex(idx)
                nxt=self.stack.currentWidget()
                eff2=QGraphicsOpacityEffect(nxt)
                nxt.setGraphicsEffect(eff2)
                a2=QPropertyAnimation(eff2, b"opacity", self)
                a2.setDuration(180); a2.setStartValue(0.0); a2.setEndValue(1.0)
                a2.finished.connect(lambda: nxt.setGraphicsEffect(None))
                a2.start(QPropertyAnimation.DeleteWhenStopped)
                nxt._anim2=a2
            anim.finished.connect(done)
            anim.start(QPropertyAnimation.DeleteWhenStopped)
            cur._anim=anim
        else:
            self.stack.setCurrentIndex(idx)

    def refresh_instances(self):
        insts=self.app.instance_manager.list()
        self.instance_view.set_instances(insts)
        self.top_bar.inst_combo.clear()
        self.group_combo.clear(); self.group_combo.addItem("All")
        groups=set()
        for i in insts:
            self.top_bar.inst_combo.addItem(f"{_display_name(i.version_id)}  [{i.loader}]", i.id)
            if i.group: groups.add(i.group)
        for g in sorted(groups): self.group_combo.addItem(g)
        if insts and not self.selected_instance:
            self.selected_instance=self.app.instance_manager.get(insts[0].id)
            self._update_status()
        self._filter_instances()

    def _filter_instances(self):
        q=self.search_edit.text().lower() if hasattr(self,'search_edit') else ""
        grp=self.group_combo.currentText() if hasattr(self,'group_combo') else "All"
        insts=self.app.instance_manager.list()
        filtered=[i for i in insts if (not q or q in i.name.lower() or q in i.version_id.lower()) and (grp=="All" or i.group==grp)]
        self.instance_view.set_instances(filtered)

    def refresh_accounts(self):
        self.top_bar.acc_combo.clear()
        try:
            for p in self.core.list_profiles():
                self.top_bar.acc_combo.addItem(f"[Offline] {p.username}", p.uuid)
            for acc in self.core.list_microsoft_accounts():
                self.top_bar.acc_combo.addItem(f"[MS] {acc.username}", acc.uuid)
        except: pass
        self._on_acc_changed()

    def _on_acc_changed(self):
        uuid=self.top_bar.acc_combo.currentData()
        prof=self.core.get_profile(uuid) if uuid else None
        self.launch_view.set_account(prof.username if prof else "", uuid)

    def _on_top_inst_changed(self):
        iid=self.top_bar.inst_combo.currentData()
        if iid:
            inst=self.app.instance_manager.get(iid)
            if inst:
                self.selected_instance=inst
                self._update_status()

    def _on_select(self, inst):
        self.selected_instance=inst
        for i in range(self.top_bar.inst_combo.count()):
            if self.top_bar.inst_combo.itemData(i)==inst.id:
                self.top_bar.inst_combo.setCurrentIndex(i); break
        self._update_status()

    def _update_status(self):
        if not self.selected_instance:
            self.lbl_sel.setText("No instance selected"); self.launch_view.set_empty(); return
        disp=_display_name(self.selected_instance.version_id)
        self.lbl_sel.setText(f"{self.selected_instance.name} • {disp} [{self.selected_instance.loader}]")
        mins=int(self.selected_instance.total_playtime//60)
        self.lbl_time.setText(f"Playtime: {mins} min")
        self.launch_view.set_instance(self.selected_instance)

    def _load_default_mc(self):
        cnt=self.app.instance_manager.load_default_minecraft_versions()
        if cnt==0:
            QMessageBox.information(self,"No new versions", "No new versions found in default .minecraft/versions or already imported.")
        else:
            QMessageBox.information(self,"Imported", f"Imported {cnt} version(s) from default .minecraft.")

    def _on_launch_btn(self):
        # toggle stop when running
        if self.app.minecraft_launcher.is_running() or self.app.minecraft_launcher.is_preparing():
            self.app.minecraft_launcher.cancel_launch()
            return
        self._launch_selected()

    def _launch_selected(self):
        if not self.selected_instance:
            QMessageBox.warning(self,"No instance","Select an instance in Instances view first."); self._animate_to(1); return
        self._launch_inst(self.selected_instance)

    def _launch_options(self):
        menu=QMenu(self)
        menu.addAction(get_action_icon("play_instance",self),"Launch offline", self._launch_selected)
        menu.addAction(get_action_icon("edit",self),"Edit instance", self._edit_instance)
        menu.addAction(get_action_icon("folder",self),"Open folder", self._open_folder)
        menu.exec(self.launch_view.drop_btn.mapToGlobal(self.launch_view.drop_btn.rect().bottomLeft()))

    def _launch_inst(self, inst, _auto_retry=False):
        required=inst.required_java()
        chosen=self.app.config.get("java_path") or inst.settings_overrides.get("java_path")
        if not chosen:
            compat=self.app.java_manager.find_compatible(required)
            if compat: chosen=compat.path
        ok,msg=self.app.java_manager.validate_for_launch(required, chosen)
        if not ok:
            # Auto-download required Java (e.g. 1.8.9 → Java 8) if missing, then auto-relaunch
            # Example: 1.8.9 needs Java 8, 1.16 → 8, 1.17 → 16, 1.18-1.20.4 → 17, 1.20.5+ → 21, 1.21+ → 21/25
            self.statusBar().showMessage(f"Java {required} required for {inst.version_id} — downloading...", 3000)
            self._auto_download_and_launch(inst, required)
            return
        uuid=self.top_bar.acc_combo.currentData()
        if not uuid: QMessageBox.warning(self,"No account","Add an account via Accounts page."); self._animate_to(2); return
        # Microsoft ownership secure check
        is_ms=self.core.is_microsoft_account(uuid) if hasattr(self.core,'is_microsoft_account') else False
        if is_ms:
            # verify token and ownership explicitly
            try:
                info=self.app.microsoft_manager.get_access_token_for_launch(uuid)
                if not info:
                    QMessageBox.warning(self,"No Minecraft License", "This Microsoft account does not own Minecraft Java Edition.\nYou cannot play with it.\n(Purchase required, auth is OAuth2 — no password stored.)")
                    return
            except Exception as ex:
                if "does not own" in str(ex) or "Minecraft account required" in str(ex):
                    QMessageBox.warning(self,"No Minecraft License", "This Microsoft account does not own Minecraft Java Edition.\nYou cannot play with it.")
                    return
                raise
        java_path=chosen or (self.app.java_manager.find_compatible(required).path if self.app.java_manager.find_compatible(required) else chosen)
        game_dir=inst.game_dir; game_dir.mkdir(parents=True, exist_ok=True)
        # ensure mods/resourcepacks dirs exist and log content for debugging
        try:
            (game_dir / "mods").mkdir(exist_ok=True)
            mods=list((game_dir / "mods").glob("*.jar"))
            enabled=[p for p in mods if not p.name.endswith(".disabled")]
            disabled=list((game_dir / "mods").glob("*.jar.disabled"))
            self.app.minecraft_launcher.log_message.emit(f"Mods check: {len(enabled)} enabled, {len(disabled)} disabled in {game_dir / 'mods'}")
            if not enabled and (game_dir / "mods").exists():
                # list any files
                all_files=list((game_dir / "mods").iterdir())
                if all_files:
                    self.app.minecraft_launcher.log_message.emit(f"Mods folder contents: {[p.name for p in all_files[:5]]}")
        except: pass
        import time; inst.last_played=time.time(); inst.save()
        self._history_start(inst)
        if is_ms and self.app.microsoft_manager:
            info=self.app.microsoft_manager.get_access_token_for_launch(uuid)
            if not info:
                QMessageBox.warning(self,"No Minecraft License", "This Microsoft account does not own Minecraft Java Edition."); return
            username, access_token, user_type, xuid = info["username"], info["access_token"], "msa", info.get("xuid"); uid=info["uuid"]
        else:
            prof=self.core.get_profile(uuid)
            if not prof: QMessageBox.warning(self,"Account","Profile not found"); return
            username, uid, access_token, user_type, xuid = prof.username, prof.uuid, "0", "legacy", None
        ram=inst.effective_setting("ram_gb", self.app.config.get("ram_gb",2))
        jvm=inst.effective_setting("custom_jvm_args", self.app.config.get("custom_jvm_args",""))
        self.app.minecraft_launcher.launch(java_path, inst.version_id, username, uid, game_dir, ram, jvm, access_token=access_token, user_type=user_type, xuid=xuid)

    def _auto_download_and_launch(self, inst, required):
        # Automatic Java fetch for any MC version: 1.8.9->8, 1.16->8, 1.17->16, 1.18-1.20.4->17, 1.20.5+->21 etc. via Adoptium
        if getattr(self, '_java_auto_downloading', False):
            return
        self._java_auto_downloading=True
        from PySide6.QtWidgets import QProgressDialog
        dlg=QProgressDialog(f"Java {required} not found for {inst.version_id}\nDownloading Temurin {required} ...", "Cancel", 0, 100, self); dlg.setWindowModality(Qt.WindowModal); dlg.setMinimumDuration(0); dlg.show()
        def on_prog(v):
            dlg.setValue(v)
            if dlg.wasCanceled():
                try: self.app.java_manager.cancel_download()
                except: pass
        def on_ok(exe):
            try: self.app.java_manager.download_progress.disconnect(on_prog)
            except: pass
            try: self.app.java_manager.download_finished.disconnect(on_ok)
            except: pass
            try: self.app.java_manager.download_failed.disconnect(on_fail)
            except: pass
            self._java_auto_downloading=False
            dlg.close()
            # persist for this instance and auto-relaunch
            inst.settings_overrides["java_path"]=exe; inst.save()
            try: self.app.java_manager.detect()
            except: pass
            self.statusBar().showMessage(f"Java {required} ready — launching {inst.name}...", 3000)
            QTimer.singleShot(400, lambda: self._launch_inst(inst, _auto_retry=True))
        def on_fail(m):
            try: self.app.java_manager.download_progress.disconnect(on_prog)
            except: pass
            try: self.app.java_manager.download_finished.disconnect(on_ok)
            except: pass
            try: self.app.java_manager.download_failed.disconnect(on_fail)
            except: pass
            self._java_auto_downloading=False
            dlg.close()
            QMessageBox.warning(self,"Java download failed", f"Could not fetch Java {required} for {inst.version_id}:\n{m}\n\nInstall it manually in Settings → Java.")
        self.app.java_manager.download_progress.connect(on_prog)
        self.app.java_manager.download_finished.connect(on_ok)
        self.app.java_manager.download_failed.connect(on_fail)
        self.app.java_manager.download_java(required)

    def _download_java(self, required, inst):
        # Manual fallback (kept for Settings)
        return self._auto_download_and_launch(inst, required)

    def _instance_action(self, act):
        if not self.selected_instance: QMessageBox.warning(self,"No instance","Select one first."); return
        if act=="edit": self._edit_instance()
        elif act=="copy": self._copy_instance()
        elif act=="export": self._export_instance()
        elif act=="delete": self._delete_instance()
        elif act=="folder": self._open_folder()
        elif act=="play_instance": self._launch_inst(self.selected_instance)
        elif act=="health": self._health_check()

    def _edit_instance(self):
        if not self.selected_instance: return
        from ui.instance_pages.dialog import InstanceSettingsDialog
        dlg=InstanceSettingsDialog(self.selected_instance, self); dlg.exec(); self.refresh_instances()

    def _copy_instance(self):
        if not self.selected_instance: return
        name,ok=QInputDialog.getText(self,"Copy","New name:", text=self.selected_instance.name+" - Copy")
        if ok and name: self.app.instance_manager.copy(self.selected_instance.id, name)

    def _export_instance(self):
        if not self.selected_instance: return
        dest,_=QFileDialog.getSaveFileName(self,"Export", self.selected_instance.name+".zip", "ZIP (*.zip)")
        if dest: self.app.instance_manager.export(self.selected_instance.id, Path(dest))

    def _delete_instance(self):
        if not self.selected_instance: return
        if QMessageBox.question(self,"Delete",f"Delete {self.selected_instance.name}?")==QMessageBox.Yes:
            self.app.instance_manager.delete(self.selected_instance.id); self.selected_instance=None; self._update_status()

    def _open_folder(self):
        if not self.selected_instance: return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.selected_instance.path.resolve())))

    def _on_context(self, inst, pos):
        menu=QMenu(self)
        menu.addAction(get_action_icon("play_instance",self),"Launch", lambda: self._launch_inst(inst))
        menu.addAction(get_action_icon("edit",self),"Edit", lambda: (setattr(self,'selected_instance',inst), self._edit_instance()))
        menu.addAction(get_action_icon("health",self),"Health Check", lambda: (setattr(self,'selected_instance',inst), self._health_check()))
        menu.addAction(get_action_icon("copy",self),"Copy", lambda: (setattr(self,'selected_instance',inst), self._copy_instance()))
        menu.addAction(get_action_icon("delete",self),"Delete", lambda: (setattr(self,'selected_instance',inst), self._delete_instance()))
        menu.addAction(get_action_icon("folder",self),"Folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(inst.path.resolve()))))
        menu.exec(pos)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()
            if get_theme().animations:
                self.instance_view.setStyleSheet("border: 2px dashed #2d7dff; border-radius: 10px;")
    def dragLeaveEvent(self, e):
        self.instance_view.setStyleSheet("")
    def dropEvent(self, e):
        self.instance_view.setStyleSheet("")
        if e.mimeData().hasUrls() and self.stack.currentIndex()==1:
            pos=self.instance_view.viewport().mapFromGlobal(e.position().toPoint() if hasattr(e.position(), 'toPoint') else e.pos())
            item=self.instance_view.itemAt(pos)
            if item:
                try: inst=item.data(0x0100)
                except: inst=None
                if inst and hasattr(inst,'game_dir'):
                    for url in e.mimeData().urls():
                        p=Path(url.toLocalFile())
                        if p.suffix.lower() in (".jar",".zip"):
                            if p.suffix.lower()==".jar":
                                from launcher.mods.manager import ModManager
                                mgr=ModManager(inst)
                                ok,msg=mgr.check_compat(p.name, inst)
                                if not ok: QMessageBox.warning(self,"Incompatible",msg); continue
                                dest=mgr.mods_dir()
                            else:
                                dest=inst.game_dir / "resourcepacks"
                                dest.mkdir(parents=True, exist_ok=True)
                            import shutil
                            shutil.copy2(p, dest / p.name)
                            QMessageBox.information(self,"Installed", f"{p.name} → {inst.name}")
                            e.acceptProposedAction()
                            return
        if e.mimeData().hasText() and self.stack.currentIndex()==1:
            txt=e.mimeData().text().strip()
            if txt.startswith("modrinth:"):
                try:
                    _, pid, ptype = txt.split(":",2)
                    pos=self.instance_view.viewport().mapFromGlobal(e.position().toPoint() if hasattr(e.position(), 'toPoint') else e.pos())
                    item=self.instance_view.itemAt(pos)
                    inst=None
                    if item:
                        try: inst=item.data(0x0100)
                        except: pass
                    if not inst: inst=self.selected_instance
                    if inst:
                        folder_map={"mod":"mods","resourcepack":"resourcepacks","shader":"shaderpacks","datapack":"datapacks"}
                        folder=folder_map.get(ptype,"mods")
                        from launcher.modplatform.modrinth import get_project_versions, download_version_file, check_compat
                        from launcher.version_metadata import _parse_minecraft_version
                        import json, urllib.request
                        req=urllib.request.Request(f"https://api.modrinth.com/v2/project/{pid}", headers={"User-Agent":"KLauncher/1.0"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            proj=json.loads(resp.read().decode())
                        ok,msg=check_compat(proj, inst)
                        if not ok:
                            QMessageBox.warning(self,"Incompatible",msg); e.acceptProposedAction(); return
                        parsed=_parse_minecraft_version(inst.version_id)
                        mc=f"{parsed[0]}.{parsed[1]}.{parsed[2]}" if parsed and parsed[2] else (f"{parsed[0]}.{parsed[1]}" if parsed else None)
                        loader=inst.loader if inst.loader in ("fabric","forge","quilt") and ptype in ("mod","shader") else None
                        vers=get_project_versions(pid, loaders=[loader] if loader else None, game_versions=[mc] if mc else None)
                        if not vers and mc:
                            vers=get_project_versions(pid, loaders=[loader] if loader else None, game_versions=None)
                        if not vers:
                            QMessageBox.warning(self,"No compatible version", f"No version for {inst.version_id}"); e.acceptProposedAction(); return
                        dest_dir=inst.game_dir / folder
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        dest=download_version_file(vers[0], dest_dir)
                        QMessageBox.information(self,"Installed", f"{dest.name} → {inst.name}/{folder}/")
                except Exception as ex:
                    QMessageBox.warning(self,"Install failed", str(ex))
                e.acceptProposedAction()
                return
        super().dropEvent(e)

    def _refresh_theme_icons(self):
        # Re-tint all shell icons for light/dark + off-white accent (black text/icons on light accent)
        try:
            from launcher.theme import get_theme as _gt
            _t=_gt(); _acc_text=_t.effective_text(_t.accent, "#ffffff")
            for act, btn in self.left_rail.btns.items():
                # state-aware: white when unchecked, accent_text when checked
                try:
                    white_ic=get_action_icon(act, None, color="#eef2fb")
                    accent_ic=get_action_icon(act, None, color=_acc_text)
                    ic=QIcon()
                    ic.addPixmap(white_ic.pixmap(QSize(22,22)), QIcon.Normal, QIcon.Off)
                    ic.addPixmap(accent_ic.pixmap(QSize(22,22)), QIcon.Normal, QIcon.On)
                    ic.addPixmap(accent_ic.pixmap(QSize(22,22)), QIcon.Active, QIcon.On)
                    btn.setIcon(ic)
                except:
                    btn.setIcon(get_action_icon(act, btn))
            self.top_bar.btn_back.setIcon(get_action_icon("back", self.top_bar.btn_back))
            self.top_bar.btn_fwd.setIcon(get_action_icon("forward", self.top_bar.btn_fwd))
            self.launch_view.launch_btn.setIcon(get_action_icon("launch", None, color=_acc_text))
            self.btn_grid.setIcon(get_action_icon("instances", self.btn_grid))
            self.btn_add.setIcon(get_action_icon("download", self.btn_add))
        except: pass

    def _on_theme_changed(self, theme):
        from launcher.assets import clear_tinted_cache
        clear_tinted_cache()
        self.setStyleSheet(theme.qss())
        self._refresh_theme_icons()
        self.instance_view.set_instances(self.app.instance_manager.list())
        self._filter_instances()

    def _open_global_settings(self):
        d=QDialog(self); d.setWindowTitle("Settings"); d.resize(700,540)
        lay=QVBoxLayout(d)
        from ui import SettingsPage
        page=SettingsPage()
        page.set_values({"java_path": self.app.config.get("java_path",""), "game_directory": self.app.config.get("game_directory",""), "ram_gb": self.app.config.get("ram_gb",2), "custom_jvm_args": self.app.config.get("custom_jvm_args","")})
        page.theme_changed.connect(self._on_theme_changed)
        from PySide6.QtWidgets import QComboBox as CB, QCheckBox
        from launcher.theme_manager import list_themes, apply_theme_file
        row=QHBoxLayout(); row.addWidget(QLabel("Theme:"))
        cb=CB()
        themes=list_themes()
        for stem,name,path in themes:
            cb.addItem(name, str(path))
        row.addWidget(cb,1)
        lay.addLayout(row)
        warn=QLabel("⚠️ Light mode is buggy and not polished in this version — use Dark for best experience. Light may show white icons/lag.")
        warn.setObjectName("caption")
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#f59e0b; background:#fffbeb; border:1px solid #fcd34d; border-radius:8px; padding:6px 8px;")
        warn.setVisible(False)
        lay.addWidget(warn)
        def on_theme():
            p=Path(cb.currentData())
            if p.exists():
                t=apply_theme_file(p)
                self._on_theme_changed(t)
                is_light="light" in p.stem.lower() or "light" in cb.currentText().lower()
                warn.setVisible(is_light)
                if is_light:
                    # also disable animations for light to reduce lag
                    t.animations=False
        cb.currentIndexChanged.connect(on_theme)
        # init visibility
        try:
            cur=Path(cb.currentData())
            if cur and "light" in cur.stem.lower():
                warn.setVisible(True)
        except: pass
        # tray + logs options — apply logs instantly, not just on reopen
        tray_cb=QCheckBox("Minimize to tray when Minecraft running")
        tray_cb.setChecked(bool(self.app.config.get("minimize_to_tray", True)))
        logs_cb=QCheckBox("Show logs on main tab")
        logs_cb.setChecked(bool(self.app.config.get("show_logs_on_main", False)))
        lay.addWidget(tray_cb); lay.addWidget(logs_cb)
        def _apply_logs_live(checked):
            self.app.config.set("show_logs_on_main", bool(checked))
            self._apply_logs_setting()
        logs_cb.toggled.connect(_apply_logs_live)
        tray_cb.toggled.connect(lambda c: self.app.config.set("minimize_to_tray", bool(c)))
        def on_save(s):
            s["minimize_to_tray"]=bool(tray_cb.isChecked())
            s["show_logs_on_main"]=bool(logs_cb.isChecked())
            self.core.save_settings(s)
            self._apply_logs_setting()
            self.setStyleSheet(get_theme().qss())
            d.accept()
        page.save_clicked.connect(on_save)
        lay.addWidget(page)
        d.exec(); self.setStyleSheet(get_theme().qss()); self._apply_logs_setting()

    def _on_log(self, text):
        if hasattr(self, 'launch_view') and self.launch_view.log_view.isVisible():
            self.launch_view.log_view.append(text)

    def _health_check(self):
        if not self.selected_instance: return
        from launcher.health import health_check, auto_fix
        report=health_check(self.selected_instance, self.app.java_manager)
        dlg=QDialog(self); dlg.setWindowTitle(f"Health — {self.selected_instance.name}"); lay=QVBoxLayout(dlg)
        txt=QTextEdit(); txt.setReadOnly(True)
        lines=[]
        for sev,msg,fix in report:
            lines.append(f"[{sev}] {msg}" + (f"  Fix: {fix}" if fix else ""))
        if not report: lines=["[OK] No issues found."]
        txt.setText("\n".join(lines)); lay.addWidget(txt,1)
        row=QHBoxLayout()
        fix_btn=QPushButton("Auto-fix"); fix_btn.setIcon(get_action_icon("health",self))
        def do_fix():
            fixed=auto_fix(self.selected_instance, report, self.app.java_manager, self)
            QMessageBox.information(self,"Health", f"Fixed {fixed} issue(s)."); dlg.accept()
        row.addWidget(fix_btn); row.addStretch()
        close=QPushButton("Close"); close.clicked.connect(dlg.accept); row.addWidget(close)
        lay.addLayout(row)
        if not any(f for _,_,f in report if f): fix_btn.setEnabled(False)
        else: fix_btn.clicked.connect(do_fix)
        dlg.resize(560,380); dlg.exec()

    def _history_start(self, inst):
        import time
        self._launch_start=time.time(); self._launch_inst_ref=inst
    def _on_process_started(self):
        self.statusBar().showMessage("Minecraft running...")
        self.launch_view.set_running(True)
        if self.app.config.get("minimize_to_tray", True) and self._tray and self._tray.isVisible() or True:
            try:
                if self.app.config.get("minimize_to_tray"):
                    self.hide()
                    if self._tray: self._tray.show()
            except: pass
    def _on_microsoft_code(self, code, uri, expires):
        # Show device code dialog and auto-open browser (secure OAuth2, no password)
        try:
            if self._ms_dialog and self._ms_dialog.isVisible():
                try: self._ms_dialog.close()
                except: pass
        except: pass
        try:
            from ui import MicrosoftDeviceDialog
            dlg=MicrosoftDeviceDialog(code, uri, expires, self)
            self._ms_dialog=dlg
            dlg.rejected.connect(lambda: self.core.cancel_microsoft_login())
            dlg.show()
            # Ensure browser opens even if dialog blocks
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl, QTimer
            QTimer.singleShot(400, lambda: QDesktopServices.openUrl(QUrl(uri)))
        except Exception as e:
            QMessageBox.warning(self,"Microsoft Login", f"Open this URL: {uri}\nCode: {code}\nError: {e}")
            try:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl(uri))
            except: pass

    def _on_microsoft_success(self, acc):
        try:
            if self._ms_dialog:
                self._ms_dialog.accept()
                self._ms_dialog=None
        except: pass
        try: self.refresh_accounts()
        except: pass
        try: self.accounts_page.refresh()
        except: pass
        QMessageBox.information(self,"Microsoft Login", f"Signed in as {acc.username}\nOwnership verified.")
        try:
            self.core.config.set("selected_profile", acc.uuid)
        except: pass
        self.refresh_accounts()

    def _on_microsoft_failed(self, msg):
        try:
            if self._ms_dialog:
                self._ms_dialog.reject()
                self._ms_dialog=None
        except: pass
        if "does not own" in msg or "Minecraft account required" in msg:
            QMessageBox.warning(self,"No Minecraft License", msg + "\n\nThis account does not own Java Edition and cannot launch.")
        else:
            QMessageBox.warning(self,"Microsoft Login Failed", msg)

    def _on_process_finished(self, code):
        self.statusBar().showMessage(f"Exited ({code})",5000)
        self.launch_view.set_running(False)
        try: self.show(); self.showNormal()
        except: pass
        try:
            if self._tray: self._tray.hide()
        except: pass
        try:
            import time, json
            inst=getattr(self,'_launch_inst_ref', self.selected_instance)
            if inst and hasattr(self,'_launch_start'):
                dur=time.time()-self._launch_start
                inst.total_playtime+=dur; inst.save()
                hist_path=inst.path / "launch_history.json"
                hist=[]
                if hist_path.exists():
                    try: hist=json.loads(hist_path.read_text(encoding="utf-8"))
                    except: hist=[]
                hist.append({"time": time.strftime("%Y-%m-%d %H:%M"), "duration": int(dur), "exit_code": code, "crashed": code!=0})
                hist=hist[-50:]
                hist_path.write_text(json.dumps(hist, indent=2), encoding="utf-8")
                self._update_status()
        except: pass
