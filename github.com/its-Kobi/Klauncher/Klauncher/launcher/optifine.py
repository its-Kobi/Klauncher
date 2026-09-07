"""Isolated OptiFine launch subsystem.

Handles detection, artifact resolution, LaunchWrapper/tweaker integration,
classpath validation, and diagnostics. Vanilla launching does not depend on
the strategy internals here.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from launcher.library_resolver import (
    MavenCoordinate,
    class_in_jar,
    find_class_jar,
    find_existing_library,
    library_search_roots,
)

LogFn = Callable[[str], None]

OPTIFINE_TWEAKER = "optifine.OptiFineTweaker"
LAUNCHWRAPPER_MAIN = "net.minecraft.launchwrapper.Launch"
LAUNCHWRAPPER_CLASS = "net.minecraft.launchwrapper.Launch"


@dataclass
class OptiFineContext:
    is_optifine: bool
    version_id: str
    base_minecraft: Optional[str]
    launch_mode: str
    tweaker_class: Optional[str]
    optifine_jar: Optional[Path] = None
    launchwrapper_jar: Optional[Path] = None
    extra_libraries: List[Path] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def uses_launchwrapper(self) -> bool:
        return self.launch_mode in ("legacy", "legacy_modern_args")


def parse_minecraft_version(text: Optional[str]) -> Optional[Tuple[int, int, int]]:
    if not text:
        return None
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def detect_optifine(version_id: str, metadata: dict) -> OptiFineContext:
    libraries = metadata.get("libraries") or []
    has_optifine_lib = any(
        str(lib.get("name", "")).lower().startswith("optifine:optifine:")
        for lib in libraries
    )
    tweaker = _find_tweaker(metadata)
    is_optifine = (
        "optifine" in version_id.lower()
        or has_optifine_lib
        or (tweaker == OPTIFINE_TWEAKER)
    )
    base = metadata.get("_inheritsFrom") or metadata.get("inheritsFrom")
    if not base and is_optifine:
        parsed = re.match(r"^(\d+\.\d+(?:\.\d+)?)", version_id)
        base = parsed.group(1) if parsed else None

    main_class = metadata.get("mainClass") or ""
    launch_mode = "vanilla"
    if is_optifine:
        launch_mode = _select_launch_mode(base, main_class, metadata)

    return OptiFineContext(
        is_optifine=is_optifine,
        version_id=version_id,
        base_minecraft=base,
        launch_mode=launch_mode,
        tweaker_class=tweaker if is_optifine else None,
    )


def _select_launch_mode(base: Optional[str], main_class: str, metadata: dict) -> str:
    if LAUNCHWRAPPER_MAIN not in main_class:
        return "version_metadata"
    parsed = parse_minecraft_version(base)
    if parsed and (parsed[0], parsed[1]) >= (1, 13) and metadata.get("arguments"):
        return "legacy_modern_args"
    return "legacy"


def _find_tweaker(metadata: dict) -> Optional[str]:
    args = metadata.get("minecraftArguments") or ""
    if "--tweakClass" in args:
        tokens = args.split()
        for index, token in enumerate(tokens):
            if token == "--tweakClass" and index + 1 < len(tokens):
                return tokens[index + 1]
    game = (metadata.get("arguments") or {}).get("game") or []
    for index, item in enumerate(game):
        if item == "--tweakClass" and index + 1 < len(game) and isinstance(game[index + 1], str):
            return game[index + 1]
    return None


def apply_optifine(
    ctx: OptiFineContext,
    metadata: dict,
    data_dir: Path,
    classpath_entries: List[str],
    log: LogFn,
) -> OptiFineContext:
    if not ctx.is_optifine:
        return ctx

    search_roots = library_search_roots(data_dir)
    ctx.optifine_jar = _resolve_optifine_jar(metadata, search_roots, log)
    ctx.launchwrapper_jar = _resolve_launchwrapper_jar(metadata, search_roots, classpath_entries, log)

    if ctx.optifine_jar:
        _ensure_on_classpath(classpath_entries, ctx.optifine_jar, place="front")
        log(f"OptiFine library JAR: {ctx.optifine_jar}")
    if ctx.launchwrapper_jar:
        _ensure_on_classpath(classpath_entries, ctx.launchwrapper_jar, place="front")
        log(f"LaunchWrapper JAR: {ctx.launchwrapper_jar}")

    if ctx.uses_launchwrapper:
        if not ctx.tweaker_class:
            ctx.tweaker_class = OPTIFINE_TWEAKER
    return ctx


def _optifine_library_names(metadata: dict) -> List[str]:
    names = []
    for lib in metadata.get("libraries") or []:
        name = lib.get("name") or ""
        if name.lower().startswith("optifine:optifine:"):
            names.append(name)
    return names


def _resolve_optifine_jar(metadata: dict, search_roots: List[Path], log: LogFn) -> Path:
    names = _optifine_library_names(metadata)
    for name in names:
        coord = MavenCoordinate.from_string(name)
        rel = coord.relative_path()
        found = find_existing_library(rel, search_roots)
        if found:
            if class_in_jar(found, OPTIFINE_TWEAKER) or class_in_jar(found, "optifine.OptiFineClassTransformer"):
                return found
            log(f"Ignoring OptiFine path that does not contain OptiFine classes: {found}")

    for root in search_roots:
        optifine_root = root / "optifine" / "OptiFine"
        if not optifine_root.is_dir():
            continue
        for jar in sorted(optifine_root.rglob("*.jar")):
            if class_in_jar(jar, OPTIFINE_TWEAKER):
                log(f"Located OptiFine JAR by class scan: {jar}")
                return jar

    raise FileNotFoundError(
        "Could not resolve the OptiFine library JAR (the one that contains "
        "optifine.OptiFineTweaker). KLauncher will not use the version client JAR "
        "as a substitute. Run the OptiFine installer so "
        "libraries/optifine/OptiFine/<version>/OptiFine-<version>.jar exists."
    )


def _launchwrapper_names(metadata: dict) -> List[str]:
    names = []
    for lib in metadata.get("libraries") or []:
        name = lib.get("name") or ""
        lower = name.lower()
        if lower.startswith("net.minecraft:launchwrapper:") or lower.startswith("optifine:launchwrapper-of:"):
            names.append(name)
    if not names:
        names.append("net.minecraft:launchwrapper:1.12")
    return names


def _resolve_launchwrapper_jar(
    metadata: dict,
    search_roots: List[Path],
    classpath_entries: List[str],
    log: LogFn,
) -> Path:
    existing = find_class_jar(classpath_entries, LAUNCHWRAPPER_CLASS)
    if existing:
        return existing

    for name in _launchwrapper_names(metadata):
        coord = MavenCoordinate.from_string(name)
        found = find_existing_library(coord.relative_path(), search_roots)
        if found and class_in_jar(found, LAUNCHWRAPPER_CLASS):
            return found

    for root in search_roots:
        for pattern in (
            root / "net" / "minecraft" / "launchwrapper",
            root / "optifine" / "launchwrapper-of",
        ):
            if not pattern.is_dir():
                continue
            for jar in sorted(pattern.rglob("*.jar"), reverse=True):
                if class_in_jar(jar, LAUNCHWRAPPER_CLASS):
                    log(f"Located LaunchWrapper by class scan: {jar}")
                    return jar

    raise FileNotFoundError(
        "Could not resolve net.minecraft.launchwrapper.Launch. "
        "Expected libraries/net/minecraft/launchwrapper/<ver>/launchwrapper-<ver>.jar "
        "or optifine/launchwrapper-of."
    )


def _ensure_on_classpath(classpath_entries: List[str], jar: Path, place: str = "front") -> None:
    resolved = str(jar.resolve())
    normalized = [str(Path(entry).resolve()) if Path(entry).exists() else entry for entry in classpath_entries]
    if resolved in normalized:
        index = normalized.index(resolved)
        if place == "front" and index != 0:
            classpath_entries.insert(0, classpath_entries.pop(index))
        return
    if place == "front":
        classpath_entries.insert(0, str(jar))
    else:
        classpath_entries.append(str(jar))


def ensure_tweak_class_arg(game_args: List[str], tweaker: str) -> List[str]:
    existing = []
    index = 0
    while index < len(game_args):
        if game_args[index] == "--tweakClass" and index + 1 < len(game_args) and not game_args[index + 1].startswith("--"):
            existing.append(game_args[index + 1])
            index += 2
            continue
        index += 1
    if tweaker in existing:
        return game_args
    return list(game_args) + ["--tweakClass", tweaker]


def ensure_launchwrapper_required_args(
    game_args: List[str],
    game_dir: Path,
    assets_dir: Path,
    version_id: str,
    asset_index: str,
) -> List[str]:
    """LaunchWrapper + OptiFineTweaker require these before Tweaker.acceptOptions."""
    required = [
        ("--gameDir", str(game_dir)),
        ("--assetsDir", str(assets_dir)),
        ("--version", version_id),
        ("--assetIndex", asset_index),
    ]
    result = list(game_args)
    for flag, value in required:
        if flag not in result:
            result.extend([flag, value])
            continue
        idx = result.index(flag)
        if idx + 1 >= len(result) or result[idx + 1].startswith("--"):
            result.insert(idx + 1, value)
    return result


def validate_optifine_classpath(ctx: OptiFineContext, classpath_entries: List[str]) -> List[str]:
    errors: List[str] = []
    if not ctx.is_optifine:
        return errors

    if ctx.uses_launchwrapper:
        lw = find_class_jar(classpath_entries, LAUNCHWRAPPER_CLASS)
        if not lw:
            errors.append(
                f"{LAUNCHWRAPPER_CLASS} not found on the final classpath "
                f"({len(classpath_entries)} jars)."
            )
        else:
            ctx.launchwrapper_jar = lw

        tweaker = ctx.tweaker_class or OPTIFINE_TWEAKER
        of_jar = find_class_jar(classpath_entries, tweaker)
        if not of_jar:
            errors.append(
                f"{tweaker} not found on the final classpath "
                f"({len(classpath_entries)} jars)."
            )
        else:
            ctx.optifine_jar = of_jar
            client_like = of_jar.name.lower().endswith("-optifine_hd") or "optifine_hd" in of_jar.name.lower()
            if client_like and "libraries" not in str(of_jar).replace("\\", "/").lower():
                errors.append(
                    f"{tweaker} was found in {of_jar}, which looks like a version client JAR. "
                    "The OptiFine library under libraries/optifine must be on the classpath instead."
                )
    return errors


def log_optifine_diagnostics(ctx: OptiFineContext, classpath_entries: Sequence[str], log: LogFn) -> None:
    if not ctx.is_optifine:
        return
    lw_found = find_class_jar(list(classpath_entries), LAUNCHWRAPPER_CLASS)
    tweaker = ctx.tweaker_class or OPTIFINE_TWEAKER
    of_found = find_class_jar(list(classpath_entries), tweaker)
    log("=== OPTIFINE ===")
    log(f"OptiFine launch mode: {ctx.launch_mode}")
    log(f"Minecraft base version: {ctx.base_minecraft}")
    log(f"Detected OptiFine version: {ctx.version_id}")
    log(f"LaunchWrapper: {lw_found or ctx.launchwrapper_jar}")
    log(f"OptiFine: {of_found or ctx.optifine_jar}")
    log(f"OptiFineTweaker: {'found' if of_found else 'MISSING'}")
    log(f"LaunchWrapper Launch: {'found' if lw_found else 'MISSING'}")
    log(f"Classpath entries: {len(classpath_entries)}")
    for note in ctx.notes:
        log(f"Note: {note}")


def jar_contains(path: Path, class_name: str) -> bool:
    return class_in_jar(path, class_name)


def list_jar_classes_sample(path: Path, prefix: str) -> List[str]:
    try:
        with zipfile.ZipFile(path) as zf:
            return [name for name in zf.namelist() if name.startswith(prefix) and name.endswith(".class")][:20]
    except Exception:
        return []
