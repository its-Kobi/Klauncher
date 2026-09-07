"""Discover installed Java runtimes and select one that matches version metadata."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

from launcher import paths

try:
    import winreg
except ImportError:
    winreg = None

LogFn = Callable[[str], None]


class JavaResolutionError(Exception):
    pass


@dataclass(frozen=True)
class JavaInstallation:
    path: str
    version_string: str
    major: Optional[int]

    def compatible_with(self, required_major: int) -> bool:
        return java_major_compatible(self.major, required_major)


def parse_java_major(version_string: Optional[str]) -> Optional[int]:
    if not version_string:
        return None
    text = version_string.strip()
    match = re.search(r"(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    try:
        first = int(match.group(1))
        if first == 1 and match.group(2) is not None:
            return int(match.group(2))
        return first
    except (TypeError, ValueError):
        return None


def java_major_compatible(actual: Optional[int], required: int) -> bool:
    if actual is None:
        return False
    if required <= 8:
        return actual == 8
    return actual >= required


def class_file_major_for_java(java_major: int) -> Optional[int]:
    mapping = {8: 52, 11: 55, 16: 60, 17: 61, 21: 65, 22: 66, 25: 69}
    return mapping.get(java_major)


_JAVA_VERSION_CACHE: dict = {}
_JAVA_INSTALLS_CACHE: Optional[List[JavaInstallation]] = None
_JAVA_INSTALLS_CACHE_TIME: float = 0.0
_CACHE_TTL: float = 30.0

def _creation_flags():
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0

def get_java_version(java_path: str) -> Optional[str]:
    """Run `java -version` and extract the quoted version string (cached, no console window)."""
    if java_path in _JAVA_VERSION_CACHE:
        return _JAVA_VERSION_CACHE[java_path]
    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_creation_flags(),
        )
        output = result.stderr or result.stdout
        for line in output.splitlines():
            match = re.search(r'"([^"]+)"', line)
            if match:
                _JAVA_VERSION_CACHE[java_path] = match.group(1)
                return match.group(1)
        val = output.strip().split("\n")[0] if output.strip() else None
        _JAVA_VERSION_CACHE[java_path] = val
        return val
    except Exception:
        return None


def detect_java() -> Optional[str]:
    """Return a single Java executable for settings/auto-detect (first discovered)."""
    installs = discover_java_installations()
    if installs:
        return installs[0].path
    return _first_java_path_without_version()


def discover_java_installations(
    extra_paths: Optional[Sequence[str]] = None,
    use_cache: bool = True,
) -> List[JavaInstallation]:
    global _JAVA_INSTALLS_CACHE, _JAVA_INSTALLS_CACHE_TIME
    import time
    if use_cache and extra_paths is None and _JAVA_INSTALLS_CACHE is not None:
        if time.time() - _JAVA_INSTALLS_CACHE_TIME < _CACHE_TTL:
            return list(_JAVA_INSTALLS_CACHE)
    found: List[JavaInstallation] = []
    seen = set()

    for candidate in _java_candidate_paths(extra_paths):
        resolved = _normalize_java_exe(candidate)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        version = get_java_version(resolved)
        found.append(
            JavaInstallation(
                path=resolved,
                version_string=version or "",
                major=parse_java_major(version),
            )
        )
    if extra_paths is None:
        _JAVA_INSTALLS_CACHE = list(found)
        _JAVA_INSTALLS_CACHE_TIME = time.time()
    return found

def clear_java_cache():
    global _JAVA_INSTALLS_CACHE, _JAVA_INSTALLS_CACHE_TIME, _JAVA_VERSION_CACHE
    _JAVA_INSTALLS_CACHE = None
    _JAVA_INSTALLS_CACHE_TIME = 0.0
    _JAVA_VERSION_CACHE.clear()


def resolve_java_executable(
    preferred_path: Optional[str],
    required_major: Optional[int],
    log: Optional[LogFn] = None,
) -> str:
    """Pick a Java executable that satisfies the version's required major version."""
    log = log or (lambda _msg: None)
    preferred = _normalize_java_exe(preferred_path) if preferred_path else None
    extra = [preferred] if preferred else None
    installs = discover_java_installations(extra_paths=extra)

    if required_major is None:
        if preferred:
            log(f"Java: using configured/detected executable {preferred}")
            return preferred
        if installs:
            log(f"Java: no required major version; using {installs[0].path}")
            return installs[0].path
        raise JavaResolutionError(
            "No Java installation was found. Install a JDK/JRE and set the Java path in Settings."
        )

    compatible = [item for item in installs if item.compatible_with(required_major)]
    preferred_install = _installation_for_path(installs, preferred) if preferred else None

    if preferred_install and preferred_install.compatible_with(required_major):
        log(
            f"Java: using configured runtime {preferred_install.path} "
            f"(major {preferred_install.major}, required {required_major})"
        )
        return preferred_install.path

    if compatible:
        chosen = pick_best_java(compatible, required_major)
        if preferred_install and not preferred_install.compatible_with(required_major):
            log(
                f"Configured Java {preferred_install.version_string or preferred} "
                f"(major {preferred_install.major}) cannot run this version "
                f"(requires Java {required_major}). Switching to {chosen.path}."
            )
        else:
            log(f"Java: selected {chosen.path} (major {chosen.major}, required {required_major})")
        return chosen.path

    if preferred and not Path(preferred).is_file():
        log(
            f"Could not verify Java compatibility for '{preferred_path}'. "
            f"This version requires Java {required_major}."
        )
        return preferred_path or preferred

    class_file = class_file_major_for_java(required_major)
    class_note = f" (class file {class_file}.0)" if class_file else ""
    found_desc = _format_installs(installs)
    raise JavaResolutionError(
        f"This Minecraft version requires Java {required_major}{class_note}.\n"
        f"No compatible Java installation was found.\n"
        f"{found_desc}\n"
        "Install a matching JDK and/or set it in Settings. KLauncher will not launch "
        "with an incompatible runtime."
    )


def pick_best_java(candidates: Sequence[JavaInstallation], required_major: int) -> JavaInstallation:
    exact = [item for item in candidates if item.major == required_major]
    if exact:
        return exact[0]
    return min(candidates, key=lambda item: (item.major or 99, item.path))


def _installation_for_path(installs: Sequence[JavaInstallation], path: str) -> Optional[JavaInstallation]:
    target = Path(path)
    for item in installs:
        try:
            if Path(item.path).resolve() == target.resolve():
                return item
        except OSError:
            if item.path == path:
                return item
    return None


def _format_installs(installs: Sequence[JavaInstallation]) -> str:
    if not installs:
        return "Installed Java runtimes: none detected."
    lines = ["Installed Java runtimes:"]
    for item in installs:
        major = item.major if item.major is not None else "?"
        lines.append(f"  - Java {major} ({item.version_string or 'unknown'}) at {item.path}")
    return "\n".join(lines)


def _normalize_java_exe(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        for name in ("java.exe", "java"):
            nested = candidate / "bin" / name
            if nested.is_file():
                return str(nested.resolve())
            nested = candidate / name
            if nested.is_file():
                return str(nested.resolve())
        return None
    if candidate.is_file():
        return str(candidate.resolve())
    return None


def _first_java_path_without_version() -> Optional[str]:
    for candidate in _java_candidate_paths(None):
        normalized = _normalize_java_exe(candidate)
        if normalized:
            return normalized
        which = shutil.which(candidate) if not Path(candidate).is_absolute() else None
        if which:
            return which
    return None


def _java_candidate_paths(extra_paths: Optional[Sequence[str]]) -> List[str]:
    ordered: List[str] = []

    def add(value: Optional[str]) -> None:
        if value and value not in ordered:
            ordered.append(value)

    if extra_paths:
        for item in extra_paths:
            add(item)

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        add(str(Path(java_home) / "bin" / "java.exe"))
        add(str(Path(java_home) / "bin" / "java"))

    which_java = shutil.which("java")
    if which_java:
        add(which_java)

    for key_path in (
        r"SOFTWARE\JavaSoft\Java Runtime Environment",
        r"SOFTWARE\JavaSoft\JDK",
        r"SOFTWARE\JavaSoft\Java Development Kit",
        r"SOFTWARE\Eclipse Adoptium\JDK",
        r"SOFTWARE\Eclipse Foundation\JDK",
        r"SOFTWARE\Microsoft\JDK",
        r"SOFTWARE\Azul Systems\Zulu",
        r"SOFTWARE\BellSoft\Liberica",
    ):
        for home in _registry_java_homes(key_path):
            add(str(Path(home) / "bin" / "java.exe"))

    program_files = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    ]
    vendor_names = (
        "Java",
        "Eclipse Adoptium",
        "Eclipse Foundation",
        "AdoptOpenJDK",
        "Microsoft",
        "Zulu",
        "Amazon Corretto",
        "BellSoft",
        "OpenJDK",
        "Semeru",
        "Temurin",
        "Oracle",
        "JavaSoft",
    )
    for root in program_files:
        if not root:
            continue
        for vendor in vendor_names:
            vendor_dir = root / vendor
            if vendor_dir.is_dir():
                for exe in _direct_java_exes(vendor_dir):
                    add(str(exe))

    for runtime_root in (
        paths.get_minecraft_dir() / "runtime",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Packages" / "Microsoft.4297127D64EC6_8wekyb3d8bbwe" / "LocalCache" / "Local" / "runtime",
        paths.get_data_dir() / "runtime",
    ):
        if runtime_root.is_dir():
            for exe in _java_exes_under(runtime_root, max_depth=6):
                add(str(exe))

    return ordered


def _direct_java_exes(vendor_dir: Path) -> Iterable[Path]:
    """Look for <vendor>/<install>/bin/java without walking unrelated trees."""
    try:
        installs = list(vendor_dir.iterdir())
    except OSError:
        return
    for install in installs:
        if not install.is_dir():
            continue
        for name in ("java.exe", "java"):
            exe = install / "bin" / name
            if exe.is_file():
                yield exe


def _java_exes_under(root: Path, max_depth: int) -> Iterable[Path]:
    if max_depth < 0 or not root.is_dir():
        return
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for child in entries:
        if child.is_file() and child.name.lower() in ("java.exe", "java"):
            yield child
        elif child.is_dir():
            if child.name.lower() == "bin":
                for name in ("java.exe", "java"):
                    exe = child / name
                    if exe.is_file():
                        yield exe
            yield from _java_exes_under(child, max_depth - 1)


def _registry_java_homes(key_path: str) -> List[str]:
    homes: List[str] = []
    if not winreg:
        return homes
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                homes.extend(_registry_homes_from_key(key))
        except OSError:
            continue
    return homes


def _registry_homes_from_key(key) -> List[str]:
    homes: List[str] = []
    try:
        java_home, _ = winreg.QueryValueEx(key, "JavaHome")
        if java_home:
            homes.append(java_home)
    except OSError:
        pass
    index = 0
    while True:
        try:
            sub_name = winreg.EnumKey(key, index)
        except OSError:
            break
        index += 1
        try:
            with winreg.OpenKey(key, sub_name) as sub:
                homes.extend(_registry_homes_from_key(sub))
        except OSError:
            continue
    return homes
