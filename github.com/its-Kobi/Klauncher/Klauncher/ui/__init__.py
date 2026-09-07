import sys, hashlib
from pathlib import Path
from typing import List, Optional, Dict

from PySide6.QtCore import Qt, Signal, Slot, QSize, QUrl, QTimer, QPropertyAnimation, QEasingCurve, QByteArray, QParallelAnimationGroup, QRect
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QPainterPath, QTextCursor, QDesktopServices, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame, QListWidget, QListWidgetItem,
    QLineEdit, QSpinBox, QComboBox, QFileDialog, QTextEdit, QMessageBox,
    QSizePolicy, QSpacerItem, QGroupBox, QFormLayout, QProgressBar, QCheckBox,
    QDialog, QDialogButtonBox, QScrollArea, QGridLayout, QStyle, QStyleOption,
    QStyledItemDelegate, QAbstractItemView, QListView, QToolButton, QMenu, QGraphicsOpacityEffect, QColorDialog, QSystemTrayIcon
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from core import LauncherCore
from launcher.profiles import Profile
from launcher.java_detector import discover_java_installations
from launcher.theme import get_theme, save_theme, Theme, DEFAULT_THEME
from launcher.assets import icon_for_nav, icon_for_loader, get_icon, load_icon, tinted_icon
from launcher.skin_cache import get_skin_cache

# --- small animation helper ---
def fade_in(widget, duration=180):
    if not get_theme().animations:
        widget.show()
        widget.setGraphicsEffect(None)
        # ensure visible if previous effect left opacity 0
        try:
            widget.setStyleSheet(widget.styleSheet())
        except:
            pass
        return
    # clear any previous effect that may keep opacity 0
    try:
        widget.setGraphicsEffect(None)
    except:
        pass
    eff = QGraphicsOpacityEffect(widget)
    eff.setOpacity(0)
    widget.setGraphicsEffect(eff)
    widget.show()
    widget.raise_()
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0); anim.setEndValue(1)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    # keep reference to prevent GC
    widget._fade_anim = anim
    def _on_finished():
        try:
            widget.setGraphicsEffect(None)
        except:
            pass
        try:
            delattr(widget, "_fade_anim")
        except:
            pass
    anim.finished.connect(_on_finished)
    anim.start()

def _enable_black_titlebar(win):
    try:
        import ctypes
        hwnd=int(win.winId())
        for attr in (20, 19):
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
                break
            except: pass
        try:
            DWMWA_CAPTION_COLOR=35
            col=0x00000000
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(ctypes.c_int(col)), ctypes.sizeof(ctypes.c_int))
        except: pass
    except: pass

class AvatarLabel(QLabel):
    """Real Minecraft skin head, cached, async. Fallback to neutral avatar."""
    def __init__(self, size=48, parent=None):
        super().__init__(parent)
        self._size=size
        self.setFixedSize(size,size)
        self.setScaledContents(False)
        self._uuid=""
        self._username=""
        self._fallback_pm=None
        self._build_fallback()
        self.setPixmap(self._fallback_pm)

    def _build_fallback(self):
        pm=QPixmap(self._size,self._size)
        pm.fill(Qt.transparent)
        p=QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        # neutral slate circle with person icon
        p.setBrush(QBrush(QColor("#252e42")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0,0,self._size,self._size, self._size*0.28, self._size*0.28)
        p.setPen(QColor("#8a92a8"))
        p.setFont(QFont("Segoe UI", max(10, self._size//4)))
        p.drawText(pm.rect(), Qt.AlignCenter, "◯")
        p.end()
        self._fallback_pm=pm

    def set_profile(self, username: str, uuid: str):
        self._username=username or ""
        self._uuid=uuid or ""
        if not uuid:
            self.setPixmap(self._fallback_pm)
            return
        cache=get_skin_cache()
        # check cache instantly
        pm=cache.get_cached(uuid)
        if pm:
            self._set_pm(pm)
            return
        # async fetch
        cache.fetched.connect(self._on_fetched)
        cache.request(uuid, username)
        # keep fallback until fetched
        self.setPixmap(self._fallback_pm)

    def _on_fetched(self, uuid, pm):
        if uuid != self._uuid or pm is None:
            return
        try:
            from launcher.skin_cache import get_skin_cache
            get_skin_cache().fetched.disconnect(self._on_fetched)
        except: pass
        self._set_pm(pm)

    def _set_pm(self, pm: QPixmap):
        # pm is avatar head 64px from crafatar - scale and round
        size=self._size
        rounded=QPixmap(size,size)
        rounded.fill(Qt.transparent)
        p=QPainter(rounded)
        p.setRenderHint(QPainter.Antialiasing)
        # clip to rounded rect
        path=QPainterPath()
        path.addRoundedRect(0,0,size,size, size*0.28, size*0.28)
        p.setClipPath(path)
        # scale with smooth
        scaled=pm.scaled(size,size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        # center crop
        x=(scaled.width()-size)//2
        y=(scaled.height()-size)//2
        p.drawPixmap(0,0, scaled, x, y, size, size)
        # subtle inner border
        p.setClipping(False)
        p.setPen(QPen(QColor(0,0,0,40),1))
        p.drawRoundedRect(0.5,0.5,size-1,size-1,size*0.28,size*0.28)
        p.end()
        self.setPixmap(rounded)

    def set_fallback(self, username: str=""):
        self.setPixmap(self._fallback_pm)

# Sidebar
class Sidebar(QFrame):
    nav_clicked=Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(216)
        lay=QVBoxLayout(self)
        lay.setContentsMargins(14,18,14,14)
        lay.setSpacing(6)
        # brand row with logo
        brand_row=QHBoxLayout()
        brand_row.setSpacing(10)
        logo=QLabel()
        icon=get_icon("Klauncher_logo")
        if not icon.isNull():
            logo.setPixmap(icon.pixmap(QSize(28,28)))
        else:
            logo.setText("◈")
            logo.setStyleSheet("font-size: 22px;")
        brand_row.addWidget(logo)
        col=QVBoxLayout()
        col.setSpacing(0)
        title=QLabel("KLauncher")
        title.setObjectName("brand")
        col.addWidget(title)
        sub=QLabel("MINECRAFT")
        sub.setObjectName("brandSub")
        col.addWidget(sub)
        brand_row.addLayout(col)
        brand_row.addStretch()
        lay.addLayout(brand_row)
        lay.addSpacing(14)
        self.btns={}
        for name in ["Play","Versions","Profiles","Settings"]:
            btn=QPushButton(f"  {name}")
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setIcon(icon_for_nav(name.lower(), self))
            btn.setIconSize(QSize(18,18))
            btn.clicked.connect(lambda checked, n=name: self.nav_clicked.emit(n))
            self.btns[name]=btn
            lay.addWidget(btn)
        lay.addStretch()
        # bottom meta
        self.profile_chip=QLabel("No profile")
        self.profile_chip.setObjectName("caption")
        self.profile_chip.setWordWrap(True)
        self.version_chip=QLabel("No version")
        self.version_chip.setObjectName("caption")
        self.version_chip.setWordWrap(True)
        lay.addWidget(self.profile_chip)
        lay.addWidget(self.version_chip)
        lay.addSpacing(4)
    def set_active(self, name: str):
        for k,b in self.btns.items():
            b.setChecked(k==name)
    def refresh_icons(self):
        for name, btn in self.btns.items():
            btn.setIcon(icon_for_nav(name.lower(), self))

# Play Page - premium hero layout
class PlayPage(QWidget):
    play_clicked=Signal()
    change_version=Signal()
    change_profile=Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        root=QVBoxLayout(self)
        root.setContentsMargins(32,28,32,28)
        root.setSpacing(18)
        # header
        hdr=QVBoxLayout()
        hdr.setSpacing(4)
        t=QLabel("Ready to play")
        t.setObjectName("pageTitle")
        hdr.addWidget(t)
        s=QLabel("Select your identity and universe, then launch")
        s.setObjectName("pageSub")
        hdr.addWidget(s)
        root.addLayout(hdr)
        # hero card
        hero=QFrame(); hero.setObjectName("panel")
        hl=QHBoxLayout(hero); hl.setContentsMargins(20,20,20,20); hl.setSpacing(18)
        # profile card compact
        self.profile_card=QFrame(); self.profile_card.setObjectName("card")
        self.profile_card.setFixedWidth(260)
        pl=QHBoxLayout(self.profile_card); pl.setContentsMargins(14,14,14,14); pl.setSpacing(12)
        self.avatar=AvatarLabel(52)
        pl.addWidget(self.avatar)
        info=QVBoxLayout(); info.setSpacing(2)
        self.profile_name=QLabel("No profile")
        self.profile_name.setObjectName("cardTitle")
        info.addWidget(self.profile_name)
        self.profile_sub=QLabel("Offline • —")
        self.profile_sub.setObjectName("caption")
        info.addWidget(self.profile_sub)
        self.profile_tag=QLabel("Selected")
        self.profile_tag.setObjectName("caption")
        self.profile_tag.setStyleSheet("background:#1e2a3a; color:#6fb3ff; padding:2px 6px; border-radius:6px; font-size:10px; font-weight:700;")
        info.addWidget(self.profile_tag, alignment=Qt.AlignLeft)
        pl.addLayout(info)
        hl.addWidget(self.profile_card)
        # version card
        self.version_card=QFrame(); self.version_card.setObjectName("card")
        vl=QVBoxLayout(self.version_card); vl.setContentsMargins(16,16,16,16); vl.setSpacing(8)
        row=QHBoxLayout(); row.setSpacing(8)
        self.loader_icon=QLabel()
        self.loader_icon.setFixedSize(28,28)
        self.loader_icon.setScaledContents(True)
        row.addWidget(self.loader_icon)
        col=QVBoxLayout(); col.setSpacing(0)
        self.version_label=QLabel("No version")
        self.version_label.setObjectName("cardTitle")
        col.addWidget(self.version_label)
        self.version_sub=QLabel("—")
        self.version_sub.setObjectName("caption")
        col.addWidget(self.version_sub)
        row.addLayout(col)
        row.addStretch()
        self.loader_badge=QLabel("VANILLA")
        self.loader_badge.setObjectName("badge")
        row.addWidget(self.loader_badge)
        vl.addLayout(row)
        # change buttons
        br=QHBoxLayout()
        self.change_profile_btn=QPushButton("Switch Profile")
        self.change_profile_btn.setObjectName("ghostButton")
        self.change_profile_btn.clicked.connect(self.change_profile)
        self.change_version_btn=QPushButton("Change Version")
        self.change_version_btn.setObjectName("ghostButton")
        self.change_version_btn.clicked.connect(self.change_version)
        br.addWidget(self.change_profile_btn); br.addWidget(self.change_version_btn); br.addStretch()
        vl.addLayout(br)
        hl.addWidget(self.version_card, 1)
        root.addWidget(hero)
        # actions row - play prominent but not dominating
        actions=QFrame(); actions.setStyleSheet("background: transparent; border: none;")
        al=QHBoxLayout(actions); al.setContentsMargins(0,0,0,0); al.setSpacing(12)
        self.play_button=QPushButton("  PLAY")
        self.play_button.setObjectName("playButton")
        self.play_button.setFixedHeight(52)
        self.play_button.setIcon(get_icon("Play_icon"))
        self.play_button.setIconSize(QSize(18,18))
        self.play_button.clicked.connect(self.play_clicked)
        al.addWidget(self.play_button)
        self.cancel_button=QPushButton("Cancel")
        self.cancel_button.setObjectName("secondaryButton")
        self.cancel_button.setVisible(False)
        al.addWidget(self.cancel_button)
        al.addStretch()
        self.java_chip=QLabel("Java: detecting…")
        self.java_chip.setObjectName("caption")
        al.addWidget(self.java_chip)
        root.addWidget(actions)
        # status
        status=QFrame(); status.setObjectName("panel")
        sl=QHBoxLayout(status); sl.setContentsMargins(16,12,16,12)
        self.status_label=QLabel("Ready")
        self.status_label.setObjectName("muted")
        sl.addWidget(self.status_label)
        sl.addStretch()
        self.progress=QProgressBar(); self.progress.setVisible(False); self.progress.setFixedHeight(6); self.progress.setTextVisible(False)
        root.addWidget(status)
        root.addWidget(self.progress)
        # log
        log_head=QHBoxLayout()
        log_head.addWidget(QLabel("Log"))
        log_head.addStretch()
        clear=QPushButton("Clear")
        clear.setObjectName("ghostButton")
        log_head.addWidget(clear)
        root.addLayout(log_head)
        self.log_view=QTextEdit(); self.log_view.setObjectName("logView"); self.log_view.setReadOnly(True); self.log_view.setFixedHeight(140)
        clear.clicked.connect(lambda: self.log_view.clear())
        root.addWidget(self.log_view)
        root.addStretch()

    def set_profile(self, username: str, uuid: str=""):
        if username and username!="None":
            self.profile_name.setText(username)
            self.profile_sub.setText(f"Offline • {uuid[:8]}…")
            self.avatar.set_profile(username, uuid)
            self.profile_tag.setVisible(True)
        else:
            self.profile_name.setText("No profile")
            self.profile_sub.setText("Offline • —")
            self.avatar.set_fallback()
            self.profile_tag.setVisible(False)

    def set_version(self, version: str, kind: str="vanilla"):
        if version and version!="None":
            self.version_label.setText(version)
            self.version_sub.setText(f"{kind.capitalize()} • Ready")
            self.loader_badge.setText(kind.upper())
            colors={"vanilla":("#1e2a3a","#6fb3ff"),"fabric":("#2a2438","#c2a6ff"),"forge":("#332a1a","#ffb86a"),"quilt":("#3a2430","#ff8ac6"),"optifine":("#1e3320","#7ed67a"),"custom":("#2a2a2a","#c8c8d0")}
            bg,fg=colors.get(kind.lower(), colors["vanilla"])
            self.loader_badge.setStyleSheet(f"background:{bg};color:{fg};padding:3px 8px;border-radius:7px;font-size:10px;font-weight:700;")
            icon=icon_for_loader(kind)
            if not icon.isNull():
                self.loader_icon.setPixmap(icon.pixmap(QSize(28,28)))
            else:
                self.loader_icon.setText("")
        else:
            self.version_label.setText("No version")
            self.version_sub.setText("—")
            self.loader_badge.setText("—")
            self.loader_icon.setPixmap(QPixmap())

    def set_status(self, text: str):
        self.status_label.setText(text)
    def set_java_status(self, text: str):
        self.java_chip.setText(text)
    def set_progress(self, value: int):
        self.progress.setVisible(True); self.progress.setValue(value)
        if value>=100:
            QTimer.singleShot(1200, lambda: self.progress.setVisible(False))
    def set_launching(self, launching: bool):
        self.play_button.setVisible(not launching)
        self.cancel_button.setVisible(launching)
        self.cancel_button.setText("Cancel Launch" if launching else "Cancel")
    def append_log(self, text: str):
        self.log_view.append(text); self.log_view.moveCursor(QTextCursor.End)

# VersionCard retains but modernized via theme already
class VersionCard(QFrame):
    selected=Signal(str,str)
    request_context=Signal(dict, object)
    def __init__(self, version_info: dict, parent=None):
        super().__init__(parent)
        self.version_info=version_info
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        layout=QHBoxLayout(self)
        layout.setContentsMargins(14,12,14,12); layout.setSpacing(12)
        left=QVBoxLayout(); left.setSpacing(2)
        title=QLabel(version_info["id"]); title.setObjectName("cardTitle"); left.addWidget(title)
        meta=QLabel(f"{version_info.get('type','unknown')}  •  {version_info['source']}")
        meta.setObjectName("caption"); left.addWidget(meta)
        layout.addLayout(left,1)
        vid=version_info["id"].lower()
        kind="vanilla"
        if "optifine" in vid: kind="optifine"
        elif "fabric" in vid: kind="fabric"
        elif "quilt" in vid: kind="quilt"
        elif "forge" in vid: kind="forge"
        j=version_info.get("json") or {}
        for lib in j.get("libraries") or []:
            n=str(lib.get("name","")).lower()
            if "fabric-loader" in n: kind="fabric"; break
            if "quilt-loader" in n: kind="quilt"; break
            if "forge" in n: kind="forge"; break
            if "optifine" in n: kind="optifine"; break
        badge=QLabel(kind.upper()); badge.setObjectName("badge"); layout.addWidget(badge)
        colors={"vanilla":("#1e2a3a","#6fb3ff"),"optifine":("#1e3320","#7ed67a"),"fabric":("#2a2438","#c2a6ff"),"quilt":("#3a2430","#ff8ac6"),"forge":("#332a1a","#ffb86a"),"custom":("#2a2a2a","#c8c8d0")}
        bg,fg=colors.get(kind, colors["vanilla"])
        badge.setStyleSheet(f"background:{bg};color:{fg};padding:4px 8px;border-radius:8px;font-size:10px;font-weight:700;")
        icon_lab=QLabel()
        icon_lab.setFixedSize(22,22); icon_lab.setScaledContents(True)
        ic=icon_for_loader(kind)
        if not ic.isNull():
            icon_lab.setPixmap(ic.pixmap(QSize(22,22)))
        layout.addWidget(icon_lab)
        play=QPushButton("Play"); play.setObjectName("secondaryButton"); play.clicked.connect(lambda: self.selected.emit(version_info["id"], version_info["source"])); layout.addWidget(play)
    def mousePressEvent(self, event):
        if event.button()==Qt.LeftButton:
            self.selected.emit(self.version_info["id"], self.version_info["source"])
        elif event.button()==Qt.RightButton:
            self.request_context.emit(self.version_info, event.globalPos())
        super().mousePressEvent(event)
    def contextMenuEvent(self, event):
        self.request_context.emit(self.version_info, event.globalPos()); event.accept()

class VersionsPage(QWidget):
    add_clicked=Signal()
    version_selected=Signal(str,str)
    version_context_requested=Signal(dict, object)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_versions=[]
        main=QVBoxLayout(self); main.setContentsMargins(22,22,22,22); main.setSpacing(14)
        hdr=QHBoxLayout()
        title=QLabel("Versions"); title.setObjectName("pageTitle"); hdr.addWidget(title); hdr.addStretch()
        add=QPushButton(" Add Version"); add.setObjectName("secondaryButton"); add.setIcon(get_icon("folder_icon")); add.clicked.connect(self.add_clicked); hdr.addWidget(add)
        main.addLayout(hdr)
        ctrl=QHBoxLayout()
        self.search_edit=QLineEdit(); self.search_edit.setPlaceholderText("Search versions…"); self.search_edit.textChanged.connect(self._apply_filters); ctrl.addWidget(self.search_edit,2)
        self.filter_combo=QComboBox(); self.filter_combo.addItems(["All","Releases","Snapshots","Installed","Custom / Community","Modded (Fabric/Forge/Quilt/OptiFine)"]); self.filter_combo.currentTextChanged.connect(self._apply_filters); ctrl.addWidget(self.filter_combo,1)
        self.sort_combo=QComboBox(); self.sort_combo.addItems(["Newest first","Oldest first","Name A→Z","Name Z→A"]); self.sort_combo.currentTextChanged.connect(self._apply_filters); ctrl.addWidget(self.sort_combo,1)
        main.addLayout(ctrl)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        self.container=QWidget(); self.lay=QVBoxLayout(self.container); self.lay.setContentsMargins(0,0,0,0); self.lay.setSpacing(8); self.lay.addStretch()
        self.scroll.setWidget(self.container); self.scroll.viewport().setStyleSheet("background: transparent; border: none;"); main.addWidget(self.scroll)
        self.loading=QLabel("Loading…"); self.loading.setObjectName("caption"); self.loading.setVisible(False); main.addWidget(self.loading)
    def set_versions(self, versions):
        self.all_versions=versions; self._apply_filters()
    def _apply_filters(self):
        while self.lay.count()>1:
            it=self.lay.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        filtered=self.all_versions.copy()
        q=self.search_edit.text().lower()
        if q: filtered=[v for v in filtered if q in v["id"].lower()]
        f=self.filter_combo.currentText()
        if f=="Releases": filtered=[v for v in filtered if v.get("type")=="release"]
        elif f=="Snapshots": filtered=[v for v in filtered if v.get("type")=="snapshot"]
        elif f=="Installed": filtered=[v for v in filtered if v.get("source") in ("klauncher","external")]
        elif f=="Custom / Community": filtered=[v for v in filtered if v.get("type") not in ("release","snapshot")]
        elif f=="Modded (Fabric/Forge/Quilt/OptiFine)":
            def is_mod(v):
                if any(x in v["id"].lower() for x in ("fabric","forge","quilt","optifine")): return True
                for lib in (v.get("json") or {}).get("libraries") or []:
                    if any(x in str(lib.get("name","")).lower() for x in ("fabric-loader","quilt-loader","forge","optifine")): return True
                return False
            filtered=[v for v in filtered if is_mod(v)]
        s=self.sort_combo.currentText()
        if s=="Newest first": filtered.sort(key=lambda x: x.get("id",""), reverse=True)
        elif s=="Oldest first": filtered.sort(key=lambda x: x.get("id",""))
        elif s=="Name A→Z": filtered.sort(key=lambda x: x.get("id","").lower())
        elif s=="Name Z→A": filtered.sort(key=lambda x: x.get("id","").lower(), reverse=True)
        if not filtered:
            e=QLabel("No versions match the current filter."); e.setObjectName("caption"); self.lay.insertWidget(0,e)
        else:
            for v in filtered:
                c=VersionCard(v); c.selected.connect(self.version_selected); c.request_context.connect(self.version_context_requested); self.lay.insertWidget(self.lay.count()-1,c)
    def set_loading(self, loading: bool): self.loading.setVisible(loading)

# AddVersionDialog (reuse previous)
class AddVersionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Version"); self.setModal(True); self.resize(460,260)
        lay=QVBoxLayout(self); lay.setSpacing(12)
        t=QLabel("Add Version"); t.setObjectName("pageTitle"); lay.addWidget(t)
        s=QLabel("Select loader and Minecraft version to install"); s.setObjectName("pageSub"); lay.addWidget(s)
        form=QFormLayout(); form.setSpacing(10)
        self.type_combo=QComboBox()
        for tid, label in [("vanilla","Vanilla"),("fabric","Fabric"),("forge","Forge"),("quilt","Quilt"),("optifine","OptiFine"),("custom","Custom")]:
            self.type_combo.addItem(label, tid)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed); form.addRow("Loader / Type:", self.type_combo)
        self.mc_combo=QComboBox(); self.mc_combo.setPlaceholderText("Loading..."); self.mc_combo.currentIndexChanged.connect(self._on_mc_changed); form.addRow("Minecraft Version:", self.mc_combo)
        self.loader_combo=QComboBox(); self.loader_combo.setPlaceholderText("Loader version"); form.addRow("Loader Version:", self.loader_combo)
        lay.addLayout(form)
        self.status_label=QLabel(""); self.status_label.setObjectName("caption"); self.status_label.setWordWrap(True); lay.addWidget(self.status_label)
        btns=QHBoxLayout()
        cancel=QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        self.ok_btn=QPushButton("Install"); self.ok_btn.setObjectName("playButton"); self.ok_btn.clicked.connect(self._on_install); self.ok_btn.setEnabled(False)
        btns.addStretch(); btns.addWidget(cancel); btns.addWidget(self.ok_btn); lay.addLayout(btns)
        self._fetch_thread=None; self._on_type_changed()
    def _set_status(self, txt, error=False):
        self.status_label.setText(txt); self.status_label.setStyleSheet("color: #ff6b6b;" if error else "color: #8a92a8;")
    def _on_type_changed(self):
        loader=self.type_combo.currentData(); show=loader in ("fabric","forge","quilt","optifine")
        self.loader_combo.setVisible(show); self.mc_combo.clear(); self.loader_combo.clear(); self.ok_btn.setEnabled(False); self._set_status("Fetching Minecraft versions..."); self._fetch_mc_versions(loader)
    def _on_mc_changed(self):
        loader=self.type_combo.currentData()
        if loader not in ("fabric","forge","quilt","optifine"):
            self.ok_btn.setEnabled(self.mc_combo.currentData() is not None); return
        mc=self.mc_combo.currentData()
        if not mc: return
        self.loader_combo.clear(); self._set_status("Fetching loader versions..."); self._fetch_loader_versions(loader, mc)
    def _fetch_mc_versions(self, loader: str):
        from PySide6.QtCore import QThread, Signal
        if self._fetch_thread and self._fetch_thread.isRunning():
            try: self._fetch_thread.terminate()
            except: pass
        class Worker(QThread):
            done=Signal(list); err=Signal(str)
            def __init__(self, loader): super().__init__(); self.loader=loader
            def run(self):
                try:
                    from launcher.providers.registry import get_provider
                    self.done.emit(get_provider(self.loader).fetch_minecraft_versions())
                except Exception as e: self.err.emit(str(e))
        self._fetch_thread=Worker(loader)
        self._fetch_thread.done.connect(self._on_mc_fetched)
        self._fetch_thread.err.connect(lambda e: self._set_status(f"Failed to fetch versions: {e}", True))
        self._fetch_thread.start()
    def _on_mc_fetched(self, vers):
        self.mc_combo.clear()
        for v in vers[:200]: self.mc_combo.addItem(v, v)
        if vers:
            self._set_status(f"Found {len(vers)} Minecraft versions")
            self.ok_btn.setEnabled(self.type_combo.currentData() in ("vanilla","custom"))
        else: self._set_status("No versions found", True)
        self._on_mc_changed()
    def _fetch_loader_versions(self, loader: str, mc: str):
        from PySide6.QtCore import QThread, Signal
        class Worker(QThread):
            done=Signal(list); err=Signal(str)
            def __init__(self, loader, mc): super().__init__(); self.loader=loader; self.mc=mc
            def run(self):
                try:
                    from launcher.providers.registry import get_provider
                    self.done.emit(get_provider(self.loader).fetch_loader_versions(self.mc))
                except Exception as e: self.err.emit(str(e))
        w=Worker(loader, mc)
        w.done.connect(self._on_loader_fetched); w.err.connect(lambda e: self._set_status(f"Loader fetch failed: {e}", True)); w.start(); self._loader_worker=w
    def _on_loader_fetched(self, vers):
        self.loader_combo.clear()
        for v in vers[:50]: self.loader_combo.addItem(v, v)
        if vers:
            self._set_status(f"Found {len(vers)} loader versions"); self.ok_btn.setEnabled(True)
        else:
            if self.type_combo.currentData() in ("forge","optifine"):
                self._set_status("No loader data (Forge/OptiFine requires manual install).", True)
            else: self._set_status("No loader versions found", True)
            self.ok_btn.setEnabled(False)
    def _on_install(self):
        if not self.mc_combo.currentData(): self._set_status("Select a Minecraft version", True); return
        loader=self.type_combo.currentData()
        if loader in ("fabric","quilt") and not self.loader_combo.currentData(): self._set_status("Select a loader version", True); return
        self.accept()
    def get_selection(self):
        return {"loader": self.type_combo.currentData(), "minecraft_version": self.mc_combo.currentData(), "loader_version": self.loader_combo.currentData()}
    def get_selected_version_id(self) -> str:
        sel=self.get_selection()
        return sel["minecraft_version"] or ""

class ProgressDialog(QDialog):
    def __init__(self, version_id: str, parent=None):
        super().__init__(parent); self.version_id=version_id; self.setWindowTitle(f"Installing {version_id}"); self.setModal(False); self.setMinimumWidth(420)
        lay=QVBoxLayout(self); lay.setSpacing(12)
        t=QLabel(f"Installing {version_id}"); t.setObjectName("pageTitle"); lay.addWidget(t)
        self.progress_bar=QProgressBar(); self.progress_bar.setRange(0,100); lay.addWidget(self.progress_bar)
        self.status_label=QLabel("Preparing…"); self.status_label.setObjectName("caption"); lay.addWidget(self.status_label)
        self.log_view=QTextEdit(); self.log_view.setReadOnly(True); self.log_view.setFixedHeight(120); lay.addWidget(self.log_view)
        self.close_btn=QPushButton("Close"); self.close_btn.setObjectName("secondaryButton"); self.close_btn.setEnabled(False); self.close_btn.clicked.connect(self.accept); lay.addWidget(self.close_btn, alignment=Qt.AlignRight)
    def update_progress(self, percent: int): self.progress_bar.setValue(percent)
    def append_log(self, message: str): self.log_view.append(message)
    def set_status(self, text: str): self.status_label.setText(text)
    def set_error(self, error_msg: str): self.set_status(f"Error: {error_msg}"); self.append_log(f"ERROR: {error_msg}"); self.close_btn.setEnabled(True)
    def set_finished(self): self.set_status("Completed successfully."); self.progress_bar.setValue(100); self.close_btn.setEnabled(True)

class MicrosoftDeviceDialog(QDialog):
    def __init__(self, user_code: str, verification_uri: str, expires_in: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Microsoft Login")
        self.setModal(True)
        self.resize(420, 200)
        lay=QVBoxLayout(self); lay.setSpacing(12)
        title=QLabel("Login with Microsoft"); title.setObjectName("cardTitle"); lay.addWidget(title)
        info=QLabel("Authenticate directly with Microsoft. KLauncher will never ask for your password."); info.setObjectName("caption"); info.setWordWrap(True); lay.addWidget(info)
        code_row=QHBoxLayout()
        code_label=QLabel(f"Code: {user_code}"); code_label.setObjectName("cardTitle"); code_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        code_row.addWidget(code_label)
        copy_btn=QPushButton("Copy"); copy_btn.setObjectName("ghostButton")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(user_code))
        code_row.addWidget(copy_btn)
        lay.addLayout(code_row)
        uri_label=QLabel(f"Go to: {verification_uri}"); uri_label.setObjectName("caption"); uri_label.setTextInteractionFlags(Qt.TextSelectableByMouse); uri_label.setOpenExternalLinks(True)
        lay.addWidget(uri_label)
        # Countdown
        self.countdown=QLabel(f"Expires in {expires_in//60} min"); self.countdown.setObjectName("caption"); lay.addWidget(self.countdown)
        self._remaining=expires_in
        self._timer=QTimer(self); self._timer.timeout.connect(self._tick); self._timer.start(1000)
        btns=QHBoxLayout()
        open_btn=QPushButton("Open Browser"); open_btn.setObjectName("secondaryButton")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(verification_uri)))
        cancel_btn=QPushButton("Cancel"); cancel_btn.setObjectName("ghostButton"); cancel_btn.clicked.connect(self.reject)
        btns.addWidget(open_btn); btns.addStretch(); btns.addWidget(cancel_btn)
        lay.addLayout(btns)
        # Auto open browser
        QTimer.singleShot(500, lambda: QDesktopServices.openUrl(QUrl(verification_uri)))
    def _tick(self):
        self._remaining-=1
        if self._remaining<=0:
            self._timer.stop()
            self.countdown.setText("Expired")
        else:
            self.countdown.setText(f"Expires in {self._remaining//60}:{self._remaining%60:02d}")

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About KLauncher")
        self.setModal(True)
        self.resize(440, 300)
        self.setStyleSheet(get_theme().qss())
        lay=QVBoxLayout(self); lay.setContentsMargins(24,24,24,24); lay.setSpacing(16)
        # header with logo
        head=QHBoxLayout(); head.setSpacing(12)
        logo=QLabel()
        ic=get_icon("Klauncher_logo")
        if not ic.isNull():
            logo.setPixmap(ic.pixmap(QSize(48,48)))
        head.addWidget(logo)
        title_col=QVBoxLayout(); title_col.setSpacing(2)
        t=QLabel("KLauncher"); t.setObjectName("pageTitle"); title_col.addWidget(t)
        sub=QLabel("Modern Minecraft Launcher"); sub.setObjectName("pageSub"); title_col.addWidget(sub)
        head.addLayout(title_col); head.addStretch()
        lay.addLayout(head)
        # info panel
        panel=QFrame(); panel.setObjectName("panel"); pl=QVBoxLayout(panel); pl.setContentsMargins(16,16,16,16); pl.setSpacing(8)
        ver=QLabel("Version 1.0.0"); ver.setObjectName("cardTitle"); pl.addWidget(ver)
        made=QLabel("Made by KOBI • 2026"); made.setObjectName("caption"); pl.addWidget(made)
        desc=QLabel("A modern, minimal and extensible Minecraft launcher supporting Vanilla, Fabric, Forge, Quilt and Custom clients with secure Microsoft authentication."); desc.setObjectName("caption"); desc.setWordWrap(True); pl.addWidget(desc)
        # custom icon preview
        row=QHBoxLayout()
        ic_lab=QLabel(); ic_lab.setFixedSize(28,28); ic_lab.setScaledContents(True)
        ic=get_icon("custom_icon")
        if not ic.isNull(): ic_lab.setPixmap(ic.pixmap(QSize(28,28)))
        row.addWidget(ic_lab)
        row.addWidget(QLabel("Custom clients use custom_icon.svg — auto-tinted for contrast")); row.addStretch()
        pl.addLayout(row)
        lay.addWidget(panel)
        # footer
        foot=QHBoxLayout()
        git=QPushButton("GitHub"); git.setObjectName("ghostButton"); git.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com")))
        close=QPushButton("Close"); close.setObjectName("secondaryButton"); close.clicked.connect(self.accept)
        foot.addWidget(git); foot.addStretch(); foot.addWidget(close)
        lay.addLayout(foot)

class SplashScreen(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(420, 260)
        self._progress=0
        self._target=0
        self._theme=get_theme()
        screen=QApplication.primaryScreen().geometry() if QApplication.primaryScreen() else None
        if screen:
            self.move(screen.center() - self.rect().center())
        self._timer=QTimer(self); self._timer.timeout.connect(self._step)
        self._timer.start(16)
        self._pulse=0
        self._pulse_timer=QTimer(self); self._pulse_timer.timeout.connect(lambda: (setattr(self, '_pulse', (self._pulse+0.08)%6.28), self.update())); self._pulse_timer.start(32)
        self.show(); self.raise_()

    def _step(self):
        # smooth eased progress
        self._target=min(100, self._target+1.2)
        # ease
        self._progress += (self._target - self._progress)*0.12
        if self._target>=100 and abs(self._progress-100)<0.5:
            self._progress=100
            self._timer.stop(); self._pulse_timer.stop()
        self.update()

    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        # flat minimal card matching new shell
        path=QPainterPath(); path.addRoundedRect(self.rect(), 18, 18)
        p.fillPath(path, QBrush(QColor(self._theme.bg_primary)))
        p.setPen(QPen(QColor(self._theme.border),1)); p.drawPath(path)
        # logo small pulsing
        from launcher.assets import tinted_icon
        scale=1.0+0.04*abs(__import__('math').sin(self._pulse))
        sz=int(56*scale)
        ic=tinted_icon("Klauncher_logo", "#ffffff", QSize(sz,sz))
        if not ic.isNull():
            pm=ic.pixmap(QSize(sz,sz))
            x=(self.width()-sz)//2
            p.drawPixmap(x, 28, pm)
        # title with minecraft font if enabled
        try:
            fam="Minecraft Seven" if self._theme._font_family().count("Minecraft") else "Segoe UI"
        except: fam="Segoe UI"
        p.setPen(QColor(self._theme.text_primary))
        f=QFont(fam, 18, QFont.Bold); p.setFont(f)
        p.drawText(QRect(0, 92, self.width(), 24), Qt.AlignHCenter, "KLauncher")
        f2=QFont("Segoe UI", 8); f2.setLetterSpacing(QFont.AbsoluteSpacing, 1.2); p.setFont(f2)
        p.setPen(QColor(self._theme.text_muted))
        p.drawText(QRect(0, 118, self.width(), 14), Qt.AlignHCenter, "MINECRAFT  •  KOBI 2026")
        # progress bar minimal
        bar_y=188; bar_h=4; bar_rect=QRect(48, bar_y, self.width()-96, bar_h)
        p.setPen(Qt.NoPen); p.setBrush(QColor(self._theme.bg_card)); p.drawRoundedRect(bar_rect, 2,2)
        fill_w=int(bar_rect.width() * self._progress/100)
        if fill_w>0:
            fill=QRect(bar_rect.x(), bar_rect.y(), fill_w, bar_rect.height())
            p.setBrush(QColor(self._theme.accent)); p.drawRoundedRect(fill,2,2)
        p.setPen(QColor(self._theme.text_muted))
        f3=QFont("Segoe UI", 7); p.setFont(f3)
        p.drawText(QRect(0, bar_y+12, self.width(), 12), Qt.AlignHCenter, f"Loading  {int(self._progress)}%")
        p.end()

    def finish_and_close(self):
        # fade out
        eff=QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim=QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220); anim.setStartValue(1); anim.setEndValue(0)
        anim.finished.connect(self.close)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._fade=anim

# Profiles Page — compatible layout: left Offline + creation at bottom, right Microsoft
class ProfilesPage(QWidget):
    profile_created=Signal(str); profile_deleted=Signal(str); profile_selected=Signal(str)
    microsoft_login_requested=Signal()
    microsoft_logout_requested=Signal(str)
    microsoft_selected=Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        outer=QVBoxLayout(self); outer.setContentsMargins(28,24,28,24); outer.setSpacing(12)
        title=QLabel("Accounts"); title.setObjectName("pageTitle"); outer.addWidget(title)
        sub=QLabel("Offline on the left — Microsoft official on the right. Select one to launch."); sub.setObjectName("pageSub"); outer.addWidget(sub)
        content=QHBoxLayout(); content.setSpacing(12); outer.addLayout(content, 1)
        # LEFT: Offline profiles
        left=QFrame(); left.setObjectName("panel")
        ll=QVBoxLayout(left); ll.setContentsMargins(14,14,14,14); ll.setSpacing(10)
        left_title=QLabel("Offline Accounts"); left_title.setObjectName("cardTitle"); ll.addWidget(left_title)
        left_sub=QLabel("Visual skin only — no password"); left_sub.setObjectName("caption"); ll.addWidget(left_sub)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        self.list_container=QWidget(); self.list_layout=QVBoxLayout(self.list_container); self.list_layout.setContentsMargins(0,0,0,0); self.list_layout.setSpacing(8); self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container); self.scroll.viewport().setStyleSheet("background: transparent; border: none;"); self.scroll.setMinimumHeight(180); ll.addWidget(self.scroll, 1)
        self.preview_card=QFrame(); self.preview_card.setObjectName("card")
        pc=QHBoxLayout(self.preview_card); pc.setContentsMargins(12,12,12,12)
        self.preview_avatar=AvatarLabel(48); pc.addWidget(self.preview_avatar)
        info=QVBoxLayout(); info.setSpacing(2)
        self.preview_name=QLabel("Select a profile"); self.preview_name.setObjectName("cardTitle"); info.addWidget(self.preview_name)
        self.preview_uuid=QLabel("—"); self.preview_uuid.setObjectName("caption"); info.addWidget(self.preview_uuid)
        self.preview_offline=QLabel("Offline profile • skin visual only"); self.preview_offline.setObjectName("caption"); info.addWidget(self.preview_offline)
        pc.addLayout(info,1)
        self.delete_btn=QPushButton("Delete"); self.delete_btn.setObjectName("ghostButton"); self.delete_btn.clicked.connect(self._delete_clicked); pc.addWidget(self.delete_btn)
        ll.addWidget(self.preview_card)
        # bottom bar: text + button anchored left bottom
        row=QHBoxLayout()
        self.username_input=QLineEdit(); self.username_input.setPlaceholderText("Username (3-16 letters, numbers, _)")
        create=QPushButton("Create Offline"); create.setObjectName("playButton"); create.clicked.connect(self._create_clicked)
        from launcher.icons import get_action_icon
        create.setIcon(get_action_icon("accounts", self))
        row.addWidget(self.username_input,1); row.addWidget(create)
        ll.addLayout(row)
        content.addWidget(left, 1)
        # RIGHT: Microsoft official auto sign-in
        right=QFrame(); right.setObjectName("panel")
        rl=QVBoxLayout(right); rl.setContentsMargins(14,14,14,14); rl.setSpacing(10)
        ms_title=QLabel("Microsoft — Official"); ms_title.setObjectName("cardTitle"); rl.addWidget(ms_title)
        ms_sub=QLabel("Auto sign-in via Microsoft OAuth2. No password stored in KLauncher. Ownership checked before launch."); ms_sub.setObjectName("caption"); ms_sub.setWordWrap(True); rl.addWidget(ms_sub)
        self.ms_status=QLabel("Not signed in"); self.ms_status.setObjectName("caption"); rl.addWidget(self.ms_status)
        self.ms_list_container=QWidget(); self.ms_layout=QVBoxLayout(self.ms_list_container); self.ms_layout.setContentsMargins(0,0,0,0); self.ms_layout.setSpacing(8); self.ms_layout.addStretch()
        self.ms_scroll=QScrollArea(); self.ms_scroll.setWidgetResizable(True); self.ms_scroll.setFrameShape(QFrame.NoFrame); self.ms_scroll.setWidget(self.ms_list_container); self.ms_scroll.viewport().setStyleSheet("background: transparent; border: none;"); self.ms_scroll.setMinimumHeight(160); rl.addWidget(self.ms_scroll, 1)
        ms_btns=QHBoxLayout()
        self.ms_login_btn=QPushButton("  Sign in with Microsoft"); self.ms_login_btn.setObjectName("playButton"); self.ms_login_btn.setIcon(get_action_icon("accounts", self)); self.ms_login_btn.clicked.connect(lambda: self.microsoft_login_requested.emit())
        self.ms_logout_btn=QPushButton("Log out"); self.ms_logout_btn.setObjectName("ghostButton"); self.ms_logout_btn.clicked.connect(self._ms_logout_clicked)
        self.ms_logout_btn.setVisible(False)
        ms_btns.addWidget(self.ms_login_btn,1); ms_btns.addWidget(self.ms_logout_btn)
        rl.addLayout(ms_btns)
        rl.addStretch()
        content.addWidget(right, 1)
        self._profiles: List[Profile]=[]; self._selected_uuid: Optional[str]=None
        self._ms_accounts: List = []
        self._ms_selected: Optional[str]=None
    def set_profiles(self, profiles: List[Profile]):
        self._profiles=profiles
        while self.list_layout.count()>1:
            it=self.list_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        for p in profiles:
            card=QFrame(); card.setObjectName("card"); card.setCursor(Qt.PointingHandCursor)
            hl=QHBoxLayout(card); hl.setContentsMargins(12,10,12,10)
            av=AvatarLabel(36); av.set_profile(p.username, p.uuid); hl.addWidget(av)
            vl=QVBoxLayout(); vl.setSpacing(0)
            name=QLabel(p.username); name.setObjectName("cardTitle"); vl.addWidget(name)
            uid=QLabel(p.uuid[:8]+"…"); uid.setObjectName("caption"); vl.addWidget(uid)
            hl.addLayout(vl,1)
            sel=QLabel("Offline"); sel.setObjectName("caption"); hl.addWidget(sel)
            card.mousePressEvent=lambda e, u=p.uuid: (self._select(u) if e.button()==Qt.LeftButton else None)
            is_sel=(p.uuid==self._selected_uuid)
            if is_sel: card.setStyleSheet("QFrame#card{border:1px solid #2d7dff;}")
            self.list_layout.insertWidget(self.list_layout.count()-1, card)
        if profiles and self._selected_uuid: self._update_preview()
    def set_microsoft_accounts(self, accounts):
        self._ms_accounts=accounts or []
        while self.ms_layout.count()>1:
            it=self.ms_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        if not self._ms_accounts:
            self.ms_status.setText("Not signed in — offline mode available")
            self.ms_login_btn.setVisible(True)
            self.ms_logout_btn.setVisible(False)
            lbl=QLabel("No Microsoft account"); lbl.setObjectName("caption"); self.ms_layout.insertWidget(0, lbl)
            return
        self.ms_status.setText(f"Signed in: {len(self._ms_accounts)} account(s)")
        self.ms_login_btn.setVisible(True)
        # Show accounts
        for acc in self._ms_accounts:
            card=QFrame(); card.setObjectName("card"); card.setCursor(Qt.PointingHandCursor)
            hl=QHBoxLayout(card); hl.setContentsMargins(12,10,12,10)
            av=AvatarLabel(36); av.set_profile(acc.username, acc.uuid); hl.addWidget(av)
            vl=QVBoxLayout(); vl.setSpacing(0)
            name=QLabel(acc.username); name.setObjectName("cardTitle"); vl.addWidget(name)
            sub=QLabel("Microsoft Account"); sub.setObjectName("caption"); vl.addWidget(sub)
            hl.addLayout(vl,1)
            sel=QLabel("Microsoft"); sel.setObjectName("caption"); hl.addWidget(sel)
            card.mousePressEvent=lambda e, u=acc.uuid: (self._ms_select(u) if e.button()==Qt.LeftButton else None)
            is_sel=(acc.uuid==self._ms_selected or acc.uuid==self._selected_uuid)
            if is_sel: card.setStyleSheet("QFrame#card{border:1px solid #2d7dff;}")
            self.ms_layout.insertWidget(self.ms_layout.count()-1, card)
        # Show logout for selected microsoft
        has_sel = any(a.uuid==self._selected_uuid for a in self._ms_accounts)
        self.ms_logout_btn.setVisible(has_sel)

    def _select(self, uuid: str):
        self._selected_uuid=uuid; self._ms_selected=None; self.profile_selected.emit(uuid); self.microsoft_selected.emit(uuid); self.set_profiles(self._profiles); self.set_microsoft_accounts(self._ms_accounts); self._update_preview()
    def _ms_select(self, uuid: str):
        self._selected_uuid=uuid; self._ms_selected=uuid; self.microsoft_selected.emit(uuid); self.profile_selected.emit(uuid); self.set_profiles(self._profiles); self.set_microsoft_accounts(self._ms_accounts); self._update_preview()
        # Also update preview to show microsoft
        for acc in self._ms_accounts:
            if acc.uuid==uuid:
                self.preview_name.setText(acc.username); self.preview_uuid.setText(acc.uuid); self.preview_avatar.set_profile(acc.username, acc.uuid); self.preview_offline.setText("Microsoft Account"); return
    def _update_preview(self):
        # Check microsoft first if selected is microsoft
        for acc in self._ms_accounts:
            if acc.uuid==self._selected_uuid:
                self.preview_name.setText(acc.username); self.preview_uuid.setText(acc.uuid); self.preview_avatar.set_profile(acc.username, acc.uuid); self.preview_offline.setText("Microsoft Account"); return
        for p in self._profiles:
            if p.uuid==self._selected_uuid:
                self.preview_name.setText(p.username); self.preview_uuid.setText(p.uuid); self.preview_avatar.set_profile(p.username, p.uuid); self.preview_offline.setText("Offline profile • skin visual only"); return
        self.preview_name.setText("Select a profile"); self.preview_uuid.setText("—"); self.preview_avatar.set_fallback(); self.preview_offline.setText("Offline profile • skin visual only")
    def _create_clicked(self):
        u=self.username_input.text().strip()
        if u: self.profile_created.emit(u); self.username_input.clear()
    def _delete_clicked(self):
        if self._selected_uuid:
            # Check if microsoft
            if any(a.uuid==self._selected_uuid for a in self._ms_accounts):
                self.microsoft_logout_requested.emit(self._selected_uuid)
            else:
                self.profile_deleted.emit(self._selected_uuid)
            self._selected_uuid=None
    def _ms_logout_clicked(self):
        if self._selected_uuid and any(a.uuid==self._selected_uuid for a in self._ms_accounts):
            self.microsoft_logout_requested.emit(self._selected_uuid)
            self._selected_uuid=None

# Settings Page - redesigned with sections
class SettingsPage(QWidget):
    save_clicked=Signal(dict); reset_clicked=Signal()
    theme_changed=Signal(Theme)
    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme=get_theme()
        outer=QVBoxLayout(self); outer.setContentsMargins(28,24,28,24); outer.setSpacing(16)
        # scroll for settings
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        container=QWidget(); lay=QVBoxLayout(container); lay.setContentsMargins(0,0,0,0); lay.setSpacing(18)
        # General / Appearance
        gen=QFrame(); gen.setObjectName("panel"); gl=QVBoxLayout(gen); gl.setContentsMargins(16,16,16,16); gl.setSpacing(10)
        ht=QLabel("Appearance"); ht.setObjectName("cardTitle"); gl.addWidget(ht)
        # accent
        row=QHBoxLayout(); row.addWidget(QLabel("Accent"))
        self.accent_btn=QPushButton("Pick"); self.accent_btn.setObjectName("ghostButton"); self.accent_btn.clicked.connect(self._pick_accent)
        self.accent_preview=QLabel(); self.accent_preview.setFixedSize(22,22); self.accent_preview.setStyleSheet(f"background:{self._theme.accent}; border-radius:6px; border:1px solid #222a3a;")
        row.addWidget(self.accent_preview); row.addWidget(self.accent_btn); row.addStretch()
        self.gradient_check=QCheckBox("Background gradient"); self.gradient_check.setChecked(self._theme.use_gradient); self.gradient_check.toggled.connect(self._on_gradient_toggle)
        row.addWidget(self.gradient_check)
        self.anim_check=QCheckBox("Animations"); self.anim_check.setChecked(self._theme.animations); self.anim_check.toggled.connect(self._on_anim_toggle)
        row.addWidget(self.anim_check)
        gl.addLayout(row)
        # gradient colors - smooth clean preview under everything
        grow=QHBoxLayout()
        grow.addWidget(QLabel("Gradient"))
        self.grad_from_btn=QPushButton("From"); self.grad_from_btn.setObjectName("ghostButton"); self.grad_from_btn.clicked.connect(lambda: self._pick_grad("from"))
        self.grad_to_btn=QPushButton("To"); self.grad_to_btn.setObjectName("ghostButton"); self.grad_to_btn.clicked.connect(lambda: self._pick_grad("to"))
        grow.addWidget(self.grad_from_btn); grow.addWidget(self.grad_to_btn); grow.addStretch()
        reset_theme=QPushButton("Reset Theme"); reset_theme.setObjectName("ghostButton"); reset_theme.clicked.connect(self._reset_theme)
        grow.addWidget(reset_theme)
        gl.addLayout(grow)
        # smooth gradient preview (visible under everything)
        self.gradient_preview=QFrame(); self.gradient_preview.setFixedHeight(32); self.gradient_preview.setObjectName("gradientPreview")
        gl.addWidget(self.gradient_preview)
        self._update_gradient_preview()
        lay.addWidget(gen)
        # Minecraft
        mc=QFrame(); mc.setObjectName("panel"); ml=QVBoxLayout(mc); ml.setContentsMargins(16,16,16,16); ml.setSpacing(10)
        ht2=QLabel("Minecraft"); ht2.setObjectName("cardTitle"); ml.addWidget(ht2)
        form=QFormLayout(); form.setSpacing(10)
        self.game_dir_edit=QLineEdit()
        gb=QPushButton("Browse…"); gb.setObjectName("ghostButton"); gb.clicked.connect(self._browse_game_dir)
        glay=QHBoxLayout(); glay.addWidget(self.game_dir_edit,1); glay.addWidget(gb)
        form.addRow("Game Directory:", glay)
        self.ram_spin=QSpinBox(); self.ram_spin.setRange(1,32); self.ram_spin.setSuffix(" GB")
        form.addRow("RAM:", self.ram_spin)
        ml.addLayout(form)
        lay.addWidget(mc)
        # Java
        jf=QFrame(); jf.setObjectName("panel"); jl=QVBoxLayout(jf); jl.setContentsMargins(16,16,16,16); jl.setSpacing(10)
        ht3=QLabel("Java"); ht3.setObjectName("cardTitle"); jl.addWidget(ht3)
        java_row=QHBoxLayout()
        self.java_combo=QComboBox(); self.java_combo.setEditable(True); self.java_combo.setPlaceholderText("Auto-detected Java")
        self.refresh_java_btn=QPushButton("Detect"); self.refresh_java_btn.setObjectName("ghostButton"); self.refresh_java_btn.clicked.connect(self._refresh_java)
        browse_java=QPushButton("Browse…"); browse_java.setObjectName("ghostButton"); browse_java.clicked.connect(self._browse_java)
        java_row.addWidget(self.java_combo,1); java_row.addWidget(self.refresh_java_btn); java_row.addWidget(browse_java)
        jl.addLayout(java_row)
        self.java_info=QLabel(""); self.java_info.setObjectName("caption"); jl.addWidget(self.java_info)
        lay.addWidget(jf)
        # Advanced
        adv=QFrame(); adv.setObjectName("panel"); al=QVBoxLayout(adv); al.setContentsMargins(16,16,16,16); al.setSpacing(10)
        ht4=QLabel("Advanced"); ht4.setObjectName("cardTitle"); al.addWidget(ht4)
        self.custom_args_edit=QLineEdit(); self.custom_args_edit.setPlaceholderText("Additional JVM arguments")
        af=QFormLayout(); af.addRow("JVM Args:", self.custom_args_edit); al.addLayout(af)
        lay.addWidget(adv)
        # About / Info
        about=QFrame(); about.setObjectName("panel"); ab_lay=QVBoxLayout(about); ab_lay.setContentsMargins(16,16,16,16); ab_lay.setSpacing(10)
        ht5=QLabel("About"); ht5.setObjectName("cardTitle"); ab_lay.addWidget(ht5)
        info_row=QHBoxLayout(); info_row.setSpacing(12)
        ab_icon=QLabel(); ab_icon.setFixedSize(32,32); ab_icon.setScaledContents(True)
        ic_ab=get_icon("custom_icon")
        if not ic_ab.isNull(): ab_icon.setPixmap(ic_ab.pixmap(QSize(32,32)))
        info_row.addWidget(ab_icon)
        ab_text=QVBoxLayout(); ab_text.setSpacing(2)
        ab_name=QLabel("KLauncher 1.0.0"); ab_name.setObjectName("cardTitle"); ab_text.addWidget(ab_name)
        ab_made=QLabel("Made by KOBI • 2026"); ab_made.setObjectName("caption"); ab_text.addWidget(ab_made)
        info_row.addLayout(ab_text); info_row.addStretch()
        ab_btn=QPushButton("Info / About"); ab_btn.setObjectName("secondaryButton"); ab_btn.setIcon(get_icon("custom_icon")); ab_btn.clicked.connect(self._show_about)
        info_row.addWidget(ab_btn)
        ab_lay.addLayout(info_row)
        lay.addWidget(about)
        scroll.setWidget(container); scroll.viewport().setStyleSheet("background: transparent; border: none;"); outer.addWidget(scroll)
        save=QPushButton("Save Settings"); save.setObjectName("playButton"); save.clicked.connect(self._save_clicked); outer.addWidget(save, alignment=Qt.AlignRight)
        reset_note=QLabel("Reset removes only KLauncher data, never your .minecraft folder."); reset_note.setObjectName("caption"); reset_note.setWordWrap(True); outer.addWidget(reset_note)
        reset=QPushButton("Reset KLauncher data"); reset.setObjectName("secondaryButton"); reset.clicked.connect(lambda: self.reset_clicked.emit()); outer.addWidget(reset, alignment=Qt.AlignLeft)
        # defer java refresh
        QTimer.singleShot(200, self._refresh_java)

    def _pick_accent(self):
        c=QColorDialog.getColor(QColor(self._theme.accent), self, "Pick Accent")
        if c.isValid():
            self._theme.accent=c.name()
            # auto hover lighter
            self._theme.accent_hover=c.lighter(115).name()
            self.accent_preview.setStyleSheet(f"background:{self._theme.accent}; border-radius:6px; border:1px solid #222a3a;")
            self._emit_theme()

    def _pick_grad(self, which):
        cur= self._theme.gradient_from if which=="from" else self._theme.gradient_to
        c=QColorDialog.getColor(QColor(cur), self, "Pick Gradient "+which)
        if c.isValid():
            if which=="from": self._theme.gradient_from=c.name()
            else: self._theme.gradient_to=c.name()
            self._emit_theme()

    def _on_gradient_toggle(self, v):
        self._theme.use_gradient=v; self._emit_theme()
    def _on_anim_toggle(self, v):
        self._theme.animations=v; self._emit_theme()
    def _reset_theme(self):
        from launcher.theme import DEFAULT_THEME
        self._theme=Theme.from_dict(DEFAULT_THEME)
        self.gradient_check.setChecked(self._theme.use_gradient)
        self.anim_check.setChecked(self._theme.animations)
        self.accent_preview.setStyleSheet(f"background:{self._theme.accent}; border-radius:6px; border:1px solid #222a3a;")
        self._emit_theme()

    def _update_gradient_preview(self):
        try:
            if self._theme.use_gradient:
                self.gradient_preview.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {self._theme.gradient_from}, stop:1 {self._theme.gradient_to}); border-radius:8px; border:1px solid {self._theme.border};")
            else:
                self.gradient_preview.setStyleSheet(f"background: {self._theme.bg_primary}; border-radius:8px; border:1px solid {self._theme.border};")
            self.gradient_preview.setVisible(True)
        except: pass

    def _emit_theme(self):
        save_theme(self._theme)
        self._update_gradient_preview()
        self.theme_changed.emit(self._theme)

    def _refresh_java(self):
        self.java_combo.clear(); self.java_info.setText("Detecting Java..."); self.refresh_java_btn.setEnabled(False)
        from PySide6.QtCore import QThread, Signal
        class Worker(QThread):
            done=Signal(list)
            def run(self):
                from launcher.java_detector import discover_java_installations
                try: installs=discover_java_installations(use_cache=False)
                except: installs=[]
                self.done.emit(installs)
        self._java_thread=Worker(self)
        def on_done(installs):
            self.java_combo.clear()
            for inst in installs:
                self.java_combo.addItem(f"Java {inst.major or '?'} ({inst.version_string or 'unknown'}) — {inst.path}", inst.path)
            self.java_info.setText(f"Found {len(installs)} Java installation(s)" if installs else "No Java detected")
            self.refresh_java_btn.setEnabled(True); self._java_thread=None
        self._java_thread.done.connect(on_done); self._java_thread.start()

    def set_values(self, settings: dict):
        jp=settings.get("java_path","")
        idx=self.java_combo.findData(jp)
        if idx>=0: self.java_combo.setCurrentIndex(idx)
        else: self.java_combo.setEditText(jp)
        self.game_dir_edit.setText(settings.get("game_directory",""))
        self.ram_spin.setValue(int(settings.get("ram_gb",2)))
        self.custom_args_edit.setText(settings.get("custom_jvm_args",""))
        # theme already loaded

    def _browse_java(self):
        fp,_=QFileDialog.getOpenFileName(self,"Select Java Executable","","Executable (*.exe);;All Files (*)")
        if fp: self.java_combo.setEditText(fp)
    def _browse_game_dir(self):
        d=QFileDialog.getExistingDirectory(self,"Select Game Directory")
        if d: self.game_dir_edit.setText(d)
    def _show_about(self):
        dlg=AboutDialog(self)
        dlg.exec()
    def _save_clicked(self):
        jp=self.java_combo.currentData() or self.java_combo.currentText().strip()
        settings={"java_path": jp, "game_directory": self.game_dir_edit.text().strip(), "ram_gb": self.ram_spin.value(), "custom_jvm_args": self.custom_args_edit.text().strip()}
        self.save_clicked.emit(settings)

# MainWindow with background gradient and animated stack
class MainWindow(QMainWindow):
    def __init__(self, core: LauncherCore):
        super().__init__()
        self.core=core
        self.setWindowTitle("KLauncher")
        self.resize(1180, 720)
        self.setStyleSheet(get_theme().qss())
        _enable_black_titlebar(self)
        self.progress_dialogs: Dict[str, ProgressDialog]={}
        central=QWidget(); self.setCentralWidget(central)
        # app bg
        self.bg=QFrame(central); self.bg.setObjectName("appBg")
        outer=QVBoxLayout(central); outer.setContentsMargins(0,0,0,0)
        outer.addWidget(self.bg)
        lay=QHBoxLayout(self.bg); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
        self.sidebar=Sidebar(); lay.addWidget(self.sidebar)
        # animated stack container
        self.stack=QStackedWidget(); lay.addWidget(self.stack)
        self.play_page=PlayPage(); self.versions_page=VersionsPage(); self.profiles_page=ProfilesPage(); self.settings_page=SettingsPage()
        self.stack.addWidget(self.play_page); self.stack.addWidget(self.versions_page); self.stack.addWidget(self.profiles_page); self.stack.addWidget(self.settings_page)
        # tray - when Minecraft runs, hide to tray
        self.tray = QSystemTrayIcon(self)
        tray_icon = get_icon("Klauncher_logo")
        if tray_icon.isNull():
            tray_icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray.setIcon(tray_icon)
        self.tray.setToolTip("KLauncher - Minecraft running")
        tray_menu = QMenu()
        act_show = tray_menu.addAction("Show KLauncher")
        act_show.triggered.connect(self._tray_show)
        act_quit = tray_menu.addAction("Quit")
        act_quit.triggered.connect(QApplication.quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        # signals
        self.sidebar.nav_clicked.connect(self._on_nav_clicked)
        self.play_page.play_clicked.connect(self._on_play_clicked)
        self.play_page.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.play_page.change_version.connect(lambda: self._on_nav_clicked("Versions"))
        self.play_page.change_profile.connect(lambda: self._on_nav_clicked("Profiles"))
        self.versions_page.add_clicked.connect(self._on_add_version_clicked)
        self.versions_page.version_selected.connect(self._on_version_selected)
        self.versions_page.version_context_requested.connect(self._on_version_context)
        self.profiles_page.profile_created.connect(self._on_profile_created)
        self.profiles_page.profile_deleted.connect(self._on_profile_deleted)
        self.profiles_page.profile_selected.connect(self._on_profile_selected)
        self.profiles_page.microsoft_login_requested.connect(self._on_microsoft_login)
        self.profiles_page.microsoft_logout_requested.connect(self._on_microsoft_logout)
        self.profiles_page.microsoft_selected.connect(self._on_profile_selected)
        self.settings_page.save_clicked.connect(self._on_settings_saved)
        self.settings_page.reset_clicked.connect(self._on_reset_klauncher_data)
        self.settings_page.theme_changed.connect(self._on_theme_changed)
        self.core.profiles_updated.connect(self._update_profiles_ui)
        if hasattr(self.core, 'microsoft_accounts_changed'):
            self.core.microsoft_accounts_changed.connect(self._update_profiles_ui)
            self.core.microsoft_login_succeeded.connect(self._on_microsoft_success)
            self.core.microsoft_login_failed.connect(self._on_microsoft_failed)
            self.core.microsoft_code_ready.connect(self._on_microsoft_code)
        self.core.versions_updated.connect(self._on_remote_versions_updated)
        self.core.installed_versions_changed.connect(self._update_installed_versions_ui)
        self.core.version_error.connect(self._on_version_error)
        self.core.version_loading_changed.connect(self._on_version_loading_changed)
        self.core.install_started.connect(self._on_install_started)
        self.core.install_progress.connect(self._on_install_progress)
        self.core.install_log.connect(self._on_install_log)
        self.core.install_error.connect(self._on_install_error)
        self.core.install_finished.connect(self._on_install_finished)
        self.core.log_message.connect(self._on_log_message)
        self.core.launch_failed.connect(self._on_launch_failed)
        self.core.launch_cancelled.connect(self._on_launch_cancelled)
        self.core.process_started.connect(self._on_process_started)
        self.core.process_finished.connect(self._on_process_finished)
        self.core.java_detected.connect(self._on_java_detected)
        self._update_profiles_ui()
        self._update_installed_versions_ui(self.core.get_installed_versions())
        self._load_settings_to_ui()
        self._update_selected_info()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, lambda: self.core.fetch_versions())
        self._pending_add_dialog=False
        self._ms_dialog = None
        self.sidebar.set_active("Play")
        self._current_idx=0
    def showEvent(self, e):
        super().showEvent(e)
        _enable_black_titlebar(self)
    def _on_theme_changed(self, theme):
        from launcher.assets import clear_tinted_cache
        clear_tinted_cache()
        self.setStyleSheet(theme.qss())
        try:
            self.sidebar.refresh_icons()
            self.play_page.play_button.setIcon(icon_for_nav("play", self))
            self.play_page.change_profile_btn.setIcon(icon_for_nav("profiles", self))
            self.play_page.change_version_btn.setIcon(icon_for_nav("versions", self))
            # recreate cards to pick up new tinted icons
            self.versions_page._apply_filters()
        except:
            pass
    def _on_nav_clicked(self, name: str):
        idx={"Play":0,"Versions":1,"Profiles":2,"Settings":3}[name]
        if idx==self._current_idx:
            return
        # Clear any lingering opacity effects that could hide pages (regression from fade_in)
        for i in range(self.stack.count()):
            w=self.stack.widget(i)
            try:
                if w.graphicsEffect():
                    w.setGraphicsEffect(None)
                # also clear stored anim
                if hasattr(w, "_fade_anim"):
                    try: w._fade_anim.stop()
                    except: pass
                    delattr(w, "_fade_anim")
            except:
                pass
        self.stack.setCurrentIndex(idx)
        self._current_idx=idx
        self.sidebar.set_active(name)
        # subtle non-blocking highlight, no opacity fade on stacked pages to avoid invisible regression
        if get_theme().animations:
            # light pulse on new page's first card for polish without hiding
            try:
                w=self.stack.widget(idx)
                w.setStyleSheet(w.styleSheet())
            except:
                pass
    def _on_play_clicked(self):
        pid=self.core.config.get("selected_profile")
        vid=self.core.config.get("selected_version")
        vs=self.core.config.get("selected_version_source","klauncher")
        if not pid:
            QMessageBox.warning(self,"No Profile","Please select a profile first."); return
        if not vid:
            QMessageBox.warning(self,"No Version","Please select an installed version first."); return
        self.play_page.set_launching(True)
        self.play_page.set_status(f"Preparing {vid}...")
        self.core.launch_minecraft(pid, vid, vs)
    def _on_add_version_clicked(self):
        self._show_add_version_dialog()
    def _on_remote_versions_updated(self, versions: list):
        if self._pending_add_dialog:
            self._pending_add_dialog=False
            self._show_add_version_dialog()
    def _show_add_version_dialog(self, versions: list | None = None):
        dialog=AddVersionDialog(self)
        if dialog.exec()==QDialog.Accepted:
            sel=dialog.get_selection()
            loader=sel["loader"]; mc_ver=sel["minecraft_version"]; loader_ver=sel["loader_version"]
            if loader=="vanilla":
                vid=mc_ver
                if any(v["id"]==vid for v in self.core.get_installed_versions()):
                    QMessageBox.information(self,"Already Installed", f"Version {vid} is already installed."); return
                self.core.install_version(vid); self.play_page.set_status(f"Starting installation of {vid}…")
            elif loader=="fabric":
                self.core.version_manager.install_loader("fabric", mc_ver, loader_ver); self.play_page.set_status(f"Installing Fabric {loader_ver} for {mc_ver}…")
            elif loader=="quilt":
                self.core.version_manager.install_loader("quilt", mc_ver, loader_ver); self.play_page.set_status(f"Installing Quilt {loader_ver} for {mc_ver}…")
            elif loader=="forge":
                QMessageBox.information(self,"Forge","Forge auto-install not yet supported. Download Forge installer manually and place version under .minecraft/versions.")
            elif loader=="optifine":
                QMessageBox.information(self,"OptiFine","OptiFine must be installed via official installer. Run OptiFine installer to add version to libraries.")
            elif loader=="custom":
                QMessageBox.information(self,"Custom","Place custom version JSON+JAR under versions/<id>/ and refresh.")
            else:
                vid=mc_ver; self.core.install_version(vid); self.play_page.set_status(f"Starting installation of {vid}…")
    def _on_version_selected(self, version_id: str, source: str):
        self.core.config.set("selected_version", version_id)
        self.core.config.set("selected_version_source", source)
        self._update_selected_info()
        # subtle pulse on play page
        if get_theme().animations:
            try: self.play_page.version_card.setGraphicsEffect(None)
            except: pass
            eff=QGraphicsOpacityEffect(self.play_page.version_card)
            eff.setOpacity(1)
            self.play_page.version_card.setGraphicsEffect(eff)
            anim=QPropertyAnimation(eff, b"opacity", self.play_page.version_card)
            anim.setDuration(180); anim.setStartValue(0.3); anim.setEndValue(1)
            self.play_page.version_card._pulse_anim = anim
            def _clear():
                try: self.play_page.version_card.setGraphicsEffect(None)
                except: pass
                try: delattr(self.play_page.version_card, "_pulse_anim")
                except: pass
            anim.finished.connect(_clear)
            anim.start()
    def _on_version_context(self, version_info: dict, global_pos):
        vid=version_info.get("id",""); source=version_info.get("source","klauncher"); j=version_info.get("json",{})
        caps=self.core.version_manager.get_capabilities(version_info)
        game_dir=self.core.version_manager.get_game_dir_for_version(version_info, self.core.config.get("game_directory"))
        menu=QMenu(self)
        act_launch=menu.addAction(self.style().standardIcon(QStyle.SP_MediaPlay), "Launch")
        act_launch.triggered.connect(lambda: (self.core.config.set("selected_version", vid), self.core.config.set("selected_version_source", source), self._update_selected_info(), self._on_play_clicked()))
        menu.addSeparator()
        act_open=menu.addAction(get_icon("folder_icon"), "Open Folder")
        act_open.triggered.connect(lambda: self._open_folder(game_dir))
        if caps.get("mods"):
            a=menu.addAction(get_icon("folder_icon"), "Open Mods Folder")
            a.triggered.connect(lambda: self._open_folder(game_dir / "mods"))
        a=menu.addAction(get_icon("folder_icon"), "Open Worlds Folder")
        a.triggered.connect(lambda: self._open_folder(game_dir / "saves"))
        if caps.get("config"):
            a=menu.addAction(get_icon("folder_icon"), "Open Config Folder")
            a.triggered.connect(lambda: self._open_folder(game_dir / "config"))
        menu.addSeparator()
        act_info=menu.addAction(self.style().standardIcon(QStyle.SP_FileDialogInfoView), "Version Info")
        act_info.triggered.connect(lambda: self._show_version_info(version_info))
        act_repair=menu.addAction(self.style().standardIcon(QStyle.SP_BrowserReload), "Repair")
        act_repair.setEnabled(True); act_repair.triggered.connect(lambda: self._repair_version(version_info))
        act_delete=menu.addAction(self.style().standardIcon(QStyle.SP_TrashIcon), "Delete")
        act_delete.triggered.connect(lambda: self._delete_version(version_info))
        menu.exec(global_pos)
    def _open_folder(self, path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Cannot open {path}: {e}")
    def _show_version_info(self, version_info: dict):
        j=version_info.get("json",{}); vid=version_info.get("id",""); source=version_info.get("source",""); vpath=version_info.get("path","")
        from launcher.targets.registry import detect_target
        from launcher.version_metadata import recommended_java_major
        try:
            t=detect_target(vid, j); info=t.describe(vid, j); loader=f"{info.display_name} ({info.loader_version})" if info.loader_version else info.display_name
        except: loader="Unknown"
        java_req=recommended_java_major(j); mc_ver=j.get("inheritsFrom") or j.get("jar") or j.get("id") or vid
        details=f"ID: {vid}\nSource: {source}\nPath: {vpath}\nMinecraft: {mc_ver}\nLoader: {loader}\nJava Required: {java_req or 'unknown'}\nType: {j.get('type','unknown')}\nMain Class: {j.get('mainClass','')}"
        QMessageBox.information(self, "Version Info", details)
    def _delete_version(self, version_info: dict):
        vid=version_info.get("id",""); source=version_info.get("source","")
        reply=QMessageBox.question(self, "Delete Version", f"Delete version '{vid}'?\nThis will remove only this version's folder and is not reversible.\nIt will NOT delete your entire .minecraft folder.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply!=QMessageBox.Yes: return
        ok=self.core.version_manager.delete_version(vid, source)
        if ok:
            if self.core.config.get("selected_version")==vid: self.core.config.set("selected_version", None)
            self._update_selected_info()
        else: QMessageBox.warning(self, "Delete Failed", f"Could not delete {vid}.")
    def _repair_version(self, version_info: dict):
        vid=version_info.get("id",""); source=version_info.get("source","")
        if not self.core.version_manager.repair_version(vid, source):
            QMessageBox.information(self, "Repair", "Repair not available for this version. Re-install manually if needed."); return
        self.play_page.set_status(f"Repairing {vid}...")
    def _on_profile_created(self, username: str):
        p=self.core.create_profile(username)
        if p: self.core.config.set("selected_profile", p.uuid); self.profiles_page._selected_uuid=p.uuid; self._update_selected_info()
    def _on_profile_deleted(self, uuid: str):
        self.core.delete_profile(uuid)
        if self.core.config.get("selected_profile")==uuid: self.core.config.set("selected_profile", None)
        self._update_selected_info()
    def _on_profile_selected(self, uuid: str):
        self.core.config.set("selected_profile", uuid); self.profiles_page._selected_uuid=uuid; self._update_selected_info()
    def _on_settings_saved(self, settings: dict):
        jp=settings.get("java_path","")
        if jp and not Path(jp).exists(): QMessageBox.warning(self,"Invalid Java Path","The specified Java executable does not exist."); return
        gd=settings.get("game_directory","")
        if gd:
            try: Path(gd).mkdir(parents=True, exist_ok=True)
            except Exception as e: QMessageBox.warning(self,"Invalid Game Directory", f"Cannot create game directory: {str(e)}"); return
        self.core.save_settings(settings); QMessageBox.information(self,"Settings Saved","Settings saved successfully."); self._load_settings_to_ui(); self._update_selected_info()
    def _on_reset_klauncher_data(self):
        c=QMessageBox.question(self,"Reset KLauncher data","This deletes only KLauncher's own AppData (config, cache, generated files).\n\nYour .minecraft folder, worlds, resource packs, mods, and Minecraft libraries will not be touched.\n\nContinue?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if c!=QMessageBox.Yes: return
        if self.core.reset_klauncher_data():
            QMessageBox.information(self,"Reset complete","KLauncher data was reset."); self._update_profiles_ui(); self._load_settings_to_ui(); self._update_selected_info()
        else: QMessageBox.warning(self,"Reset failed","Could not reset KLauncher data. See the Play log.")
    def _update_profiles_ui(self):
        profiles=self.core.list_profiles(); self.profiles_page.set_profiles(profiles)
        # Microsoft accounts (isolated, never overwrites offline)
        try:
            if hasattr(self.core, 'list_microsoft_accounts'):
                ms = self.core.list_microsoft_accounts()
                self.profiles_page.set_microsoft_accounts(ms)
        except:
            pass
        self._update_selected_info()
    def _update_installed_versions_ui(self, versions: List[dict]):
        self.versions_page.set_versions(versions); self._update_selected_info()
    def _on_version_error(self, msg: str): self.play_page.set_status(f"Version error: {msg}"); QMessageBox.warning(self,"Version Error",msg)
    def _on_version_loading_changed(self, loading: bool): self.versions_page.set_loading(loading)
    def _on_install_started(self, vid: str):
        if vid not in self.progress_dialogs: self.progress_dialogs[vid]=ProgressDialog(vid,self)
        self.progress_dialogs[vid].show(); self.progress_dialogs[vid].set_status("Initializing…")
    def _on_install_progress(self, vid: str, prog: int):
        if vid in self.progress_dialogs: self.progress_dialogs[vid].update_progress(prog)
    def _on_install_log(self, vid: str, msg: str):
        if vid in self.progress_dialogs: self.progress_dialogs[vid].append_log(msg)
    def _on_install_error(self, vid: str, err: str):
        if vid in self.progress_dialogs: self.progress_dialogs[vid].set_error(err)
        self.play_page.set_status(f"Installation error for {vid}: {err}"); QMessageBox.critical(self,"Installation Error", f"Failed to install {vid}:\n{err}")
    def _on_install_finished(self, vid: str):
        if vid in self.progress_dialogs: self.progress_dialogs[vid].set_finished()
        self.play_page.set_status(f"Version {vid} installed successfully."); self.play_page.set_progress(100); self.core.scan_installed_versions()
    def _on_log_message(self, msg: str): self.play_page.append_log(msg)
    def _on_launch_failed(self, msg: str): self.play_page.set_launching(False); QMessageBox.critical(self,"Cannot launch Minecraft", msg)
    def _on_launch_cancelled(self): self.play_page.set_launching(False); self.play_page.set_status("Launch cancelled")
    def _on_process_started(self):
        self.play_page.set_launching(True); self.play_page.cancel_button.setText("Stop Minecraft"); self.play_page.set_status("Minecraft running...")
        # go to tray
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
            self.tray.showMessage("KLauncher", "Minecraft is running — KLauncher minimized to tray", QSystemTrayIcon.Information, 2500)
            QTimer.singleShot(400, self.hide)
    def _on_process_finished(self, code: int):
        self.play_page.set_launching(False); self.play_page.set_status(f"Minecraft exited ({code})")
        # return from tray
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.show(); self.showNormal(); self.raise_(); self.activateWindow()
            self.tray.hide()
    def _tray_show(self):
        self.show(); self.showNormal(); self.raise_(); self.activateWindow()
        self.tray.hide()
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._tray_show()
    def _on_java_detected(self, path: str, ver: str): self._update_selected_info()
    def _on_cancel_clicked(self): self.core.cancel_launch()
    def _on_microsoft_login(self):
        self.profiles_page.ms_login_btn.setEnabled(False)
        self.profiles_page.ms_status.setText("Starting Microsoft authentication...")
        try:
            self.core.start_microsoft_login()
        except Exception as e:
            QMessageBox.warning(self, "Microsoft Login", f"Failed to start login: {e}")
            self.profiles_page.ms_login_btn.setEnabled(True)

    def _on_microsoft_logout(self, uuid: str):
        self.core.logout_microsoft(uuid)
        self._update_profiles_ui()

    def _on_microsoft_code(self, code: str, uri: str, expires: int):
        # Show device code dialog (official Microsoft page, never asks for password in launcher)
        if self._ms_dialog and self._ms_dialog.isVisible():
            try:
                self._ms_dialog.close()
            except:
                pass
        dlg = MicrosoftDeviceDialog(code, uri, expires, self)
        self._ms_dialog = dlg
        dlg.rejected.connect(lambda: self.core.cancel_microsoft_login())
        dlg.show()

    def _on_microsoft_success(self, acc):
        try:
            if self._ms_dialog:
                self._ms_dialog.accept()
                self._ms_dialog = None
        except:
            pass
        self.profiles_page.ms_login_btn.setEnabled(True)
        QMessageBox.information(self, "Microsoft Login", f"Signed in as {acc.username}\nMicrosoft account verified and Minecraft profile loaded.")
        self._update_profiles_ui()
        # Auto-select the new Microsoft account
        try:
            self.core.config.set("selected_profile", acc.uuid)
            self.profiles_page._selected_uuid = acc.uuid
            self._update_selected_info()
        except:
            pass

    def _on_microsoft_failed(self, msg: str):
        try:
            if self._ms_dialog:
                self._ms_dialog.reject()
                self._ms_dialog = None
        except:
            pass
        self.profiles_page.ms_login_btn.setEnabled(True)
        # Do NOT fallback to offline automatically
        if "Minecraft account required" in msg or "does not own" in msg:
            QMessageBox.warning(self, "Minecraft account required", msg)
        else:
            QMessageBox.warning(self, "Microsoft Login Failed", msg)
        self.profiles_page.ms_status.setText(f"Failed: {msg}")

    def _load_settings_to_ui(self):
        settings={"java_path": self.core.config.get("java_path",""), "game_directory": self.core.config.get("game_directory", str(Path.home()/ "minecraft")), "ram_gb": self.core.config.get("ram_gb",2), "custom_jvm_args": self.core.config.get("custom_jvm_args","")}
        self.settings_page.set_values(settings)
    def _update_selected_info(self):
        pu=self.core.config.get("selected_profile"); profile=self.core.get_profile(pu) if pu else None
        is_ms = self.core.is_microsoft_account(pu) if pu and hasattr(self.core, 'is_microsoft_account') else False
        if profile:
            # Show Microsoft vs Offline distinction
            if is_ms:
                self.sidebar.profile_chip.setText(f"Microsoft: {profile.username}")
                self.play_page.set_profile(profile.username, profile.uuid)
                # Update preview to show Microsoft label
                try:
                    self.profiles_page.preview_offline.setText("Microsoft Account")
                except:
                    pass
            else:
                self.sidebar.profile_chip.setText(f"Profile: {profile.username}"); self.play_page.set_profile(profile.username, profile.uuid)
                try:
                    self.profiles_page.preview_offline.setText("Offline profile • skin visual only")
                except:
                    pass
            self.profiles_page._selected_uuid=profile.uuid; 
            # Also keep microsoft selection in sync
            try:
                self.profiles_page._ms_selected = pu if is_ms else None
                self.profiles_page.set_microsoft_accounts(self.core.list_microsoft_accounts() if hasattr(self.core, 'list_microsoft_accounts') else [])
            except:
                pass
            self.profiles_page._update_preview()
        else:
            self.sidebar.profile_chip.setText("Profile: None"); self.play_page.set_profile("None")
            try:
                self.profiles_page.preview_offline.setText("Offline profile • skin visual only")
            except:
                pass
        vid=self.core.config.get("selected_version"); vs=self.core.config.get("selected_version_source","klauncher"); kind="vanilla"
        if vid:
            low=vid.lower()
            if "optifine" in low: kind="optifine"
            elif "fabric" in low: kind="fabric"
            elif "quilt" in low: kind="quilt"
            elif "forge" in low: kind="forge"
            disp=f"{vid}"; self.sidebar.version_chip.setText(f"Version: {disp}"); self.play_page.set_version(disp, kind)
        else:
            self.sidebar.version_chip.setText("Version: None"); self.play_page.set_version("None")
        jp=self.core.config.get("java_path") or self.core.detected_java_path or "Not found"
        from launcher.java_detector import get_java_version
        ver=get_java_version(jp) if jp and Path(jp).exists() else None
        if ver: self.play_page.set_java_status(f"Java: {ver} — {Path(jp).name}")
        else: self.play_page.set_java_status(f"Java: {jp}")

