from __future__ import annotations
from pathlib import Path
from typing import List
from launcher.targets.base import LaunchTarget, TargetInfo

class VanillaTarget(LaunchTarget):
    kind = "vanilla"
    display_name = "Vanilla"
    priority = 1000  # fallback lowest priority

    def matches(self, version_id: str, metadata: dict) -> bool:
        return True  # fallback

    def describe(self, version_id: str, metadata: dict) -> TargetInfo:
        mc = metadata.get("mainClass") or "net.minecraft.client.main.Main"
        return TargetInfo(kind=self.kind, display_name=self.display_name, icon="vanilla", main_class=mc)

    def capabilities(self, metadata: dict) -> dict:
        return {"mods": False, "config": False, "worlds": True, "game_dir": True}
