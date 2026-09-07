from __future__ import annotations
from typing import List
from launcher.providers.base import VersionProvider, ProviderError

FABRIC_GAME_URL = "https://meta.fabricmc.net/v2/versions/game"
FABRIC_LOADER_URL = "https://meta.fabricmc.net/v2/versions/loader"

class FabricProvider(VersionProvider):
    id = "fabric"
    display = "Fabric"

    def fetch_minecraft_versions(self, force: bool=False) -> List[str]:
        data = self._fetch_json(FABRIC_GAME_URL, "fabric_game", force)
        # data is list of {"version":"1.20.1","stable":true}
        if isinstance(data, list):
            return [e["version"] for e in data if isinstance(e, dict) and e.get("version")]
        return []

    def fetch_loader_versions(self, minecraft_version: str | None = None, force: bool=False) -> List[str]:
        data = self._fetch_json(FABRIC_LOADER_URL, "fabric_loader", force)
        if isinstance(data, list):
            vers = []
            for e in data:
                if isinstance(e, dict) and e.get("version"):
                    vers.append(e["version"])
                elif isinstance(e, dict) and e.get("loader",{}).get("version"):
                    vers.append(e["loader"]["version"])
            # deduplicate preserve order, latest first is first in list
            seen=set(); out=[]
            for v in vers:
                if v not in seen:
                    seen.add(v); out.append(v)
            return out
        return []

    def get_profile_url(self, minecraft_version: str, loader_version: str) -> str:
        return f"https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/{loader_version}/profile/json"
