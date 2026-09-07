from __future__ import annotations
from typing import List
from pathlib import Path
from launcher.targets.base import LaunchTarget, TargetInfo

FABRIC_LOADER_PREFIX = "net.fabricmc:fabric-loader:"
FABRIC_KNOT = "net.fabricmc.loader.impl.launch.knot.KnotClient"

class FabricTarget(LaunchTarget):
    kind = "fabric"
    display_name = "Fabric"
    priority = 20

    def matches(self, version_id: str, metadata: dict) -> bool:
        libs = metadata.get("libraries") or []
        for lib in libs:
            name = str(lib.get("name") or "")
            if name.lower().startswith("net.fabricmc:fabric-loader:"):
                return True
            if name.lower().startswith("net.fabricmc:intermediary:"):
                # intermediary alone is not fabric but strong signal if knot present
                pass
        mc = str(metadata.get("mainClass") or "")
        if "fabricmc" in mc.lower():
            return True
        # also check arguments for fabric specifics
        return False

    def describe(self, version_id: str, metadata: dict) -> TargetInfo:
        mc = metadata.get("mainClass") or FABRIC_KNOT
        # extract loader version
        loader_ver = None
        for lib in metadata.get("libraries") or []:
            n = str(lib.get("name") or "")
            if n.lower().startswith(FABRIC_LOADER_PREFIX.lower()):
                parts = n.split(":")
                if len(parts) >= 3:
                    loader_ver = parts[2]
                break
        return TargetInfo(kind=self.kind, display_name=self.display_name, icon="fabric", main_class=mc, loader_version=loader_ver)

    def validate(self, metadata: dict, classpath: List[str]) -> List[str]:
        errs = super().validate(metadata, classpath)
        mc = metadata.get("mainClass") or ""
        if "fabric" in self.kind and not mc:
            errs.append("Fabric metadata missing mainClass (expected KnotClient)")
        # ensure fabric-loader present
        has_loader = any(str(l.get("name") or "").lower().startswith(FABRIC_LOADER_PREFIX.lower()) for l in metadata.get("libraries") or [])
        if not has_loader:
            errs.append("Fabric loader library not found in version metadata")
        return errs

    def capabilities(self, metadata: dict) -> dict:
        return {"mods": True, "config": True, "worlds": True, "game_dir": True}
