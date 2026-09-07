from __future__ import annotations
from typing import List
from launcher.providers.base import VersionProvider, ProviderError
import urllib.request, json

# No stable official JSON API; use community endpoint with fallback
OPTIFINE_API = "https://bmclapi2.bangbang93.com/optifine/versionList"

class OptiFineProvider(VersionProvider):
    id = "optifine"
    display = "OptiFine"

    def fetch_minecraft_versions(self, force: bool=False) -> List[str]:
        try:
            data = self._fetch_json(OPTIFINE_API, "optifine_versions", force)
            # bmclapi returns list of {"mcversion":...}
            if isinstance(data, list):
                mcs = []
                for e in data:
                    mc = e.get("mcversion") or e.get("minecraftVersion")
                    if mc and mc not in mcs:
                        mcs.append(mc)
                if mcs:
                    return sorted(mcs, key=lambda x: [int(n) for n in x.split(".") if n.isdigit()], reverse=True)
        except Exception:
            pass
        # fallback: use vanilla releases that commonly have OptiFine
        from launcher.providers.vanilla import VanillaProvider
        try:
            v = VanillaProvider().fetch_minecraft_versions(force=False)
            # filter to likely optifine-supported (not super new snapshots)
            return [x for x in v if not x.startswith("24w")][:20]
        except:
            return []

    def fetch_loader_versions(self, minecraft_version: str | None = None, force: bool=False) -> List[str]:
        if not minecraft_version:
            return []
        try:
            data = self._fetch_json(OPTIFINE_API, "optifine_versions", force)
            out=[]
            for e in data:
                if (e.get("mcversion") or e.get("minecraftVersion"))==minecraft_version:
                    # name like OptiFine_HD_U_G5
                    name = e.get("name") or e.get("version") or e.get("patch")
                    if name:
                        out.append(name)
                    elif e.get("type"):
                        out.append(e.get("type"))
            if out:
                return out
        except Exception:
            pass
        return []
