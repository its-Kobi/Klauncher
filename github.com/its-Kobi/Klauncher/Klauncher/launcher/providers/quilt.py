from __future__ import annotations
from typing import List
from launcher.providers.base import VersionProvider

QUILT_GAME_URL = "https://meta.quiltmc.org/v3/versions/game"
QUILT_LOADER_URL = "https://meta.quiltmc.org/v3/versions/loader"

class QuiltProvider(VersionProvider):
    id = "quilt"
    display = "Quilt"

    def fetch_minecraft_versions(self, force: bool=False) -> List[str]:
        try:
            data = self._fetch_json(QUILT_GAME_URL, "quilt_game", force)
            if isinstance(data, list):
                return [e["version"] for e in data if isinstance(e, dict) and e.get("version")]
        except Exception:
            pass
        # fallback to vanilla
        from launcher.providers.vanilla import VanillaProvider
        return VanillaProvider().fetch_minecraft_versions(force=False)

    def fetch_loader_versions(self, minecraft_version: str | None = None, force: bool=False) -> List[str]:
        try:
            data = self._fetch_json(QUILT_LOADER_URL, "quilt_loader", force)
            if isinstance(data, list):
                vers=[]
                for e in data:
                    if isinstance(e, dict) and e.get("version"):
                        vers.append(e["version"])
                seen=set(); out=[]
                for v in vers:
                    if v not in seen:
                        seen.add(v); out.append(v)
                return out
        except Exception:
            pass
        return []
