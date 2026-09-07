import json, shutil
from pathlib import Path
from typing import List, Optional, Dict

from PySide6.QtCore import QObject, Signal

from launcher import paths
from launcher.downloader import Downloader
from launcher.installer import VersionInstaller, FabricInstaller


class VersionManager(QObject):
    """Fetches remote version manifest and manages installed versions."""

    versions_loaded = Signal(list)               # remote versions
    installed_versions_changed = Signal(list)    # list of dicts (id, type, source, path)
    install_started = Signal(str)
    install_progress = Signal(str, int)
    install_log = Signal(str, str)
    install_error = Signal(str, str)
    install_finished = Signal(str)
    error = Signal(str)
    loading_changed = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.downloader = Downloader(self)
        self.downloader.finished.connect(self._on_manifest_downloaded)
        self.downloader.error.connect(self._on_download_error)
        self.manifest_path = paths.get_data_dir() / "cache" / "version_manifest.json"
        self._versions: List[dict] = []
        self._installers = {}

    def fetch_versions(self, force_refresh: bool = False) -> None:
        if not force_refresh and self.manifest_path.exists():
            try:
                self._load_manifest_from_file()
                return
            except Exception:
                pass
        self.loading_changed.emit(True)
        self.downloader.download(
            "https://launchermeta.mojang.com/mc/game/version_manifest.json",
            self.manifest_path,
            retries=3,
            timeout_ms=15000
        )

    def get_available_versions(self) -> List[dict]:
        return self._versions.copy()

    def get_all_installed_versions(self) -> List[dict]:
        """Return combined list of KLauncher and external versions with metadata."""
        result = []
        klauncher_dir = paths.get_data_dir() / "versions"
        if klauncher_dir.exists():
            for child in klauncher_dir.iterdir():
                if child.is_dir() and (child / f"{child.name}.json").exists():
                    info = self._get_version_info(child, "klauncher")
                    if info:
                        result.append(info)
        mc_dir = paths.get_minecraft_dir()
        external_dir = mc_dir / "versions"
        if external_dir.exists():
            for child in external_dir.iterdir():
                if child.is_dir() and (child / f"{child.name}.json").exists():
                    info = self._get_version_info(child, "external")
                    if info:
                        result.append(info)
        return result

    def _get_version_info(self, dir_path: Path, source: str) -> Optional[dict]:
        version_id = dir_path.name
        json_path = dir_path / f"{version_id}.json"
        if not json_path.exists():
            return None
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        version_type = data.get("type", "unknown")
        if "inheritsFrom" in data:
            base_type = self._get_base_type(dir_path, data["inheritsFrom"])
            if base_type:
                version_type = base_type
        return {
            "id": version_id,
            "type": version_type,
            "source": source,
            "path": str(dir_path),
            "json": data
        }

    def _get_base_type(self, current_dir: Path, base_id: str) -> Optional[str]:
        parent = current_dir.parent
        base_path = parent / base_id
        if base_path.exists():
            json_path = base_path / f"{base_id}.json"
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    return data.get("type")
                except Exception:
                    pass
        return None

    def install_version(self, version_id: str) -> None:
        version_url = None
        for v in self._versions:
            if v["id"] == version_id:
                version_url = v["url"]
                break
        if not version_url:
            self.install_error.emit(version_id, "Version not found in manifest.")
            return
        if version_id in self._installers:
            self.install_log.emit(version_id, "Already installing.")
            return
        installer = VersionInstaller(version_id, version_url)
        installer.progress.connect(lambda prog, vid=version_id: self.install_progress.emit(vid, prog))
        installer.log.connect(lambda msg, vid=version_id: self.install_log.emit(vid, msg))
        installer.error.connect(lambda err, vid=version_id: self.install_error.emit(vid, err))
        installer.finished_install.connect(self._on_install_finished)
        self._installers[version_id] = installer
        installer.start()
        self.install_started.emit(version_id)

    def install_fabric(self, minecraft_version: str, loader_version: str) -> None:
        version_id = f"fabric-loader-{loader_version}-{minecraft_version}"
        if version_id in self._installers:
            self.install_log.emit(version_id, "Already installing.")
            return
        installer = FabricInstaller(minecraft_version, loader_version)
        installer.progress.connect(lambda prog, vid=version_id: self.install_progress.emit(vid, prog))
        installer.log.connect(lambda msg, vid=version_id: self.install_log.emit(vid, msg))
        installer.error.connect(lambda err, vid=version_id: self.install_error.emit(vid, err))
        installer.finished_install.connect(self._on_install_finished)
        self._installers[version_id] = installer
        installer.start()
        self.install_started.emit(version_id)

    def install_quilt(self, minecraft_version: str, loader_version: str) -> None:
        version_id = f"quilt-loader-{loader_version}-{minecraft_version}"
        # Reuse FabricInstaller logic with Quilt meta
        from launcher.installer import QuiltInstaller
        installer = QuiltInstaller(minecraft_version, loader_version)
        installer.progress.connect(lambda prog, vid=version_id: self.install_progress.emit(vid, prog))
        installer.log.connect(lambda msg, vid=version_id: self.install_log.emit(vid, msg))
        installer.error.connect(lambda err, vid=version_id: self.install_error.emit(vid, err))
        installer.finished_install.connect(self._on_install_finished)
        self._installers[version_id] = installer
        installer.start()
        self.install_started.emit(version_id)

    def install_loader(self, loader: str, minecraft_version: str, loader_version: str):
        loader = loader.lower()
        if loader == "fabric":
            self.install_fabric(minecraft_version, loader_version)
        elif loader == "quilt":
            self.install_quilt(minecraft_version, loader_version)
        elif loader == "forge":
            self.install_error.emit(f"forge-{minecraft_version}", "Forge install requires manual installer. Place version in .minecraft/versions.")
        elif loader == "optifine":
            self.install_error.emit(f"optifine-{minecraft_version}", "OptiFine must be installed via official installer.")
        else:
            self.install_version(minecraft_version)

    def get_game_dir_for_version(self, version_info: dict, config_game_dir: Optional[str]=None) -> Path:
        # Use same logic as core.launch_minecraft
        source = version_info.get("source", "klauncher")
        if source == "external":
            return paths.get_minecraft_dir()
        # klauncher
        if config_game_dir:
            return Path(config_game_dir)
        return paths.get_data_dir() / "game"

    def get_capabilities(self, version_info: dict) -> dict:
        from launcher.targets.registry import detect_target
        data = version_info.get("json", {})
        vid = version_info.get("id","")
        try:
            target = detect_target(vid, data)
            return target.capabilities(data)
        except:
            return {"mods": False, "config": False, "worlds": True, "game_dir": True}

    def delete_version(self, version_id: str, source: str) -> bool:
        # Safety checks
        if not version_id or version_id in (".", ".."):
            return False
        if source == "external":
            base = paths.get_minecraft_dir() / "versions" / version_id
            # ensure inside .minecraft/versions
            try:
                if not str(base.resolve()).startswith(str((paths.get_minecraft_dir() / "versions").resolve())):
                    return False
            except:
                return False
        else:
            base = paths.get_data_dir() / "versions" / version_id
            try:
                if not str(base.resolve()).startswith(str((paths.get_data_dir() / "versions").resolve())):
                    return False
            except:
                return False
        if not base.exists():
            return False
        try:
            shutil.rmtree(base)
            self.installed_versions_changed.emit(self.get_all_installed_versions())
            return True
        except Exception as e:
            self.error.emit(str(e))
            return False

    def repair_version(self, version_id: str, source: str) -> bool:
        # Reuse installer: for vanilla, re-download; for fabric/quilt detect and reinstall
        # Disable if unknown
        vid_lower = version_id.lower()
        if "fabric-loader" in vid_lower:
            # parse mc and loader
            # format fabric-loader-<loader>-<mc> -> loader may contain dots/dashes
            # fabric-loader-0.15.0-1.20.1 -> split
            try:
                rest = version_id.replace("fabric-loader-","",1)
                # loader is first part before next dash that precedes mc version starting with digit
                # simpler: split last part is mc
                parts = rest.split("-")
                # mc version is last 2-3 parts? Actually 1.20.1 -> three parts but joined with .
                # rest = "0.15.0-1.20.1" -> we want loader=0.15.0, mc=1.20.1
                # split at first occurrence of digit digit? Easier: find mc start
                # Use known pattern: loader contains no letter number dot dash but mc starts with digit
                # Find index where segment starts with digit and contains dot
                mc_start = None
                for i, p in enumerate(parts):
                    if "." in p and p[0].isdigit():
                        mc_start = i
                        break
                if mc_start is not None:
                    loader_ver = "-".join(parts[:mc_start])
                    mc_ver = "-".join(parts[mc_start:])
                    self.install_fabric(mc_ver, loader_ver)
                    return True
            except:
                pass
            return False
        elif "quilt-loader" in vid_lower:
            return False
        elif vid_lower.startswith("forge") or "forge" in vid_lower:
            return False
        else:
            # vanilla: reinstall
            self.install_version(version_id)
            return True

    def _on_install_finished(self, version_id: str):
        if version_id in self._installers:
            del self._installers[version_id]
        self.installed_versions_changed.emit(self.get_all_installed_versions())
        self.install_finished.emit(version_id)

    def _load_manifest_from_file(self) -> None:
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._process_manifest(data)

    def _on_manifest_downloaded(self, filepath: str) -> None:
        self.loading_changed.emit(False)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._process_manifest(data)
        except Exception as e:
            self.error.emit(f"Failed to parse version manifest: {str(e)}")

    def _on_download_error(self, error_msg: str) -> None:
        self.loading_changed.emit(False)
        self.error.emit(error_msg)

    def _process_manifest(self, data: dict) -> None:
        versions = data.get("versions", [])
        self._versions = [v for v in versions if v.get("type") in ("release", "snapshot")]
        self.versions_loaded.emit(self._versions)
