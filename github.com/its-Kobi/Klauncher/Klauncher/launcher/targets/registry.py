from __future__ import annotations
from typing import List
from launcher.targets.base import LaunchTarget
from launcher.targets.optifine import OptiFineTarget
from launcher.targets.fabric import FabricTarget
from launcher.targets.quilt import QuiltTarget
from launcher.targets.forge import ForgeTarget
from launcher.targets.custom import CustomTarget
from launcher.targets.vanilla import VanillaTarget

_REGISTRY: List[LaunchTarget] = [
    OptiFineTarget(),
    FabricTarget(),
    QuiltTarget(),
    ForgeTarget(),
    CustomTarget(),
    VanillaTarget(),
]

# sort by priority ascending (lower = more specific)
_REGISTRY.sort(key=lambda t: t.priority)

def detect_target(version_id: str, metadata: dict) -> LaunchTarget:
    for target in _REGISTRY:
        try:
            if target.matches(version_id, metadata):
                return target
        except Exception:
            continue
    return VanillaTarget()

def get_target(kind: str) -> LaunchTarget:
    for t in _REGISTRY:
        if t.kind == kind:
            return t
    return VanillaTarget()

def list_targets():
    return list(_REGISTRY)
