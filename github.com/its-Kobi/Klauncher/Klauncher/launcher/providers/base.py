from __future__ import annotations
import json, time, urllib.request, urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from launcher import paths

class ProviderError(Exception): pass

@dataclass
class LoaderType:
    id: str
    display: str
    description: str

@dataclass
class RemoteVersion:
    id: str
    loader: str
    minecraft_version: Optional[str] = None
    loader_version: Optional[str] = None
    stable: bool = True
    url: Optional[str] = None
    display: Optional[str] = None

class VersionProvider(ABC):
    id: str = "base"
    display: str = "Base"
    cache_ttl: int = 3600

    def cache_path(self, name: str) -> Path:
        d = paths.get_data_dir() / "cache" / "providers" / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{name}.json"

    def _is_cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            age = time.time() - path.stat().st_mtime
            return age < self.cache_ttl
        except:
            return False

    def _fetch_json(self, url: str, cache_name: Optional[str]=None, force: bool=False) -> dict | list:
        cache = self.cache_path(cache_name) if cache_name else None
        if cache and not force and self._is_cache_valid(cache):
            try:
                with open(cache, encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"KLauncher/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if cache:
                try:
                    with open(cache,"w",encoding="utf-8") as f:
                        json.dump(data,f)
                except:
                    pass
            return data
        except urllib.error.URLError as e:
            # try cache fallback even if stale
            if cache and cache.exists():
                try:
                    with open(cache, encoding="utf-8") as f:
                        return json.load(f)
                except:
                    pass
            raise ProviderError(f"Network error fetching {url}: {e}") from e

    @abstractmethod
    def fetch_minecraft_versions(self, force: bool=False) -> List[str]:
        ...

    def fetch_loader_versions(self, minecraft_version: Optional[str]=None, force: bool=False) -> List[str]:
        return []

    def supports_minecraft_filter(self) -> bool:
        return True
