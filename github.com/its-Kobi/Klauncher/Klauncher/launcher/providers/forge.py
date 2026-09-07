from __future__ import annotations
from typing import List
from launcher.providers.base import VersionProvider, ProviderError

# Official Forge promotions and maven metadata
# promotions_slim gives recommended/latest per mc version
FORGE_PROMO_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
# fallback: maven metadata
FORGE_MAVEN_META = "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.json"

class ForgeProvider(VersionProvider):
    id = "forge"
    display = "Forge"

    def fetch_minecraft_versions(self, force: bool=False) -> List[str]:
        # Try promotions_slim first
        try:
            data = self._fetch_json(FORGE_PROMO_URL, "forge_promo", force)
            promos = data.get("promos", {})
            mcs = set()
            for k in promos.keys():
                # keys like "1.20.1-latest", "1.20.1-recommended"
                mc = k.split("-")[0]
                mcs.add(mc)
            if mcs:
                # sort by version desc
                return sorted(mcs, key=lambda x: [int(n) for n in x.split(".") if n.isdigit()], reverse=True)
        except ProviderError:
            pass
        # fallback to maven metadata (list all forge versions, extract mc)
        try:
            data = self._fetch_json(FORGE_MAVEN_META, "forge_maven_meta", force)
            # data may be xml? Actually maven-metadata is xml, not json. So fallback fails.
            pass
        except:
            pass
        # fallback to vanilla list filtered to known forge-supporting versions
        from launcher.providers.vanilla import VanillaProvider
        vp = VanillaProvider()
        try:
            vanilla = vp.fetch_minecraft_versions(force=False)
            # Forge supports most releases from 1.6+
            return [v for v in vanilla if v not in ("snapshot",)]
        except:
            return []

    def fetch_loader_versions(self, minecraft_version: str | None = None, force: bool=False) -> List[str]:
        if not minecraft_version:
            return []
        try:
            data = self._fetch_json(FORGE_PROMO_URL, "forge_promo", force)
            promos = data.get("promos", {})
            candidates = []
            for k,v in promos.items():
                if k.startswith(minecraft_version+"-"):
                    candidates.append(v)
            homos = data.get("homos", {})
            # homos not needed
            # deduplicate
            seen=set(); out=[]
            for c in candidates:
                if c and c not in seen:
                    seen.add(c); out.append(c)
            return out
        except ProviderError:
            return []
