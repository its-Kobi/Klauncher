from __future__ import annotations
from pathlib import Path
from typing import List
from launcher.targets.base import LaunchTarget, TargetInfo

class ForgeTarget(LaunchTarget):
    kind = "forge"
    display_name = "Forge"
    priority = 22

    def matches(self, version_id: str, metadata: dict) -> bool:
        for lib in metadata.get("libraries") or []:
            n = str(lib.get("name") or "").lower()
            if n.startswith("net.minecraftforge:forge:") or n.startswith("net.minecraftforge:fmlloader:") or n.startswith("net.minecraftforge:bootstrap:") or n.startswith("net.minecraftforge:fnl:"):
                return True
            if n.startswith("net.minecraftforge:fmllibrary:"):
                return True
        mc = str(metadata.get("mainClass") or "").lower()
        if "net.minecraftforge" in mc or "cpw.mods" in mc or "bootstrap" in mc:
            return True
        # legacy tweakClass
        from launcher.version_metadata import extract_tweak_classes
        tweakers = extract_tweak_classes(metadata)
        for t in tweakers:
            if "forge" in t.lower() or "fml" in t.lower():
                return True
        return False

    def describe(self, version_id: str, metadata: dict) -> TargetInfo:
        # Distinguish legacy (tweakClass) vs modern (bootstrap)
        mc = metadata.get("mainClass") or ""
        is_modern = "bootstrap" in mc.lower() or any("fmlloader" in str(l.get("name","")).lower() for l in metadata.get("libraries") or [])
        ver = "legacy" if "tweakClass" in str(metadata.get("minecraftArguments")) else ("modern" if is_modern else None)
        return TargetInfo(kind=self.kind, display_name=self.display_name + (f" ({ver})" if ver else ""), icon="forge", main_class=mc, loader_version=ver)

    def extra_jvm_args(self, metadata: dict, version_id: str, data_dir: Path) -> List[str]:
        # Forge modern may need no extra, but ensure we don't miss anything
        return []

    def capabilities(self, metadata: dict) -> dict:
        return {"mods": True, "config": True, "worlds": True, "game_dir": True}
