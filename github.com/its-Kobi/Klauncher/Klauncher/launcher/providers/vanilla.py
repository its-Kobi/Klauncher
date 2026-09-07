from __future__ import annotations
from typing import List
from launcher.providers.base import VersionProvider, ProviderError

class VanillaProvider(VersionProvider):
    id = "vanilla"
    display = "Vanilla"

    def fetch_minecraft_versions(self, force: bool=False) -> List[str]:
        data = self._fetch_json("https://launchermeta.mojang.com/mc/game/version_manifest.json", "mojang_manifest", force)
        versions = data.get("versions", [])
        # return release first, then snapshots if needed, but filter to release/snapshot
        ids = [v["id"] for v in versions if v.get("type") in ("release","snapshot")]
        return ids
