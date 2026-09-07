from __future__ import annotations
from typing import Optional
from launcher.version_metadata import java_major_for_minecraft, _parse_minecraft_version, recommended_java_major

def required_java_for_version(version_id: str, metadata: Optional[dict] = None) -> int:
    if metadata and metadata.get("javaVersion", {}).get("majorVersion"):
        try:
            return int(metadata["javaVersion"]["majorVersion"])
        except:
            pass
    if metadata:
        rec = recommended_java_major(metadata)
        if rec:
            return rec
    parsed = _parse_minecraft_version(version_id)
    if parsed:
        return java_major_for_minecraft(parsed)
    return 17

def required_java_for_instance(instance) -> int:
    # instance has version_id + metadata
    try:
        return required_java_for_version(instance.version_id, getattr(instance, 'metadata', None))
    except:
        return 17

def java_compatible(actual_major: Optional[int], required: int) -> bool:
    if actual_major is None:
        return False
    if required <= 8:
        return actual_major == 8
    return actual_major >= required
