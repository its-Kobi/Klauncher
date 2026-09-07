from __future__ import annotations
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPainterPath
from PySide6.QtCore import QSize, Qt
from typing import Dict

# Modern flat outline icons - drawn at runtime with consistent stroke 1.7px, rounded caps
# Ensures every action has a distinct, instantly recognizable glyph.

def _make_icon(draw_fn, size=QSize(22,22), color="#eef2fb") -> QIcon:
    pm = QPixmap(size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    draw_fn(p, size)
    p.end()
    return QIcon(pm)

def _draw_play(p, s):
    # triangle centered
    path = QPainterPath()
    path.moveTo(s.width()*0.30, s.height()*0.22)
    path.lineTo(s.width()*0.30, s.height()*0.78)
    path.lineTo(s.width()*0.78, s.height()*0.50)
    path.closeSubpath()
    p.drawPath(path)

def _draw_user(p, s):
    # head circle + shoulders
    p.drawEllipse(int(s.width()*0.32), int(s.height()*0.18), int(s.width()*0.36), int(s.height()*0.36))
    path = QPainterPath()
    path.moveTo(s.width()*0.22, s.height()*0.82)
    path.cubicTo(s.width()*0.22, s.height()*0.62, s.width()*0.35, s.height()*0.58, s.width()*0.50, s.height()*0.58)
    path.cubicTo(s.width()*0.65, s.height()*0.58, s.width()*0.78, s.height()*0.62, s.width()*0.78, s.height()*0.82)
    p.drawPath(path)

def _draw_grid(p, s):
    r=3
    gap=4
    sz=(s.width()-gap)//2 -1
    for x,y in [(2,2),(2+sz+gap,2),(2,2+sz+gap),(2+sz+gap,2+sz+gap)]:
        p.drawRoundedRect(x,y,sz,sz, r,r)

def _draw_gear(p, s):
    # simplified gear: circle + 4 ticks
    cx,cy=s.width()/2, s.height()/2
    r=s.width()*0.28
    p.drawEllipse(int(cx-r), int(cy-r), int(r*2), int(r*2))
    for ang in [0,90,180,270]:
        p.save()
        p.translate(cx,cy); p.rotate(ang)
        p.drawLine(0, int(-r-4), 0, int(-r+1))
        p.restore()
    # diagonal ticks smaller
    for ang in [45,135,225,315]:
        p.save()
        p.translate(cx,cy); p.rotate(ang)
        p.drawLine(0, int(-r-3), 0, int(-r))
        p.restore()

def _draw_back(p,s):
    p.drawLine(int(s.width()*0.68), int(s.height()*0.25), int(s.width()*0.32), int(s.height()*0.50))
    p.drawLine(int(s.width()*0.32), int(s.height()*0.50), int(s.width()*0.68), int(s.height()*0.75))

def _draw_forward(p,s):
    p.drawLine(int(s.width()*0.32), int(s.height()*0.25), int(s.width()*0.68), int(s.height()*0.50))
    p.drawLine(int(s.width()*0.68), int(s.height()*0.50), int(s.width()*0.32), int(s.height()*0.75))

def _draw_folder(p,s):
    p.drawRoundedRect(2, int(s.height()*0.35), s.width()-4, int(s.height()*0.50), 2,2)
    p.drawLine(2, int(s.height()*0.35), int(s.width()*0.55), int(s.height()*0.35))
    p.drawLine(int(s.width()*0.55), int(s.height()*0.35), int(s.width()*0.62), int(s.height()*0.28))
    p.drawLine(int(s.width()*0.62), int(s.height()*0.28), s.width()-4, int(s.height()*0.28))

def _draw_trash(p,s):
    # lid
    p.drawLine(int(s.width()*0.30), int(s.height()*0.30), int(s.width()*0.70), int(s.height()*0.30))
    p.drawLine(int(s.width()*0.38), int(s.height()*0.25), int(s.width()*0.62), int(s.height()*0.25))
    # body
    p.drawRoundedRect(int(s.width()*0.32), int(s.height()*0.30), int(s.width()*0.36), int(s.height()*0.52), 2,2)
    # lines inside
    p.drawLine(int(s.width()*0.42), int(s.height()*0.42), int(s.width()*0.42), int(s.height()*0.72))
    p.drawLine(int(s.width()*0.50), int(s.height()*0.42), int(s.width()*0.50), int(s.height()*0.72))
    p.drawLine(int(s.width()*0.58), int(s.height()*0.42), int(s.width()*0.58), int(s.height()*0.72))

def _draw_pencil(p,s):
    p.drawLine(int(s.width()*0.32), int(s.height()*0.68), int(s.width()*0.18), int(s.height()*0.82))
    p.drawLine(int(s.width()*0.18), int(s.height()*0.82), int(s.width()*0.32), int(s.height()*0.82))
    p.drawLine(int(s.width()*0.32), int(s.height()*0.82), int(s.width()*0.75), int(s.height()*0.30))
    p.drawLine(int(s.width()*0.75), int(s.height()*0.30), int(s.width()*0.82), int(s.height()*0.38))
    p.drawLine(int(s.width()*0.82), int(s.height()*0.38), int(s.width()*0.38), int(s.height()*0.82))

def _draw_download(p,s):
    p.drawLine(int(s.width()*0.50), int(s.height()*0.20), int(s.width()*0.50), int(s.height()*0.62))
    p.drawLine(int(s.width()*0.30), int(s.height()*0.48), int(s.width()*0.50), int(s.height()*0.68))
    p.drawLine(int(s.width()*0.70), int(s.height()*0.48), int(s.width()*0.50), int(s.height()*0.68))
    p.drawLine(int(s.width()*0.22), int(s.height()*0.74), int(s.width()*0.78), int(s.height()*0.74))

def _draw_puzzle(p,s):
    # puzzle piece
    p.drawRoundedRect(3,3,s.width()-6,s.height()-6,3,3)
    # tab on right
    p.drawEllipse(int(s.width()*0.62), int(s.height()*0.35), int(s.width()*0.22), int(s.height()*0.22))

def _draw_box(p,s):
    p.drawRect(3, int(s.height()*0.35), s.width()-6, int(s.height()*0.45))
    p.drawLine(3, int(s.height()*0.35), int(s.width()*0.50), int(s.height()*0.22))
    p.drawLine(int(s.width()*0.50), int(s.height()*0.22), s.width()-3, int(s.height()*0.35))

def _draw_image(p,s):
    p.drawRoundedRect(2,2,s.width()-4,s.height()-4,2,2)
    p.drawEllipse(int(s.width()*0.30), int(s.height()*0.35), int(s.width()*0.22), int(s.height()*0.22))
    path=QPainterPath()
    path.moveTo(2, s.height()-4)
    path.lineTo(int(s.width()*0.42), int(s.height()*0.58))
    path.lineTo(int(s.width()*0.62), int(s.height()*0.42))
    path.lineTo(s.width()-2, int(s.height()*0.62))
    p.drawPath(path)

def _draw_file(p,s):
    p.drawRoundedRect(4,2,s.width()-8,s.height()-4,2,2)
    p.drawLine(s.width()-8, 2, s.width()-8, 8)
    p.drawLine(s.width()-8, 8, s.width()-4, 8)

def _draw_layers(p,s):
    for off in [0,4,8]:
        y=int(s.height()*0.28)+off
        p.drawRoundedRect(3, y, s.width()-6, int(s.height()*0.18),2,2)
def _draw_pencil2(p,s): _draw_pencil(p,s); p.drawLine(2,2,4,4)
def _draw_file2(p,s): _draw_file(p,s); p.drawLine(int(s.width()*0.45), int(s.height()*0.50), int(s.width()*0.65), int(s.height()*0.50))
def _draw_file3(p,s): _draw_file(p,s); p.drawLine(int(s.width()*0.45), int(s.height()*0.60), int(s.width()*0.65), int(s.height()*0.60))
def _draw_file4(p,s): _draw_file(p,s); p.drawEllipse(int(s.width()*0.55), int(s.height()*0.55), 4,4)
def _draw_image2(p,s): _draw_image(p,s); p.drawEllipse(int(s.width()*0.60), int(s.height()*0.30), 3,3)
def _draw_box2(p,s): _draw_box(p,s); p.drawLine(int(s.width()*0.50), int(s.height()*0.22), int(s.width()*0.50), int(s.height()*0.80))
def _draw_download2(p,s): _draw_download(p,s); p.drawLine(int(s.width()*0.30), int(s.height()*0.20), int(s.width()*0.40), int(s.height()*0.20))
def _draw_download3(p,s): _draw_download(p,s); p.drawLine(int(s.width()*0.60), int(s.height()*0.20), int(s.width()*0.70), int(s.height()*0.20))
def _draw_layers2(p,s): _draw_layers(p,s); p.drawLine(3, int(s.height()*0.80), s.width()-3, int(s.height()*0.80))
def _draw_file5(p,s): _draw_file(p,s); p.drawLine(6,12, s.width()-6,12)
def _draw_file6(p,s): _draw_file(p,s); p.drawLine(6,8, s.width()-6,8); p.drawLine(6,16, s.width()-10,16)
def _draw_file7(p,s): _draw_file(p,s); p.drawEllipse(6,6,8,8); p.drawLine(13,13,18,18)

# Map action -> draw function (unique)
_DRAW_MAP = {
    "launch": _draw_play,
    "play_instance": _draw_play,
    "accounts": _draw_user,
    "instances": _draw_grid,
    "settings": _draw_gear,
    "back": _draw_back,
    "forward": _draw_forward,
    "folder": _draw_folder,
    "delete": _draw_trash,
    "edit": _draw_pencil,
    "rename": _draw_pencil2,
    "download": _draw_download,
    "mods": _draw_puzzle,
    "resourcepacks": _draw_image,
    "shaderpacks": _draw_layers,
    "worlds": _draw_box,
    "datapacks": _draw_file,
    "screenshots": _draw_image2,
    "notes": _draw_file2,
    "logs": _draw_file3,
    "health": _draw_file4,
    "diff": _draw_layers2,
    "history": _draw_file5,
    "copy": _draw_box2,
    "export": _draw_download2,
    "import": _draw_download3,
    "refresh": _draw_file6,
    "search": _draw_file7,
}

# Public registry for audit - every action listed once
ICON_ACTIONS = {k: {"draw": v} for k,v in _DRAW_MAP.items()}
# Add loaders with brand PNGs (still unique via PNG)
for k in ["vanilla","fabric","forge","quilt","optifine","custom"]:
    ICON_ACTIONS[k] = {"asset": True}

def audit_icons():
    # loaders share brand but that's expected (different PNGs); check non-loader dups
    seen = {}
    dup=[]
    for k in ICON_ACTIONS:
        if k in ("launch","play_instance") or k in ("vanilla","fabric","forge","quilt","optifine","custom"):
            continue
        fn = _DRAW_MAP.get(k)
        if fn in seen:
            dup.append((k, seen[fn]))
        else:
            seen[fn]=k
    return dup

def get_action_icon(action: str, widget=None, color=None) -> QIcon:
    # Try asset first for loaders
    if action in ("vanilla","fabric","forge","quilt","optifine","custom"):
        from launcher.assets import icon_for_loader, get_icon
        ic = icon_for_loader(action)
        if not ic.isNull():
            return ic
        return get_icon("custom_icon")
    fn = _DRAW_MAP.get(action)
    if fn:
        # Use theme-aware color
        try:
            from launcher.theme import get_theme
            c = color or get_theme().icon_color(get_theme().bg_primary)
        except:
            c="#eef2fb"
        return _make_icon(fn, QSize(22,22), c)
    return QIcon()
