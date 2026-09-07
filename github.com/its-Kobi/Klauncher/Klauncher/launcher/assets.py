from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import QSize, Qt
try:
    from PySide6.QtSvg import QSvgRenderer
    HAS_SVG = True
except:
    HAS_SVG = False

_cache: Dict[str, QIcon] = {}
_pix_cache: Dict[str, QPixmap] = {}
_tinted_cache: Dict[str, QIcon] = {}

def _asset_root() -> Path:
    # Try Assets (capital) then assets
    base = Path(__file__).resolve().parent.parent
    for name in ["Assets", "assets"]:
        p = base / name
        if p.exists():
            return p
    return base / "Assets"

def icon_path(name: str) -> Optional[Path]:
    root = _asset_root()
    candidates = [
        root / "Icons" / f"{name}.png",
        root / "Icons" / f"{name}.svg",
        root / "icons" / f"{name}.png",
        root / "Icons" / name,
    ]
    for p in candidates:
        if p.is_file():
            return p
    # case-insensitive search
    try:
        for ext in [".png",".svg"]:
            for f in (root / "Icons").glob(f"*{ext}"):
                if f.stem.lower() == name.lower():
                    return f
            for f in (root / "icons").glob(f"*{ext}"):
                if f.stem.lower() == name.lower():
                    return f
    except:
        pass
    return None

def load_icon(name: str, fallback_qstyle=None, widget=None) -> QIcon:
    key = name.lower()
    if key in _cache:
        return _cache[key]
    p = icon_path(name)
    if p and p.exists():
        icon = QIcon(str(p))
        if not icon.isNull():
            _cache[key] = icon
            return icon
    # fallback to QStyle if provided
    if fallback_qstyle is not None and widget is not None:
        try:
            icon = widget.style().standardIcon(fallback_qstyle)
            _cache[key] = icon
            return icon
        except:
            pass
    # last fallback empty
    icon = QIcon()
    _cache[key] = icon
    return icon

def get_icon(name: str) -> QIcon:
    # For UI SVGs, return contrast-aware tinted icon automatically
    if name in TINTED_ICONS:
        p = icon_path(name)
        if p and p.suffix.lower() == ".svg":
            try:
                from launcher.theme import get_theme
                theme = get_theme()
                # folder icons appear on cards/panels (bg_card), nav icons on sidebar
                # use card bg for default contrast (dark -> light)
                color = theme.icon_color(theme.bg_card)
                return _tinted_svg_icon(p, color, QSize(22,22))
            except:
                pass
    return load_icon(name)

# Mapping for sidebar etc - kept for backward compat, new code uses launcher.icons
ICON_MAP = {
    "play": "Play_icon",
    "versions": "folder_icon",
    "profiles": "Profile_icon",
    "settings": "settings_iconc",
    "fabric": "Fabric_icon",
    "forge": "Forge_icon",
    "quilt": "Quilt_icon",
    "vanilla": "vanilla_icon",
    "optifine": "optifine_icon",
    "custom": "CustomClients",
    "folder": "folder_icon",
    "refresh": "folder_icon",
}
# Re-export unified icon map for audit
try:
    from launcher.icons import ICON_ACTIONS as UNIFIED_ICONS
except:
    UNIFIED_ICONS = {}

# UI SVG icons that should be tinted for contrast (not loader PNGs)
# Include logo and custom so it follows theme like other icons
TINTED_ICONS = {"Play_icon", "folder_icon", "Profile_icon", "settings_iconc", "Klauncher_logo", "custom_icon"}

def _tinted_svg_icon(path: Path, color_hex: str, size: QSize = QSize(22,22)) -> QIcon:
    key = f"{path}:{color_hex}:{size.width()}x{size.height()}"
    if key in _tinted_cache:
        return _tinted_cache[key]
    if not HAS_SVG or path.suffix.lower() != ".svg":
        icon = QIcon(str(path))
        _tinted_cache[key] = icon
        return icon
    try:
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            icon = QIcon(str(path))
            _tinted_cache[key] = icon
            return icon
        pix = QPixmap(size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pix.rect(), QColor(color_hex))
        painter.end()
        icon = QIcon(pix)
        _tinted_cache[key] = icon
        return icon
    except:
        icon = QIcon(str(path))
        _tinted_cache[key] = icon
        return icon

def tinted_icon(name: str, color_hex: str, size: QSize = QSize(22,22)) -> QIcon:
    p = icon_path(name)
    if not p:
        return QIcon()
    if p.suffix.lower() == ".svg" and name in TINTED_ICONS:
        return _tinted_svg_icon(p, color_hex, size)
    return QIcon(str(p))

def clear_tinted_cache():
    _tinted_cache.clear()
    _cache.clear()

def icon_for_loader(kind: str) -> QIcon:
    key = kind.lower()
    # loader icons are PNG with own colors - do not tint
    asset_name = ICON_MAP.get(key)
    if not asset_name:
        if key=="vanilla": asset_name="vanilla_icon"
        elif key=="optifine": asset_name="optifine_icon"
        elif key=="custom": asset_name="CustomClients"
        else: asset_name="folder_icon"
    icon = get_icon(asset_name)
    if icon.isNull():
        # fallback chain
        if key=="optifine":
            icon = get_icon("custom_icon")
        elif key=="custom":
            icon = get_icon("custom_icon")
        if icon.isNull():
            icon = get_icon("vanilla_icon")
    return icon

def icon_for_nav(name: str, widget=None, tint_color: str | None = None):
    from PySide6.QtWidgets import QStyle
    map_style = {
        "play": QStyle.SP_MediaPlay,
        "versions": QStyle.SP_DirIcon,
        "profiles": QStyle.SP_FileDialogContentsView,
        "settings": QStyle.SP_FileDialogDetailedView,
        "add": QStyle.SP_FileDialogNewFolder,
        "folder": QStyle.SP_DirOpenIcon,
    }
    asset_map = {
        "play": "Play_icon",
        "versions": "folder_icon",
        "profiles": "Profile_icon",
        "settings": "settings_iconc",
    }
    asset = asset_map.get(name.lower(), name)
    # Determine tint color from theme if not provided
    if tint_color is None:
        try:
            from launcher.theme import get_theme
            theme = get_theme()
            # sidebar icons use sidebar bg for contrast
            bg = theme.bg_secondary if name.lower() in ("play","versions","profiles","settings") else theme.bg_primary
            tint_color = theme.icon_color(bg)
        except:
            tint_color = "#eef2fb"
    p = icon_path(asset)
    if p:
        if p.suffix.lower() == ".svg":
            return _tinted_svg_icon(p, tint_color, QSize(18,18))
        return QIcon(str(p))
    if widget and name.lower() in map_style:
        return widget.style().standardIcon(map_style[name.lower()])
    return get_icon(asset)

def icon_for_button(name: str, size: QSize = QSize(18,18)) -> QIcon:
    try:
        from launcher.theme import get_theme
        theme = get_theme()
        bg = theme.bg_card if name.lower() in ("folder_icon",) else theme.bg_primary
        # buttons on card use card bg
        color = theme.icon_color(bg)
    except:
        color = "#eef2fb"
    p = icon_path(name)
    if p and p.suffix.lower() == ".svg":
        return _tinted_svg_icon(p, color, size)
    if p:
        return QIcon(str(p))
    return QIcon()
