from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QMenu, QListView
from launcher.instances.instance import Instance
from launcher.assets import icon_for_loader, get_icon
from launcher.icons import get_action_icon

class InstanceView(QListWidget):
    instance_selected = Signal(object)
    instance_launch_requested = Signal(object)
    instance_context = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setSpacing(12)
        self.setIconSize(QSize(64,64))
        self.setWordWrap(True)
        self.setWrapping(True)
        self.setUniformItemSizes(False)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.itemClicked.connect(self._on_click)
        self.itemDoubleClicked.connect(self._on_double)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)

    def set_instances(self, instances):
        self.clear()
        def _disp(vid):
            try:
                from launcher.version_metadata import _parse_minecraft_version
                p=_parse_minecraft_version(vid)
                if p:
                    mc=f"{p[0]}.{p[1]}" + (f".{p[2]}" if p[2] else "")
                    low=vid.lower()
                    if "fabric" in low: return f"Fabric {mc}"
                    if "quilt" in low: return f"Quilt {mc}"
                    if "forge" in low: return f"Forge {mc}"
                    if "optifine" in low: return f"OptiFine {mc}"
                    return mc
            except: pass
            return vid
        for inst in instances:
            item = QListWidgetItem()
            disp=_disp(inst.version_id)
            item.setText(inst.name + f"\n{disp}")
            item.setData(Qt.UserRole, inst)
            # modpack custom icon
            ic=None
            try:
                if inst.icon and Path(inst.icon).exists():
                    ic=QIcon(str(inst.icon))
            except: pass
            if not ic or ic.isNull():
                loader = inst.loader or "vanilla"
                ic = icon_for_loader(loader)
                if ic.isNull():
                    ic = get_action_icon("instances", self)
            item.setIcon(ic)
            item.setSizeHint(QSize(120,110))
            item.setTextAlignment(Qt.AlignHCenter)
            self.addItem(item)
        # drag-drop mod onto tile support
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)
    def dropEvent(self, e):
        # handled by parent main window via position mapping
        super().dropEvent(e)

    def set_grid_mode(self, grid: bool):
        self.setViewMode(QListView.IconMode if grid else QListView.ListMode)
        self.setIconSize(QSize(64,64) if grid else QSize(32,32))

    def _on_click(self, item):
        inst = item.data(Qt.UserRole)
        if inst:
            self.instance_selected.emit(inst)

    def _on_double(self, item):
        inst = item.data(Qt.UserRole)
        if inst:
            self.instance_launch_requested.emit(inst)

    def _on_context(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        inst = item.data(Qt.UserRole)
        self.instance_context.emit(inst, self.mapToGlobal(pos))
