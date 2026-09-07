from __future__ import annotations
import json, time, uuid
from pathlib import Path
from typing import Optional, Dict, Any
from launcher import paths
from launcher.version_metadata import recommended_java_major

class Instance:
    def __init__(self, name: str, version_id: str, loader: str = "vanilla", loader_version: Optional[str]=None, icon: str="vanilla", group: str="", base_path: Optional[Path]=None):
        self.name = name
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip().replace(" ", "_")
        if not safe:
            safe = f"instance-{uuid.uuid4().hex[:6]}"
        self.id = safe
        self.version_id = version_id
        self.loader = loader.lower()
        self.loader_version = loader_version
        self.icon = icon
        self.group = group
        self.created = time.time()
        self.last_played = 0
        self.total_playtime = 0
        self.notes = ""
        self.settings_overrides: Dict[str, Any] = {}
        self._base = base_path or (paths.get_data_dir() / "instances" / self.id)
        self.metadata: Optional[dict] = None

    @property
    def path(self) -> Path:
        return self._base

    @property
    def game_dir(self) -> Path:
        return self.path / "minecraft"

    @property
    def mods_dir(self) -> Path:
        return self.game_dir / "mods"

    def ensure_dirs(self):
        for p in [self.path, self.game_dir, self.mods_dir, self.game_dir/"saves", self.game_dir/"resourcepacks", self.game_dir/"shaderpacks", self.game_dir/"logs"]:
            p.mkdir(parents=True, exist_ok=True)

    def to_dict(self):
        return {
            "name": self.name, "id": self.id, "version_id": self.version_id, "loader": self.loader,
            "loader_version": self.loader_version, "icon": self.icon, "group": self.group,
            "created": self.created, "last_played": self.last_played, "total_playtime": self.total_playtime,
            "notes": self.notes, "settings_overrides": self.settings_overrides
        }

    @classmethod
    def from_dict(cls, d: dict, base: Path):
        inst = cls(d.get("name",""), d.get("version_id",""), d.get("loader","vanilla"), d.get("loader_version"), d.get("icon","vanilla"), d.get("group",""), base)
        inst.id = d.get("id", inst.id)
        inst.created = d.get("created", inst.created)
        inst.last_played = d.get("last_played", 0)
        inst.total_playtime = d.get("total_playtime", 0)
        inst.notes = d.get("notes","")
        inst.settings_overrides = d.get("settings_overrides",{})
        return inst

    def save(self):
        self.ensure_dirs()
        (self.path / "instance.json").write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def load_metadata(self):
        try:
            from launcher.version_metadata import resolve_metadata_chain
            md = resolve_metadata_chain(paths.get_data_dir(), self.version_id, lambda x: None)
            self.metadata = md
            return md
        except:
            return None

    def required_java(self) -> int:
        from launcher.java.matcher import required_java_for_version
        md = self.metadata or self.load_metadata()
        return required_java_for_version(self.version_id, md)

    def effective_setting(self, key: str, global_val):
        return self.settings_overrides.get(key, global_val)
