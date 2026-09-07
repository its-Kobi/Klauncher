from __future__ import annotations
import json, shutil
from pathlib import Path
from typing import List, Optional, Dict
from PySide6.QtCore import QObject, Signal
from launcher.instances.instance import Instance
from launcher import paths

class InstanceManager(QObject):
    instances_changed = Signal(list)
    instance_added = Signal(object)
    instance_removed = Signal(str)

    def __init__(self):
        super().__init__()
        self._instances: List[Instance] = []
        self.root = paths.get_data_dir() / "instances"
        self.root.mkdir(parents=True, exist_ok=True)
        self.load_all()

    def load_all(self):
        self._instances.clear()
        for child in self.root.iterdir():
            if child.is_dir() and (child / "instance.json").exists():
                try:
                    data = json.loads((child / "instance.json").read_text(encoding="utf-8"))
                    inst = Instance.from_dict(data, child)
                    self._instances.append(inst)
                except:
                    continue
        # also migrate legacy: if no instances but versions exist, create instances from versions
        if not self._instances:
            self._migrate_legacy()
        self.instances_changed.emit(self._instances)

    def _migrate_legacy(self):
        vm_dir = paths.get_data_dir() / "versions"
        if not vm_dir.exists():
            return
        for vdir in vm_dir.iterdir():
            if vdir.is_dir() and (vdir / f"{vdir.name}.json").exists():
                loader = "vanilla"
                low = vdir.name.lower()
                if "fabric" in low: loader="fabric"
                elif "quilt" in low: loader="quilt"
                elif "forge" in low: loader="forge"
                elif "optifine" in low: loader="optifine"
                inst = Instance(name=vdir.name, version_id=vdir.name, loader=loader)
                inst.save()
                self._instances.append(inst)

    def list(self) -> List[Instance]:
        return list(self._instances)

    def groups(self) -> Dict[str, List[Instance]]:
        g={}
        for i in self._instances:
            g.setdefault(i.group or "Ungrouped", []).append(i)
        return g

    def create(self, name: str, version_id: str, loader="vanilla", loader_version=None, icon="vanilla", group="") -> Instance:
        inst = Instance(name, version_id, loader, loader_version, icon, group)
        inst.ensure_dirs()
        inst.save()
        self._instances.append(inst)
        self.instance_added.emit(inst)
        self.instances_changed.emit(self._instances)
        return inst

    def delete(self, inst_id: str) -> bool:
        inst = self.get(inst_id)
        if not inst:
            return False
        try:
            shutil.rmtree(inst.path)
        except:
            pass
        self._instances = [x for x in self._instances if x.id != inst_id]
        self.instance_removed.emit(inst_id)
        self.instances_changed.emit(self._instances)
        return True

    def get(self, inst_id: str) -> Optional[Instance]:
        for i in self._instances:
            if i.id == inst_id:
                return i
        return None

    def copy(self, inst_id: str, new_name: str) -> Optional[Instance]:
        src = self.get(inst_id)
        if not src:
            return None
        n = Instance(new_name, src.version_id, src.loader, src.loader_version, src.icon, src.group)
        n.ensure_dirs()
        # copy minecraft folder
        try:
            if src.game_dir.exists():
                shutil.copytree(src.game_dir, n.game_dir, dirs_exist_ok=True)
        except:
            pass
        n.save()
        self._instances.append(n)
        self.instances_changed.emit(self._instances)
        return n

    def export(self, inst_id: str, dest_zip: Path):
        inst = self.get(inst_id)
        if not inst:
            raise FileNotFoundError(inst_id)
        shutil.make_archive(str(dest_zip.with_suffix("")), 'zip', inst.path)

    def import_zip(self, zip_path: Path, new_name: Optional[str]=None) -> Instance:
        import zipfile, uuid
        tmp = self.root / f"_import_{uuid.uuid4().hex[:6]}"
        tmp.mkdir()
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmp)
        # find instance.json
        inst_json = None
        for p in tmp.rglob("instance.json"):
            inst_json = p
            break
        if inst_json:
            data = json.loads(inst_json.read_text(encoding="utf-8"))
            name = new_name or data.get("name","Imported")
            src_dir = inst_json.parent
        else:
            name = new_name or zip_path.stem
            src_dir = tmp
        inst = Instance(name, "1.20.1", "vanilla")
        if inst.path.exists():
            shutil.rmtree(inst.path)
        shutil.move(str(src_dir), str(inst.path))
        shutil.rmtree(tmp, ignore_errors=True)
        # reload
        if (inst.path / "instance.json").exists():
            data = json.loads((inst.path / "instance.json").read_text(encoding="utf-8"))
            inst = Instance.from_dict(data, inst.path)
        inst.save()
        self._instances.append(inst)
        self.instances_changed.emit(self._instances)
        return inst

    def load_default_minecraft_versions(self) -> int:
        """Scan default .minecraft/versions and create instances for each version not already present"""
        mc_dir = paths.get_minecraft_dir()
        vers_dir = mc_dir / "versions"
        if not vers_dir.exists():
            return 0
        existing_ids = {i.version_id for i in self._instances}
        added = 0
        for vdir in vers_dir.iterdir():
            if not vdir.is_dir():
                continue
            vid = vdir.name
            if vid in existing_ids:
                continue
            if not (vdir / f"{vid}.json").exists():
                continue
            # detect loader cleanly
            low = vid.lower()
            loader = "vanilla"
            if "fabric" in low: loader="fabric"
            elif "quilt" in low: loader="quilt"
            elif "forge" in low: loader="forge"
            elif "optifine" in low: loader="optifine"
            # clean display name: Fabric Loader 1.20.1 etc. handled in UI, keep internal id as vid
            inst = Instance(name=vid, version_id=vid, loader=loader)
            inst.save()
            self._instances.append(inst)
            added += 1
        if added:
            self.instances_changed.emit(self._instances)
        return added
