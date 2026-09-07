from __future__ import annotations
from pathlib import Path
from PySide6.QtGui import QFontDatabase

_loaded=False
# Defaults will be overwritten after actual load; Minecraft.otf registers as "Monocraft"
_title_family="Monocraft"
_body_family="Monocraft"

def load_fonts():
    global _loaded, _title_family, _body_family
    if _loaded:
        return _title_family, _body_family
    try:
        from launcher import paths
        base=paths.get_base_dir()
        # MinecraftTen is often broken (-1), fallback to Monocraft for titles
        p_ten=base / "Assets" / "MinecraftTen-VGORe.ttf"
        p_body=base / "Assets" / "Minecraft.otf"
        # try Ten first
        if p_ten.exists():
            idx=QFontDatabase.addApplicationFont(str(p_ten))
            fams=QFontDatabase.applicationFontFamilies(idx) if idx!=-1 else []
            if fams:
                _title_family=fams[0]
            else:
                # Ten failed (-1) -> use body font for titles too
                _title_family=_body_family
        if p_body.exists():
            idx=QFontDatabase.addApplicationFont(str(p_body))
            fams=QFontDatabase.applicationFontFamilies(idx) if idx!=-1 else []
            if fams:
                _body_family=fams[0]
                # if Ten failed, mirror body to title
                if _title_family=="Monocraft" and _body_family=="Monocraft":
                    pass
                elif "Ten" not in _title_family:
                    # keep body as Monocraft, title also Monocraft if Ten unavailable
                    if _title_family=="Minecraft Ten":
                        _title_family=_body_family
        # final fallback
        if not _title_family:
            _title_family=_body_family
        _loaded=True
    except:
        _loaded=True
    return _title_family, _body_family

def title_family():
    t,_=load_fonts()
    return t

def body_family():
    _,b=load_fonts()
    return b
