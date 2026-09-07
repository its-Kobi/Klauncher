from __future__ import annotations
import json, shutil
from pathlib import Path
from typing import List, Dict

class ModInfo:
    def __init__(self, path: Path, name: str, enabled: bool, version: str="", loader: str=""):
        self.path = path
        self.name = name
        self.enabled = enabled
        self.version = version
        self.loader = loader
        self.size = path.stat().st_size if path.exists() else 0

class ModManager:
    def __init__(self, instance):
        self.instance = instance

    def mods_dir(self) -> Path:
        d = self.instance.game_dir / "mods"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_mods(self) -> List[ModInfo]:
        d = self.mods_dir()
        result=[]
        for p in d.iterdir():
            if p.is_file() and p.suffix.lower()==".jar":
                result.append(ModInfo(p, p.stem, True))
            elif p.is_file() and p.suffix.lower()==".disabled":
                result.append(ModInfo(p, p.stem.replace(".jar",""), False))
            elif p.name.endswith(".jar.disabled"):
                result.append(ModInfo(p, p.name.replace(".jar.disabled",""), False))
        # also handle .jar.disabled double suffix
        for p in d.glob("*.jar.disabled"):
            if not any(m.path==p for m in result):
                result.append(ModInfo(p, p.name.replace(".jar.disabled",""), False))
        return result

    def set_enabled(self, mod: ModInfo, enabled: bool):
        if enabled and not mod.enabled:
            new = mod.path.with_suffix("") if mod.path.suffix==".disabled" else mod.path
            # handle .jar.disabled case
            if mod.path.name.endswith(".jar.disabled"):
                new = mod.path.parent / mod.path.name.replace(".jar.disabled", ".jar")
            else:
                new = Path(str(mod.path).replace(".disabled",""))
            mod.path.rename(new)
        elif not enabled and mod.enabled:
            new = mod.path.parent / (mod.path.name + ".disabled")
            mod.path.rename(new)

    def delete(self, mod: ModInfo):
        try:
            mod.path.unlink()
        except:
            pass

    def add_from_path(self, src: Path):
        dest = self.mods_dir() / src.name
        shutil.copy2(src, dest)
        return dest

    def check_compat(self, mod_filename: str, instance) -> tuple[bool, str]:
        # check mc version compat via filename heuristics + modrinth already checked
        # For Fabric, require fabric loader
        if instance.loader in ("fabric","quilt"):
            return True, ""
        if instance.loader in ("forge","vanilla") and "fabric" in mod_filename.lower():
            return False, "This mod appears to be a Fabric mod but instance is not Fabric."
        return True, ""
