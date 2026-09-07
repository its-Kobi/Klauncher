from __future__ import annotations
from pathlib import Path
from typing import List
from launcher.targets.base import LaunchTarget, TargetInfo
from launcher import optifine as opt_mod

class OptiFineTarget(LaunchTarget):
    kind = "optifine"
    display_name = "OptiFine"
    priority = 10

    def matches(self, version_id: str, metadata: dict) -> bool:
        # Let Custom handle versions with custom Main like Badlion offline
        # which also happen to bundle OptiFine but require a javaagent.
        mc = str(metadata.get("mainClass") or "")
        if mc == "offlineblc.starter.Start":
            return False
        ctx = opt_mod.detect_optifine(version_id, metadata)
        return ctx.is_optifine

    def describe(self, version_id: str, metadata: dict) -> TargetInfo:
        ctx = opt_mod.detect_optifine(version_id, metadata)
        tweakers = []
        if ctx.tweaker_class:
            tweakers.append(ctx.tweaker_class)
        elif ctx.uses_launchwrapper:
            tweakers.append(opt_mod.OPTIFINE_TWEAKER)
        return TargetInfo(
            kind=self.kind,
            display_name=self.display_name,
            icon="optifine",
            main_class=metadata.get("mainClass"),
            tweaker_classes=tweakers,
            uses_launchwrapper=ctx.uses_launchwrapper,
            loader_version=ctx.base_minecraft,
        )

    def post_classpath(self, metadata: dict, version_id: str, data_dir: Path, classpath: List[str], log) -> None:
        ctx = opt_mod.detect_optifine(version_id, metadata)
        if not ctx.is_optifine:
            return
        # delegate to existing working implementation
        opt_mod.apply_optifine(ctx, metadata, data_dir, classpath, log)

    def validate(self, metadata: dict, classpath: List[str]) -> List[str]:
        # Use existing validation but via temporary ctx
        vid = metadata.get("id") or ""
        ctx = opt_mod.detect_optifine(vid, metadata)
        if not ctx.is_optifine:
            return []
        return opt_mod.validate_optifine_classpath(ctx, classpath)

    def capabilities(self, metadata: dict) -> dict:
        return {"mods": False, "config": False, "worlds": True, "game_dir": True}
