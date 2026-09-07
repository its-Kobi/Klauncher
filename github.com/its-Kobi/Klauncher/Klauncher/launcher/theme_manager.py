from __future__ import annotations
import json
from pathlib import Path
from launcher.theme import Theme, get_theme, save_theme
from launcher import paths

def list_themes():
    result=[]
    # builtin themes folder
    theme_dir = paths.get_base_dir() / "themes"
    if theme_dir.exists():
        for p in theme_dir.glob("*.json"):
            try:
                data=json.loads(p.read_text(encoding="utf-8"))
                result.append((p.stem, data.get("name", p.stem), p))
            except: continue
    # user themes
    user_dir = paths.get_data_dir() / "themes"
    if user_dir.exists():
        for p in user_dir.glob("*.json"):
            try:
                data=json.loads(p.read_text(encoding="utf-8"))
                result.append((p.stem, data.get("name", p.stem), p))
            except: continue
    return result

def load_theme_file(path: Path) -> Theme:
    data=json.loads(path.read_text(encoding="utf-8"))
    return Theme.from_dict(data)

def apply_theme_file(path: Path):
    t=load_theme_file(path)
    save_theme(t)
    return t

def save_custom_theme(name: str, theme: Theme):
    dest = paths.get_data_dir() / "themes" / f"{name}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    d=theme.to_dict()
    d["name"]=name
    dest.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return dest
