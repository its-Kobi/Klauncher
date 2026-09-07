"""Minecraft version JSON inheritance and argument merging."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from launcher import paths

LogFn = Callable[[str], None]


class MetadataError(Exception):
    pass


def version_json_candidates(version_id: str, data_dir: Path) -> List[Path]:
    seen = []
    result = []
    for root in (data_dir, paths.get_minecraft_dir(), paths.get_data_dir()):
        candidate = (root / "versions" / version_id / f"{version_id}.json").resolve()
        if candidate not in seen:
            seen.append(candidate)
            result.append(candidate)
    return result


def load_version_json(version_id: str, data_dir: Path) -> dict:
    for path in version_json_candidates(version_id, data_dir):
        if path.is_file():
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            data["_json_path"] = str(path)
            data["_versions_root"] = str(path.parent.parent)
            return data
    raise MetadataError(f"Version JSON not found for {version_id}")


def resolve_metadata_chain(data_dir: Path, version_id: str, log: LogFn) -> dict:
    chain_ids: List[str] = []
    documents: List[dict] = []
    current = version_id
    visited = set()
    while current:
        if current in visited:
            raise MetadataError(f"Circular inheritance involving {current}")
        visited.add(current)
        chain_ids.append(current)
        data = load_version_json(current, data_dir)
        documents.append(data)
        current = data.get("inheritsFrom")

    log(f"Version inheritance chain: {' -> '.join(chain_ids)}")

    merged: Dict[str, Any] = {}
    for data in reversed(documents):
        merged = merge_version_documents(merged, data)

    merged["id"] = version_id
    merged["_chain"] = chain_ids
    merged["_inheritsFrom"] = documents[0].get("inheritsFrom") if documents else None
    return merged


def merge_version_documents(parent: dict, child: dict) -> dict:
    if not parent:
        merged = dict(child)
        merged["libraries"] = list(child.get("libraries") or [])
        return merged

    merged = dict(parent)
    for key, value in child.items():
        if key in ("libraries", "arguments", "minecraftArguments"):
            continue
        merged[key] = value

    merged["libraries"] = merge_libraries(
        list(parent.get("libraries") or []),
        list(child.get("libraries") or []),
    )

    if "minecraftArguments" in child:
        merged["minecraftArguments"] = child["minecraftArguments"]
    elif "minecraftArguments" in parent and "arguments" not in child:
        merged["minecraftArguments"] = parent["minecraftArguments"]

    if "arguments" in parent or "arguments" in child:
        parent_args = parent.get("arguments") or {}
        child_args = child.get("arguments") or {}
        merged["arguments"] = {
            "game": list(parent_args.get("game") or []) + list(child_args.get("game") or []),
            "jvm": list(parent_args.get("jvm") or []) + list(child_args.get("jvm") or []),
        }

    return merged


def library_override_key(lib: dict) -> str:
    name = str(lib.get("name") or "")
    parts = name.split(":")
    if len(parts) >= 4:
        return f"{parts[0]}:{parts[1]}:{parts[3]}"
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return name


def merge_libraries(parent_libs: List[dict], child_libs: List[dict]) -> List[dict]:
    """Child libraries replace parent entries with the same Maven group:artifact[:classifier]."""
    result: List[dict] = []
    index: Dict[str, int] = {}
    for lib in parent_libs:
        key = library_override_key(lib)
        index[key] = len(result)
        result.append(lib)
    for lib in child_libs:
        key = library_override_key(lib)
        if key in index:
            result[index[key]] = lib
        else:
            index[key] = len(result)
            result.append(lib)
    return result


def find_client_jar(merged: dict, version_id: str, data_dir: Path, log: LogFn) -> Path:
    jar_id = merged.get("jar") or None
    chain = merged.get("_chain") or []
    ids_to_try: List[str] = []
    if jar_id:
        ids_to_try.append(jar_id)
    # For loader versions (Fabric/Forge) the base Minecraft jar is the real client;
    # prefer the base (last in chain, e.g. 26.1) over the loader's own id (fabric-loader-...)
    # to avoid launching with a wrong version like 1.21 when 26.1 was requested.
    if chain:
        base = chain[-1]
        if base not in ids_to_try:
            ids_to_try.append(base)
    if version_id not in ids_to_try:
        ids_to_try.append(version_id)
    for inherited in chain:
        if inherited not in ids_to_try:
            ids_to_try.append(inherited)

    roots = []
    for root in (data_dir, paths.get_minecraft_dir(), paths.get_data_dir()):
        resolved = (root / "versions").resolve()
        if resolved not in roots:
            roots.append(resolved)

    for vid in ids_to_try:
        for versions_root in roots:
            candidate = versions_root / vid / f"{vid}.jar"
            if candidate.is_file():
                log(f"Client JAR: {candidate}")
                return candidate

    raise MetadataError(
        f"Client JAR not found for {version_id} (tried ids: {', '.join(ids_to_try)}). "
        "Install the vanilla Minecraft version that OptiFine inherits from."
    )


def argument_item_allowed(item: Any, os_name: str, arch: str, features: Optional[dict] = None) -> bool:
    if isinstance(item, str):
        return True
    if not isinstance(item, dict):
        return False
    rules = item.get("rules") or []
    if not rules:
        return True
    allowed = False
    features = features or {}
    for rule in rules:
        if _rule_matches(rule, os_name, arch, features):
            allowed = rule.get("action") == "allow"
    return allowed


def _rule_matches(rule: dict, os_name: str, arch: str, features: dict) -> bool:
    os_info = rule.get("os") or {}
    if os_info.get("name") and os_info["name"] != os_name:
        return False
    if os_info.get("arch") and os_info["arch"] != arch:
        return False
    if os_info.get("version"):
        try:
            if not re.search(os_info["version"], platform_os_version()):
                return False
        except re.error:
            return False
    required_features = rule.get("features") or {}
    for name, expected in required_features.items():
        if features.get(name, False) != expected:
            return False
    return True


def platform_os_version() -> str:
    import platform as py_platform
    return py_platform.version()


def expand_argument_list(items: Sequence[Any], os_name: str, arch: str) -> List[str]:
    tokens: List[str] = []
    for item in items:
        if not argument_item_allowed(item, os_name, arch):
            continue
        if isinstance(item, str):
            tokens.append(item)
        elif isinstance(item, dict):
            value = item.get("value")
            if isinstance(value, str):
                tokens.append(value)
            elif isinstance(value, list):
                tokens.extend(str(v) for v in value)
    return tokens


def build_game_args(version_data: dict, replacements: dict, os_name: str, arch: str) -> List[str]:
    if version_data.get("minecraftArguments"):
        tokens = shlex.split(version_data["minecraftArguments"], posix=False)
    elif version_data.get("arguments", {}).get("game"):
        tokens = expand_argument_list(version_data["arguments"]["game"], os_name, arch)
    else:
        tokens = []
    return [_substitute(token, replacements) for token in tokens]


def build_jvm_args_from_metadata(version_data: dict, replacements: dict, os_name: str, arch: str) -> List[str]:
    items = (version_data.get("arguments") or {}).get("jvm") or []
    if not items:
        return []
    tokens = expand_argument_list(items, os_name, arch)
    result = []
    skip_next_cp = False
    for token in tokens:
        substituted = _substitute(token, replacements)
        if skip_next_cp:
            skip_next_cp = False
            continue
        if substituted in ("-cp", "-classpath"):
            skip_next_cp = True
            continue
        if substituted == replacements.get("${classpath}", "\0"):
            continue
        result.append(substituted)
    return result


def _substitute(token: str, replacements: dict) -> str:
    for placeholder, value in replacements.items():
        token = token.replace(placeholder, value)
    return token


def recommended_java_major(version_data: dict) -> Optional[int]:
    java = version_data.get("javaVersion") or {}
    major = java.get("majorVersion")
    try:
        if major is not None:
            return int(major)
    except (TypeError, ValueError):
        pass
    return infer_java_major_from_ids(version_data.get("_chain") or [version_data.get("id")])


def infer_java_major_from_ids(chain_ids: Optional[Sequence[str]]) -> Optional[int]:
    parsed_versions = []
    for version_id in chain_ids or []:
        parsed = _parse_minecraft_version(str(version_id) if version_id else "")
        if parsed:
            parsed_versions.append(parsed)
    if not parsed_versions:
        return None
    return java_major_for_minecraft(parsed_versions[-1])


def _parse_minecraft_version(text: str) -> Optional[tuple]:
    # Find all version-like patterns; pick the last plausible Minecraft version
    # (avoids picking loader version 0.15 for 'fabric-loader-0.15.2-26.1.2')
    matches = re.findall(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not matches:
        return None
    # Prefer the last match with major >=1 (skip 0.x loader versions)
    for m in reversed(matches):
        try:
            maj = int(m[0]); minor = int(m[1]); patch = int(m[2] or 0)
            if maj >= 1:
                return maj, minor, patch
        except:
            continue
    # fallback to first match
    m = matches[0]
    return int(m[0]), int(m[1]), int(m[2] or 0)


def java_major_for_minecraft(version: tuple) -> int:
    major, minor, patch = version
    # Minecraft 26.1+ requires Java 25 (mods like Fabric API 0.155+26.1.2 declare Java 25)
    if major >= 25:
        return 25
    if major != 1:
        return 17
    if minor >= 21 or (minor == 20 and patch >= 5):
        return 21
    if minor >= 18:
        return 17
    if minor == 17:
        return 16
    return 8


def extract_tweak_classes(version_data: dict) -> List[str]:
    found: List[str] = []

    def add(value: str) -> None:
        if value and value not in found:
            found.append(value)

    args = version_data.get("minecraftArguments") or ""
    if args:
        tokens = shlex.split(args, posix=False)
        for index, token in enumerate(tokens):
            if token == "--tweakClass" and index + 1 < len(tokens):
                add(tokens[index + 1])

    game = (version_data.get("arguments") or {}).get("game") or []
    for index, item in enumerate(game):
        if item == "--tweakClass" and index + 1 < len(game) and isinstance(game[index + 1], str):
            add(game[index + 1])
    return found


def rewrite_javaagent_args(args: List[str], search_roots: Sequence[Path]) -> List[str]:
    rewritten: List[str] = []
    for arg in args:
        if not arg.startswith("-javaagent:"):
            rewritten.append(arg)
            continue
        spec = arg[len("-javaagent:"):]
        path_text, sep, options = spec.partition("=")
        resolved = _resolve_existing_path(path_text, search_roots)
        rewritten.append("-javaagent:" + resolved + (sep + options if sep else ""))
    return rewritten


def validate_metadata(metadata: dict) -> list:
    errors = []
    if not metadata.get("id"):
        errors.append("Version metadata missing 'id'")
    if not metadata.get("mainClass"):
        errors.append("Version metadata missing 'mainClass' - will fallback to net.minecraft.client.main.Main")
    libs = metadata.get("libraries")
    if libs is not None and not isinstance(libs, list):
        errors.append("Version metadata 'libraries' is not a list")
    if metadata.get("arguments") is not None and not isinstance(metadata["arguments"], dict):
        errors.append("Version metadata 'arguments' is not an object")
    return errors


def _resolve_existing_path(path_text: str, search_roots: Sequence[Path]) -> str:
    direct = Path(path_text)
    if direct.is_file():
        return str(direct)
    for root in search_roots:
        candidate = root / path_text
        if candidate.is_file():
            return str(candidate)
    return path_text
