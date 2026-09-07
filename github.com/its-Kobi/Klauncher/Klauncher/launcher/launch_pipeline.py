"""Extensible launch pipeline - generic core + loader-agnostic targets."""
from __future__ import annotations
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from launcher import paths
from launcher.java_detector import JavaResolutionError, resolve_java_executable
from launcher.library_resolver import (
    LibraryResolutionError,
    find_class_jar,
    library_search_roots,
    minecraft_os_name,
    natives_arch,
    resolve_libraries_and_natives,
    write_libraries_dir,
)
from launcher.optifine import (
    LAUNCHWRAPPER_MAIN,
    OptiFineContext,
    detect_optifine,
    ensure_launchwrapper_required_args,
    ensure_tweak_class_arg,
    log_optifine_diagnostics,
    validate_optifine_classpath,
)
from launcher.version_metadata import (
    MetadataError,
    build_game_args,
    build_jvm_args_from_metadata,
    extract_tweak_classes,
    find_client_jar,
    recommended_java_major,
    resolve_metadata_chain,
    rewrite_javaagent_args,
    validate_metadata,
)
from launcher.targets.registry import detect_target

LogFn = Callable[[str], None]

@dataclass
class LaunchPlan:
    version_id: str
    metadata: dict
    java_path: str
    main_class: str
    classpath_entries: List[str]
    natives_dir: Path
    game_dir: Path
    jvm_args: List[str]
    game_args: List[str]
    optifine: OptiFineContext
    recommended_java: Optional[int] = None
    diagnostics: List[str] = field(default_factory=list)
    target_kind: str = "vanilla"
    target_display: str = "Vanilla"

    @property
    def full_args(self) -> List[str]:
        return list(self.jvm_args) + ["-cp", os.pathsep.join(self.classpath_entries), self.main_class] + list(self.game_args)

class LaunchPreparationError(Exception):
    pass

def prepare_launch(
    java_path: str,
    version_id: str,
    username: str,
    uuid: str,
    game_dir: Path,
    ram_gb: int,
    custom_jvm_args: str = "",
    data_dir: Optional[Path] = None,
    log: Optional[LogFn] = None,
    allow_download: bool = True,
    access_token: str = "0",
    user_type: str = "legacy",
    xuid: Optional[str] = None,
) -> LaunchPlan:
    log = log or (lambda _msg: None)
    data_dir = data_dir or paths.get_data_dir()
    game_dir.mkdir(parents=True, exist_ok=True)

    try:
        metadata = resolve_metadata_chain(data_dir, version_id, log)
    except MetadataError as exc:
        raise LaunchPreparationError(str(exc)) from exc

    # Validate metadata before proceeding
    meta_errors = validate_metadata(metadata)
    if meta_errors:
        # Only hard-fail for missing mainClass or id; otherwise warn
        critical = [e for e in meta_errors if "mainClass" in e]
        if critical:
            raise LaunchPreparationError("Invalid version metadata: " + "; ".join(meta_errors))
        for w in meta_errors:
            log(f"Metadata warning: {w}")

    version_id_final = metadata.get("id") or version_id
    os_name = minecraft_os_name()
    arch = "x86" if natives_arch() == "32" else platform_arch_token()
    rec_java = recommended_java_major(metadata)

    try:
        resolved_java = resolve_java_executable(java_path, rec_java, log)
    except JavaResolutionError as exc:
        raise LaunchPreparationError(str(exc)) from exc

    # Detect target (loader-agnostic)
    target = detect_target(version_id_final, metadata)
    target_info = target.describe(version_id_final, metadata)
    log(f"Launch target: {target_info.display_name} ({target.kind})")
    if target_info.loader_version:
        log(f"Loader version: {target_info.loader_version}")

    # Allow target to do pre-resolve hooks
    try:
        target.pre_resolve(metadata, version_id_final, data_dir, log)
    except Exception as exc:
        log(f"Target pre_resolve warning: {exc}")

    client_jar = _resolve_client_jar(metadata, version_id_final, data_dir, log, target.kind)

    try:
        classpath_entries, natives_dir = resolve_libraries_and_natives(
            metadata, data_dir, version_id_final, log, allow_download=allow_download
        )
    except LibraryResolutionError as exc:
        raise LaunchPreparationError(str(exc)) from exc

    # Preserve OptiFine exact behavior via target delegation + direct handling for legacy compat
    optifine = detect_optifine(version_id_final, metadata)
    if target.kind == "optifine":
        try:
            target.post_classpath(metadata, version_id_final, data_dir, classpath_entries, log)
            # refresh optifine context after classpath mutation
            optifine = detect_optifine(version_id_final, metadata)
            from launcher.optifine import OPTIFINE_TWEAKER as _OF_TWEAKER
            from launcher.optifine import LAUNCHWRAPPER_CLASS as _LW_CLASS
            optifine.optifine_jar = find_class_jar(classpath_entries, _OF_TWEAKER) or optifine.optifine_jar
            optifine.launchwrapper_jar = find_class_jar(classpath_entries, _LW_CLASS) or optifine.launchwrapper_jar
        except FileNotFoundError as exc:
            raise LaunchPreparationError(str(exc)) from exc
        except Exception as exc:
            raise LaunchPreparationError(str(exc)) from exc
    else:
        # Generic targets may still have tweaks
        try:
            target.post_classpath(metadata, version_id_final, data_dir, classpath_entries, log)
        except Exception as exc:
            log(f"Target post_classpath warning: {exc}")

    if client_jar is not None:
        _ensure_client_jar_last(classpath_entries, client_jar)

    main_class = metadata.get("mainClass") or "net.minecraft.client.main.Main"
    asset_index_id = (metadata.get("assetIndex") or {}).get("id") or metadata.get("assets") or "legacy"
    assets_dir = _resolve_assets_dir(data_dir)
    library_dir = write_libraries_dir()
    tweak_classes = extract_tweak_classes(metadata)
    if optifine.is_optifine and optifine.uses_launchwrapper and optifine.tweaker_class:
        if optifine.tweaker_class not in tweak_classes:
            tweak_classes.append(optifine.tweaker_class)

    # Never log access_token; keep it out of diagnostics except via placeholder
    replacements = {
        "${auth_player_name}": username,
        "${version_name}": version_id_final,
        "${game_directory}": str(game_dir),
        "${assets_root}": str(assets_dir),
        "${assets_index_name}": asset_index_id,
        "${auth_uuid}": uuid,
        "${auth_access_token}": access_token,
        "${user_properties}": "{}",
        "${user_type}": user_type,
        "${version_type}": metadata.get("type", "release"),
        "${resolution_width}": "854",
        "${resolution_height}": "480",
        "${natives_directory}": str(natives_dir),
        "${launcher_name}": "KLauncher",
        "${launcher_version}": "1.0",
        "${classpath}": os.pathsep.join(classpath_entries),
        "${library_directory}": str(library_dir),
        "${classpath_separator}": os.pathsep,
        "${clientid}": "",
        "${auth_xuid}": xuid or "",
    }

    game_args = build_game_args(metadata, replacements, os_name, arch)
    game_args = _inject_standard_game_args(game_args, game_dir, assets_dir, version_id_final, asset_index_id)

    uses_launchwrapper = main_class == LAUNCHWRAPPER_MAIN
    if uses_launchwrapper:
        game_args = ensure_launchwrapper_required_args(
            game_args, game_dir, assets_dir, version_id_final, asset_index_id
        )
        for tweaker in tweak_classes:
            game_args = ensure_tweak_class_arg(game_args, tweaker)
        # also let target add tweakers
        game_args = target.tweak_game_args(game_args, metadata)

    if "--width" not in game_args:
        game_args.extend(["--width", "854", "--height", "480"])

    jvm_meta = build_jvm_args_from_metadata(metadata, replacements, os_name, arch)
    jvm_args = [f"-Xmx{ram_gb}G"]
    if custom_jvm_args:
        # Filter custom JVM args: -javaagent should only apply to custom clients
        # Fabric/Forge/Quilt etc with mods will crash if Badlion Agent is loaded
        # (mixin transformer conflict: sponge-mixin vs javassist)
        raw_custom = shlex.split(custom_jvm_args, posix=False)
        filtered_custom = []
        for arg in raw_custom:
            if "-javaagent" in arg and target.kind != "custom":
                log(f"Skipping Java agent from custom JVM args for {target.kind} target: {arg} (only for custom clients)")
                continue
            filtered_custom.append(arg)
        jvm_args.extend(filtered_custom)
    jvm_args.extend(jvm_meta)
    # Loader-specific extra JVM args (only for targets that declare them explictly)
    try:
        extra = target.extra_jvm_args(metadata, version_id_final, data_dir)
        if extra:
            log(f"Target extra JVM args: {extra}")
            jvm_args.extend(extra)
    except Exception as exc:
        log(f"Target extra_jvm_args warning: {exc}")
    jvm_args = rewrite_javaagent_args(
        [_substitute_token(arg, replacements) for arg in jvm_args],
        [library_dir, *library_search_roots(data_dir), data_dir],
    )
    if not any(arg.startswith("-Djava.library.path=") for arg in jvm_args):
        jvm_args.append(f"-Djava.library.path={natives_dir}")

    # Validation via target + generic
    generic_errors = target.validate(metadata, classpath_entries)
    if generic_errors:
        for err in generic_errors:
            log(err)
        # For vanilla/fabric etc, only hard-fail if critical
        if target.kind == "optifine":
            raise LaunchPreparationError("Validation failed:\n" + "\n".join(generic_errors))
        else:
            # Fabric validation: fail if fabric loader missing
            if target.kind in ("fabric", "quilt") and any("loader" in e.lower() for e in generic_errors):
                raise LaunchPreparationError("Validation failed:\n" + "\n".join(generic_errors))

    of_errors = validate_optifine_classpath(optifine, classpath_entries)
    if of_errors:
        for err in of_errors:
            log(err)
        raise LaunchPreparationError("OptiFine classpath validation failed:\n" + "\n".join(of_errors))

    if uses_launchwrapper:
        if find_class_jar(classpath_entries, LAUNCHWRAPPER_MAIN) is None:
            raise LaunchPreparationError(
                f"{LAUNCHWRAPPER_MAIN} is the main class but was not found on the final classpath "
                f"({len(classpath_entries)} jars)."
            )
        for tweaker in tweak_classes:
            if find_class_jar(classpath_entries, tweaker) is None:
                raise LaunchPreparationError(
                    f"Tweaker {tweaker} is declared in version metadata but was not found on the classpath."
                )

    required_flags = ["--gameDir", "--assetsDir", "--version"]
    if uses_launchwrapper and tweak_classes:
        required_flags.append("--tweakClass")
    missing = _missing_flags(game_args, required_flags)
    if missing:
        raise LaunchPreparationError(f"Missing required game arguments: {', '.join(missing)}")

    plan = LaunchPlan(
        version_id=version_id_final,
        metadata=metadata,
        java_path=resolved_java,
        main_class=main_class,
        classpath_entries=classpath_entries,
        natives_dir=natives_dir,
        game_dir=game_dir,
        jvm_args=jvm_args,
        game_args=game_args,
        optifine=optifine,
        recommended_java=rec_java,
        target_kind=target.kind,
        target_display=target_info.display_name,
    )
    _log_plan(plan, log)
    return plan


def platform_arch_token() -> str:
    import platform
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        return "x86_64"
    return machine


def _substitute_token(token: str, replacements: dict) -> str:
    for placeholder, value in replacements.items():
        token = token.replace(placeholder, value)
    return token


def _resolve_client_jar(metadata: dict, version_id: str, data_dir: Path, log: LogFn, target_kind: str = "vanilla") -> Optional[Path]:
    try:
        return find_client_jar(metadata, version_id, data_dir, log)
    except MetadataError as exc:
        # Fabric/Quilt still need client jar via inheritsFrom; if not found, error
        if metadata.get("_inheritsFrom") or metadata.get("jar") or (metadata.get("downloads") or {}).get("client"):
            raise LaunchPreparationError(str(exc)) from exc
        # For custom versions that declare mainClass but no jar, allow no client jar (like Badlion)
        if metadata.get("mainClass") and target_kind in ("custom", "fabric", "quilt", "forge"):
            log(
                f"No client JAR for {version_id}; launching with libraries and mainClass "
                f"{metadata.get('mainClass')!r} from version metadata."
            )
            return None
        if metadata.get("mainClass") and metadata.get("mainClass") != "net.minecraft.client.main.Main":
            log(
                f"No client JAR for {version_id}; launching with libraries and mainClass "
                f"{metadata.get('mainClass')!r} from version metadata."
            )
            return None
        raise LaunchPreparationError(str(exc)) from exc


def _ensure_client_jar_last(classpath_entries: List[str], client_jar: Path) -> None:
    resolved_client = str(client_jar.resolve())
    classpath_entries[:] = [
        entry for entry in classpath_entries
        if not Path(entry).exists() or str(Path(entry).resolve()) != resolved_client
    ]
    classpath_entries.append(str(client_jar))


def _resolve_assets_dir(data_dir: Path) -> Path:
    primary = data_dir / "assets"
    if (primary / "indexes").exists() or (primary / "objects").exists():
        return primary
    mc_assets = paths.get_minecraft_dir() / "assets"
    if mc_assets.exists():
        return mc_assets
    kl_assets = paths.get_data_dir() / "assets"
    if kl_assets.exists():
        return kl_assets
    return primary


def _inject_standard_game_args(
    args: List[str],
    game_dir: Path,
    assets_dir: Path,
    version_id: str,
    asset_index: str,
) -> List[str]:
    new_args = list(args)
    pairs = {
        "--gameDir": str(game_dir),
        "--assetsDir": str(assets_dir),
        "--version": version_id,
        "--assetIndex": asset_index,
    }
    for flag, value in pairs.items():
        if flag not in new_args:
            new_args.extend([flag, value])
    return new_args


def _missing_flags(args: List[str], required: List[str]) -> List[str]:
    missing = []
    for key in required:
        if key not in args:
            missing.append(key)
            continue
        idx = args.index(key)
        if idx + 1 >= len(args) or args[idx + 1].startswith("--"):
            missing.append(f"{key} (missing value)")
    return missing


def _log_plan(plan: LaunchPlan, log: LogFn) -> None:
    log("=== VERSION RESOLUTION ===")
    log(f"Selected version: {plan.version_id} [{plan.target_display}]")
    log(f"Main class: {plan.main_class}")
    if plan.recommended_java:
        log(f"Required Java major version: {plan.recommended_java}")
    log(f"Java executable: {plan.java_path}")

    log_optifine_diagnostics(plan.optifine, plan.classpath_entries, log)

    log("=== LIBRARIES / CLASSPATH ===")
    log(f"Classpath entries: {len(plan.classpath_entries)}")
    for entry in plan.classpath_entries:
        log(f"[OK] {entry}")

    log("=== NATIVES ===")
    log(f"Natives directory: {plan.natives_dir}")

    log("=== JVM ARGUMENTS ===")
    for arg in plan.jvm_args:
        log(f"  {arg}")

    log("=== GAME ARGUMENTS ===")
    for idx, arg in enumerate(plan.game_args):
        # Never log access token value: skip flag and its value
        if "accessToken" in arg:
            continue
        if idx > 0 and plan.game_args[idx-1] == "--accessToken":
            continue
        # Also skip legacy "0" token which is not sensitive
        if arg == "0" and idx > 0 and "accessToken" in plan.game_args[idx-1]:
            continue
        log(f"  {arg}")
    if "--tweakClass" in plan.game_args:
        idx = 0
        while "--tweakClass" in plan.game_args[idx:]:
            pos = plan.game_args.index("--tweakClass", idx)
            if pos + 1 < len(plan.game_args):
                log(f"tweakClass: {plan.game_args[pos + 1]}")
            idx = pos + 1
