from __future__ import annotations
from typing import List
from launcher.providers.base import VersionProvider

class CustomProvider(VersionProvider):
    id = "custom"
    display = "Custom"

    def fetch_minecraft_versions(self, force: bool=False) -> List[str]:
        from launcher.providers.vanilla import VanillaProvider
        return VanillaProvider().fetch_minecraft_versions(force=force)

    def fetch_loader_versions(self, minecraft_version: str | None = None, force: bool=False) -> List[str]:
        return []
