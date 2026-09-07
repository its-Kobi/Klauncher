import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from launcher import paths


class VersionInstaller(QThread):
    """Background thread to download and install a Minecraft version."""

    progress = Signal(int)          # overall progress 0-100
    log = Signal(str)               # log message
    error = Signal(str)             # error message
    finished_install = Signal(str)  # version id

    def __init__(self, version_id: str, version_url: str, parent=None):
        super().__init__(parent)
        self.version_id = version_id
        self.version_url = version_url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._install()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished_install.emit(self.version_id)

    def _install(self):
        data_dir = paths.get_data_dir()
        versions_dir = data_dir / "versions"
        version_dir = versions_dir / self.version_id
        version_dir.mkdir(parents=True, exist_ok=True)

        self.log.emit(f"Downloading version manifest for {self.version_id}...")
        version_json_path = version_dir / f"{self.version_id}.json"
        self._download_file(self.version_url, version_json_path)
        with open(version_json_path, "r", encoding="utf-8") as f:
            version_data = json.load(f)

        # Download client jar
        client_url = version_data["downloads"]["client"]["url"]
        client_sha1 = version_data["downloads"]["client"].get("sha1")
        jar_path = version_dir / f"{self.version_id}.jar"
        self.log.emit("Downloading client jar...")
        self._download_file(client_url, jar_path, sha1=client_sha1)
        self.progress.emit(20)

        libraries = version_data.get("libraries", [])
        total_libs = len(libraries)
        for i, lib in enumerate(libraries):
            if self._cancelled:
                return

            # ---- CORRECT RULE EVALUATION ----
            # Skip libraries that are disallowed for the current OS.
            if not self._is_library_allowed(lib):
                continue

            self.log.emit(f"Downloading library {i+1}/{total_libs}: {lib['name']}")

            # Download main artifact
            artifact = lib.get("downloads", {}).get("artifact")
            if artifact:
                lib_path = self._get_library_path(lib["name"])
                dest = data_dir / "libraries" / lib_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                self._download_file(artifact["url"], dest, sha1=artifact.get("sha1"))

            # Download and extract natives if present
            if "natives" in lib and "classifiers" in lib.get("downloads", {}):
                os_name = self._get_os_name()
                classifier_key = f"natives-{os_name}"
                classifier = lib["downloads"]["classifiers"].get(classifier_key)
                if classifier:
                    native_dest = version_dir / "natives"
                    native_dest.mkdir(exist_ok=True)
                    native_path = native_dest / f"{lib['name'].split(':')[1]}.jar"
                    self._download_file(classifier["url"], native_path, sha1=classifier.get("sha1"))
                    self._extract_natives(native_path, native_dest)
                    native_path.unlink()   # remove archive after extraction

            lib_progress = 20 + int((i+1) / total_libs * 40)
            self.progress.emit(lib_progress)

        # Asset index and assets
        asset_index_info = version_data.get("assetIndex")
        if asset_index_info:
            self.log.emit("Downloading asset index...")
            asset_index_url = asset_index_info["url"]
            asset_index_path = data_dir / "assets" / "indexes" / f"{self.version_id}.json"
            asset_index_path.parent.mkdir(parents=True, exist_ok=True)
            self._download_file(asset_index_url, asset_index_path)
            with open(asset_index_path, "r", encoding="utf-8") as f:
                asset_index = json.load(f)
            objects = asset_index.get("objects", {})
            total_assets = len(objects)
            self.log.emit(f"Downloading {total_assets} assets...")
            for i, (asset_name, asset_info) in enumerate(objects.items()):
                if self._cancelled:
                    return
                asset_hash = asset_info["hash"]
                asset_url = f"https://resources.download.minecraft.net/{asset_hash[:2]}/{asset_hash}"
                dest = data_dir / "assets" / "objects" / asset_hash[:2] / asset_hash
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    self._download_file(asset_url, dest, sha1=asset_hash)
                asset_progress = 60 + int((i+1) / total_assets * 30)
                self.progress.emit(asset_progress)

        # Mark as installed
        marker = version_dir / ".installed"
        marker.touch()
        self.progress.emit(100)
        self.log.emit("Version installed successfully.")

    def _download_file(self, url: str, dest: Path, sha1: Optional[str] = None):
        if dest.exists() and sha1:
            if self._verify_sha1(dest, sha1):
                return
            else:
                dest.unlink()   # re-download
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "MinecraftLauncher/1.0"})
        with urllib.request.urlopen(req) as response, open(dest, "wb") as out_file:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    percent = int((downloaded / total) * 100)
                    # not used; overall progress is emitted from main loop
        if sha1 and not self._verify_sha1(dest, sha1):
            raise Exception(f"SHA1 mismatch for {dest.name}")

    def _verify_sha1(self, file_path: Path, expected_sha1: str) -> bool:
        sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha1.update(chunk)
        return sha1.hexdigest() == expected_sha1

    def _get_library_path(self, name: str) -> str:
        parts = name.split(":")
        if len(parts) == 3:
            group, artifact, version = parts
            return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.jar"
        else:
            return name.replace(":", "/") + ".jar"

    def _get_os_name(self) -> str:
        import platform
        system = platform.system().lower()
        if system == "windows":
            return "windows"
        elif system == "darwin":
            return "osx"
        else:
            return "linux"

    def _is_library_allowed(self, lib: dict) -> bool:
        """Evaluate library rules correctly according to Mojang's specification."""
        rules = lib.get("rules", [])
        if not rules:
            return True   # no rules -> allowed

        os_name = self._get_os_name()
        # Iterate rules; the last matching rule determines the action.
        # If no rule matches, the library is allowed.
        allowed = True
        for rule in rules:
            action = rule.get("action")
            os_info = rule.get("os", {})
            rule_os = os_info.get("name")
            if not rule_os or rule_os == os_name:
                allowed = (action == "allow")
        return allowed

    def _extract_natives(self, archive_path: Path, dest_dir: Path):
        if archive_path.suffix in (".jar", ".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.namelist():
                    if not member.endswith("/"):
                        zf.extract(member, dest_dir)


class FabricInstaller(QThread):
    progress = Signal(int)
    log = Signal(str)
    error = Signal(str)
    finished_install = Signal(str)

    def __init__(self, minecraft_version: str, loader_version: str, parent=None):
        super().__init__(parent)
        self.minecraft_version = minecraft_version
        self.loader_version = loader_version
        self.version_id = f"fabric-loader-{loader_version}-{minecraft_version}"

    def run(self):
        try:
            self._install()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished_install.emit(self.version_id)

    def _install(self):
        data_dir = paths.get_data_dir()
        # Ensure vanilla base exists (reuse VersionInstaller logic for vanilla)
        self._ensure_vanilla(self.minecraft_version)
        self.progress.emit(30)
        self.log.emit(f"Fetching Fabric profile {self.loader_version} for {self.minecraft_version}...")
        url = f"https://meta.fabricmc.net/v2/versions/loader/{self.minecraft_version}/{self.loader_version}/profile/json"
        req = urllib.request.Request(url, headers={"User-Agent":"KLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            profile = json.loads(resp.read().decode("utf-8"))
        version_dir = data_dir / "versions" / self.version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        # Profile already has id, inheritsFrom, libraries, mainClass etc
        # Ensure id matches
        profile["id"] = self.version_id
        with open(version_dir / f"{self.version_id}.json", "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        self.progress.emit(100)
        self.log.emit(f"Fabric {self.loader_version} for {self.minecraft_version} installed as {self.version_id}")

    def _ensure_vanilla(self, mc_version: str):
        data_dir = paths.get_data_dir()
        # Check if vanilla json AND jar exist in either location
        for root in (data_dir, paths.get_minecraft_dir()):
            json_path = root / "versions" / mc_version / f"{mc_version}.json"
            jar_path = root / "versions" / mc_version / f"{mc_version}.jar"
            if json_path.is_file() and jar_path.is_file():
                return
            # If json exists but jar missing, remove stale json to force redownload
            if json_path.is_file() and not jar_path.is_file():
                try:
                    json_path.unlink()
                except:
                    pass
        # Need to download vanilla
        self.log.emit(f"Vanilla {mc_version} not found, downloading...")
        # Fetch manifest to get url
        manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
        req = urllib.request.Request(manifest_url, headers={"User-Agent":"KLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            manifest = json.loads(resp.read().decode("utf-8"))
        version_entry = next((v for v in manifest.get("versions",[]) if v["id"]==mc_version), None)
        if not version_entry:
            raise Exception(f"Minecraft version {mc_version} not found")
        version_url = version_entry["url"]
        # Reuse VersionInstaller for vanilla
        installer = VersionInstaller(mc_version, version_url)
        # Run synchronously in this thread
        installer._install()


class QuiltInstaller(FabricInstaller):
    def run(self):
        try:
            self.version_id = f"quilt-loader-{self.loader_version}-{self.minecraft_version}"
            self._install_quilt()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished_install.emit(self.version_id)

    def _install_quilt(self):
        data_dir = paths.get_data_dir()
        self._ensure_vanilla(self.minecraft_version)
        self.progress.emit(30)
        self.log.emit(f"Fetching Quilt profile {self.loader_version} for {self.minecraft_version}...")
        url = f"https://meta.quiltmc.org/v3/versions/loader/{self.minecraft_version}/{self.loader_version}/profile/json"
        req = urllib.request.Request(url, headers={"User-Agent":"KLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            profile = json.loads(resp.read().decode("utf-8"))
        version_dir = data_dir / "versions" / self.version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        profile["id"] = self.version_id
        with open(version_dir / f"{self.version_id}.json", "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        self.progress.emit(100)
        self.log.emit(f"Quilt {self.loader_version} for {self.minecraft_version} installed as {self.version_id}")