from __future__ import annotations
from pathlib import Path
from typing import List
from launcher.targets.base import LaunchTarget, TargetInfo

class CustomTarget(LaunchTarget):
    kind = "custom"
    display_name = "Custom"
    priority = 500

    def matches(self, version_id: str, metadata: dict) -> bool:
        mc = str(metadata.get("mainClass") or "")
        vanilla_mains = {"net.minecraft.client.main.Main", "net.minecraft.launchwrapper.Launch"}
        fabric_quilt_forge_mains = ["fabricmc", "quiltmc", "forge", "fml", "cpw.mods", "bootstrap"]
        if mc and mc not in vanilla_mains and not any(x in mc.lower() for x in fabric_quilt_forge_mains):
            has_tweaker = bool(metadata.get("minecraftArguments") and "--tweakClass" in metadata.get("minecraftArguments", ""))
            if has_tweaker:
                return True
            if metadata.get("inheritsFrom") and mc != "net.minecraft.client.main.Main":
                return True
            # Any custom mainClass with libraries is custom
            if metadata.get("libraries"):
                return True
        return False

    def describe(self, version_id: str, metadata: dict) -> TargetInfo:
        return TargetInfo(kind=self.kind, display_name=self.display_name, icon="custom", main_class=metadata.get("mainClass"))

    def capabilities(self, metadata: dict) -> dict:
        # Custom versions like Badlion do support mods/config in their gameDir
        return {"mods": True, "config": True, "worlds": True, "game_dir": True}

    def extra_jvm_args(self, metadata: dict, version_id: str, data_dir: Path) -> List[str]:
        """Custom javaagent handling - scoped strictly to Custom target.
        Only injects if:
        - version is Custom (this target matched) AND
        - the version explicitly requires an agent (declared in metadata OR
          known custom Main like offlineblc.starter.Start that checks for
          offlineblc.agent.AgentMain) AND
        - a valid Agent.jar with Premain-Class exists locally.
        This never leaks to Fabric/Forge/Vanilla/Quilt/OptiFine."""
        # Check if metadata explicitly declares -javaagent
        jvm_items = (metadata.get("arguments") or {}).get("jvm") or []
        has_explicit = False
        for item in jvm_items:
            if isinstance(item, str) and "-javaagent" in item:
                has_explicit = True
                break
            if isinstance(item, dict):
                v = item.get("value")
                if isinstance(v, str) and "-javaagent" in v:
                    has_explicit = True
                    break
                if isinstance(v, list) and any("-javaagent" in str(x) for x in v):
                    has_explicit = True
                    break
        main = str(metadata.get("mainClass") or "")
        # Badlion Offline explicitly checks for offlineblc.agent.AgentMain
        requires_agent = has_explicit or main == "offlineblc.starter.Start"
        if not requires_agent:
            return []
        # Search only for this Custom version's agent - prefer version folder, then adjacent
        from launcher import paths
        candidates: list[Path] = []
        for root in (data_dir, paths.get_minecraft_dir(), paths.get_data_dir()):
            candidates.append(root / "versions" / version_id / "Agent.jar")
            # also check per-version lowercase variant
            candidates.append(root / "versions" / version_id / "agent.jar")
        # Legacy location used by Badlion installer
        candidates.append(paths.get_minecraft_dir() / "Agent.jar")
        # Also check version jar parent via _json_path
        json_path = metadata.get("_json_path")
        if json_path:
            try:
                candidates.append(Path(json_path).parent / "Agent.jar")
            except Exception:
                pass
        for cand in candidates:
            if cand.is_file():
                try:
                    import zipfile
                    with zipfile.ZipFile(cand) as zf:
                        try:
                            mf = zf.read("META-INF/MANIFEST.MF").decode(errors="ignore")
                            if "Premain-Class" not in mf:
                                continue
                            # Validate java compatibility: Badlion agent built for Java 8
                            # If agent's class version > java major, it will fail with instrument assert
                            # We don't block, just allow pipeline's Java selection to choose Java 8 via recommended_java_major
                        except KeyError:
                            continue
                        return [f"-javaagent:{cand}"]
                except Exception:
                    continue
        # Explicit requires agent but not found locally
        if requires_agent:
            # Log will be handled by caller; return empty so validation can warn
            pass
        return []
