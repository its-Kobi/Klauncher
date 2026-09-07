from __future__ import annotations
from pathlib import Path
from typing import List
from launcher.targets.base import LaunchTarget, TargetInfo

class QuiltTarget(LaunchTarget):
    kind = "quilt"
    display_name = "Quilt"
    priority = 21

    def matches(self, version_id: str, metadata: dict) -> bool:
        for lib in metadata.get("libraries") or []:
            n = str(lib.get("name") or "").lower()
            if n.startswith("org.quiltmc:quilt-loader:"):
                return True
        mc = str(metadata.get("mainClass") or "").lower()
        if "quiltmc" in mc:
            return True
        return False

    def describe(self, version_id: str, metadata: dict) -> TargetInfo:
        loader_ver = None
        for lib in metadata.get("libraries") or []:
            n = str(lib.get("name") or "")
            if n.lower().startswith("org.quiltmc:quilt-loader:"):
                loader_ver = n.split(":")[2] if ":" in n else None
                break
        return TargetInfo(kind=self.kind, display_name=self.display_name, icon="quilt", main_class=metadata.get("mainClass"), loader_version=loader_ver)

    def validate(self, metadata: dict, classpath: List[str]) -> List[str]:
        errs = super().validate(metadata, classpath)
        has_loader = any(str(l.get("name") or "").lower().startswith("org.quiltmc:quilt-loader:") for l in metadata.get("libraries") or [])
        if not has_loader:
            errs.append("Quilt loader library not found in version metadata")
        mc = str(metadata.get("mainClass") or "")
        # Quilt uses KnotClient like Fabric but with quilt package
        if mc and "quiltmc" not in mc.lower():
            errs.append(f"Quilt mainClass does not look like quilt loader: {mc}")
        return errs

    def capabilities(self, metadata: dict) -> dict:
        return {"mods": True, "config": True, "worlds": True, "game_dir": True}
