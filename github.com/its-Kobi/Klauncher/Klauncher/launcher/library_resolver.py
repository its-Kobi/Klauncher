"""Library, native, and Maven path resolution shared by all Minecraft versions."""

from __future__ import annotations

import hashlib
import platform
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from launcher import paths

LogFn = Callable[[str], None]


def minecraft_os_name() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "osx"
    return system


def natives_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64", "arm64", "aarch64"):
        return "64"
    if machine in ("x86", "i386", "i686"):
        return "32"
    return "64"


def substitute_arch(value: str) -> str:
    return value.replace("${arch}", natives_arch())


@dataclass
class MavenCoordinate:
    group: str
    artifact: str
    version: str
    classifier: Optional[str] = None
    extension: str = "jar"

    @classmethod
    def from_string(cls, coord: str) -> "MavenCoordinate":
        ext = "jar"
        if "@" in coord:
            coord, ext = coord.rsplit("@", 1)
        parts = coord.split(":")
        if len(parts) == 3:
            group, artifact, version = parts
            classifier = None
        elif len(parts) == 4:
            group, artifact, version, classifier = parts
        else:
            raise ValueError(f"Invalid Maven coordinate: {coord}")
        return cls(group, artifact, version, classifier, ext)

    @property
    def base_path(self) -> Path:
        return Path(self.group.replace(".", "/")) / self.artifact / self.version

    @property
    def filename(self) -> str:
        if self.classifier:
            return f"{self.artifact}-{self.version}-{self.classifier}.{self.extension}"
        return f"{self.artifact}-{self.version}.{self.extension}"

    def relative_path(self, classifier: Optional[str] = None) -> Path:
        use = classifier if classifier is not None else self.classifier
        if use:
            name = f"{self.artifact}-{self.version}-{use}.{self.extension}"
        else:
            name = f"{self.artifact}-{self.version}.{self.extension}"
        return self.base_path / name


@dataclass
class LibraryRule:
    action: str
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    arch: Optional[str] = None

    def matches(self, os_name: str, arch: str) -> bool:
        if self.os_name is not None and self.os_name != os_name:
            return False
        if self.arch is not None and self.arch != arch:
            return False
        return True


@dataclass
class Library:
    name: str
    raw: Dict[str, Any]
    rules: List[LibraryRule] = field(default_factory=list)
    downloads: Dict[str, Any] = field(default_factory=dict)
    natives: Optional[Dict[str, str]] = None

    def is_allowed(self, os_name: str, arch: str) -> bool:
        if not self.rules:
            return True
        allowed = False
        for rule in self.rules:
            if rule.matches(os_name, arch):
                allowed = rule.action == "allow"
        return allowed

    def artifact_download(self) -> Optional[Dict[str, Any]]:
        return self.downloads.get("artifact")

    def classifier_download(self, classifier: str) -> Optional[Dict[str, Any]]:
        return self.downloads.get("classifiers", {}).get(classifier)


def parse_library(lib_raw: dict) -> Optional[Library]:
    name = lib_raw.get("name")
    if not name:
        return None
    rules = []
    for rule_raw in lib_raw.get("rules", []):
        os_info = rule_raw.get("os") or {}
        rules.append(LibraryRule(
            action=rule_raw.get("action", "allow"),
            os_name=os_info.get("name"),
            os_version=os_info.get("version"),
            arch=os_info.get("arch"),
        ))
    return Library(
        name=name,
        raw=lib_raw,
        rules=rules,
        downloads=lib_raw.get("downloads") or {},
        natives=lib_raw.get("natives"),
    )


def library_search_roots(data_dir: Path) -> List[Path]:
    roots: List[Path] = []
    for candidate in (
        data_dir / "libraries",
        paths.get_data_dir() / "libraries",
        paths.get_minecraft_dir() / "libraries",
    ):
        resolved = candidate.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return roots


def write_libraries_dir() -> Path:
    dest = paths.get_data_dir() / "libraries"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def find_existing_library(rel_path: Path, search_roots: List[Path]) -> Optional[Path]:
    for root in search_roots:
        candidate = root / rel_path
        if candidate.is_file():
            return candidate
    return None


def maven_urls(rel_path: Path, base_url: Optional[str] = None) -> List[str]:
    rel = str(rel_path).replace("\\", "/")
    urls: List[str] = []
    if base_url:
        urls.append(base_url.rstrip("/") + "/" + rel)
    urls.extend(
        [
            f"https://libraries.minecraft.net/{rel}",
            f"https://repo1.maven.org/maven2/{rel}",
        ]
    )
    return urls


def _library_base_url(lib: Library) -> str:
    return str(lib.raw.get("url") or "").strip()


def download_file(url: str, dest: Path, sha1: Optional[str], log: LogFn) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response, open(dest, "wb") as handle:
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                handle.write(chunk)
    except Exception as exc:
        log(f"Download error ({url}): {exc}")
        dest.unlink(missing_ok=True)
        return False

    if sha1 and not _verify_sha1(dest, sha1):
        log(f"SHA1 mismatch for {dest.name}")
        dest.unlink(missing_ok=True)
        return False
    return True


def download_first_available(urls: List[str], dest: Path, sha1: Optional[str], log: LogFn) -> bool:
    for url in urls:
        log(f"Downloading: {url}")
        if download_file(url, dest, sha1, log):
            return True
    return False


def _verify_sha1(file_path: Path, expected_sha1: str) -> bool:
    digest = hashlib.sha1()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(4096), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected_sha1


def extract_natives(archive_path: Path, dest_dir: Path, exclude_prefixes: Optional[List[str]] = None) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    excludes = exclude_prefixes or ["META-INF/"]
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            if any(member.startswith(prefix) or member == prefix.rstrip("/") for prefix in excludes):
                continue
            zf.extract(member, dest_dir)


def natives_dir_for_version(version_id: str) -> Path:
    dest = paths.get_data_dir() / "natives" / version_id
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def resolve_native_classifier(lib: Library, os_name: str) -> Optional[str]:
    if not lib.natives:
        return None
    raw = lib.natives.get(os_name)
    if not raw:
        return None
    return substitute_arch(raw)


def class_in_jar(jar_path: Path, class_name: str) -> bool:
    class_path = class_name.replace(".", "/") + ".class"
    try:
        with zipfile.ZipFile(jar_path) as zf:
            return class_path in zf.namelist()
    except Exception:
        return False


def find_class_jar(classpath_entries: List[str], class_name: str) -> Optional[Path]:
    for entry in classpath_entries:
        path = Path(entry)
        if path.suffix.lower() == ".jar" and path.is_file() and class_in_jar(path, class_name):
            return path
    return None


class LibraryResolutionError(Exception):
    pass


def resolve_libraries_and_natives(
    version_data: dict,
    data_dir: Path,
    version_id: str,
    log: LogFn,
    allow_download: bool = True,
) -> Tuple[List[str], Path]:
    os_name = minecraft_os_name()
    arch = "x86" if natives_arch() == "32" else "x86_64"
    search_roots = library_search_roots(data_dir)
    natives_dir = natives_dir_for_version(version_id)
    classpath: List[str] = []
    seen_classpath: set = set()

    for lib_raw in version_data.get("libraries", []):
        lib = parse_library(lib_raw)
        if not lib:
            continue
        if not lib.is_allowed(os_name, arch):
            log(f"Skipped library (rules): {lib.name}")
            continue

        coord = MavenCoordinate.from_string(lib.name)
        artifact = lib.artifact_download()
        has_natives = bool(lib.natives)

        if artifact:
            jar_path = _resolve_artifact_file(lib, coord, artifact, search_roots, allow_download, log)
            _add_classpath(classpath, seen_classpath, jar_path)

        elif has_natives:
            log(f"Native-only library (no classpath artifact): {lib.name}")
        else:
            jar_path = _resolve_unannotated_artifact(lib, coord, search_roots, allow_download, log)
            _add_classpath(classpath, seen_classpath, jar_path)

        if has_natives:
            _resolve_and_extract_natives(lib, coord, search_roots, natives_dir, os_name, allow_download, log)

    return classpath, natives_dir


def _add_classpath(classpath: List[str], seen: set, jar_path: Path) -> None:
    key = str(jar_path.resolve())
    if key not in seen:
        seen.add(key)
        classpath.append(str(jar_path))


def _resolve_artifact_file(
    lib: Library,
    coord: MavenCoordinate,
    artifact: Dict[str, Any],
    search_roots: List[Path],
    allow_download: bool,
    log: LogFn,
) -> Path:
    if artifact.get("path"):
        rel = Path(artifact["path"])
    else:
        rel = coord.relative_path()

    existing = find_existing_library(rel, search_roots)
    if existing:
        log(f"Found: {existing}")
        return existing

    log(f"Missing library: {lib.name} ({rel})")
    dest = write_libraries_dir() / rel
    urls: List[str] = []
    artifact_url = (artifact.get("url") or "").strip()
    if artifact_url:
        urls.append(artifact_url)
    urls.extend(maven_urls(rel, _library_base_url(lib)))
    if not urls or not allow_download or not download_first_available(urls, dest, artifact.get("sha1"), log):
        raise LibraryResolutionError(f"Could not resolve library {lib.name} at {rel}")
    log(f"Downloaded: {dest}")
    return dest


def _resolve_unannotated_artifact(
    lib: Library,
    coord: MavenCoordinate,
    search_roots: List[Path],
    allow_download: bool,
    log: LogFn,
) -> Path:
    rel = coord.relative_path()
    existing = find_existing_library(rel, search_roots)
    if existing:
        log(f"Found (Maven layout): {existing}")
        return existing

    log(f"Missing unannotated library: {coord.group}:{coord.artifact}:{coord.version}")
    dest = write_libraries_dir() / rel
    if coord.group.lower() == "optifine":
        raise LibraryResolutionError(
            f"OptiFine artifact not found locally: {rel}. "
            "Install OptiFine with the official installer so the library exists under libraries/optifine."
        )
    urls = maven_urls(rel, _library_base_url(lib))
    if not allow_download or not download_first_available(urls, dest, None, log):
        raise LibraryResolutionError(
            f"Could not download {coord.group}:{coord.artifact}:{coord.version} "
            f"(looked for {rel} under libraries/ and configured Maven URLs)."
        )
    log(f"Downloaded: {dest}")
    return dest


def _resolve_and_extract_natives(
    lib: Library,
    coord: MavenCoordinate,
    search_roots: List[Path],
    natives_dir: Path,
    os_name: str,
    allow_download: bool,
    log: LogFn,
) -> None:
    classifier = resolve_native_classifier(lib, os_name)
    if not classifier:
        log(f"No natives classifier for OS {os_name}: {lib.name}")
        return

    classifier_dl = lib.classifier_download(classifier)
    if classifier_dl and classifier_dl.get("path"):
        rel = Path(classifier_dl["path"])
    else:
        rel = coord.relative_path(classifier)

    archive = find_existing_library(rel, search_roots)
    if archive is None:
        dest = write_libraries_dir() / rel
        urls: List[str] = []
        if classifier_dl and classifier_dl.get("url"):
            urls.append(classifier_dl["url"])
        urls.extend(maven_urls(rel))
        sha1 = classifier_dl.get("sha1") if classifier_dl else None
        log(f"Missing natives archive: {rel}")
        if not allow_download or not download_first_available(urls, dest, sha1, log):
            raise LibraryResolutionError(f"Could not resolve natives {lib.name} ({classifier})")
        archive = dest
        log(f"Downloaded natives: {archive}")
    else:
        log(f"Found natives archive: {archive}")

    extract_natives(archive, natives_dir, exclude_prefixes=(lib.raw.get("extract") or {}).get("exclude"))
    log(f"Extracted natives from {archive.name} -> {natives_dir}")
