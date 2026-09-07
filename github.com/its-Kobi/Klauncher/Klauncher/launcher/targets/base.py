"""Abstract launch target - the core extensibility point."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

@dataclass
class TargetInfo:
    kind: str
    display_name: str
    icon: str  # Qt style key
    main_class: Optional[str] = None
    tweaker_classes: List[str] = field(default_factory=list)
    uses_launchwrapper: bool = False
    loader_version: Optional[str] = None

class LaunchTarget(ABC):
    kind: str = "generic"
    display_name: str = "Generic"
    priority: int = 100

    @abstractmethod
    def matches(self, version_id: str, metadata: dict) -> bool:
        """Metadata-driven detection - no version-name substring checks unless fallback."""
        ...

    def describe(self, version_id: str, metadata: dict) -> TargetInfo:
        return TargetInfo(kind=self.kind, display_name=self.display_name)

    def pre_resolve(self, metadata: dict, version_id: str, data_dir: Path, log) -> None:
        """Hook before library resolution (e.g. inject missing url)."""
        pass

    def post_classpath(self, metadata: dict, version_id: str, data_dir: Path, classpath: List[str], log) -> None:
        """Hook after library resolution to adjust classpath."""
        pass

    def tweak_game_args(self, game_args: List[str], metadata: dict) -> List[str]:
        return game_args

    def extra_jvm_args(self, metadata: dict, version_id: str, data_dir: Path) -> List[str]:
        return []

    def validate(self, metadata: dict, classpath: List[str]) -> List[str]:
        errors: List[str] = []
        if not metadata.get("mainClass"):
            errors.append("Version metadata missing mainClass")
        if not metadata.get("libraries"):
            # allow minimal custom versions but warn
            pass
        return errors

    def diagnostics(self, metadata: dict, classpath: List[str]) -> List[str]:
        return []

    def capabilities(self, metadata: dict) -> dict:
        """Filesystem/UI capabilities for this launch target. Used for context menus."""
        return {
            "mods": False,
            "config": False,
            "worlds": True,  # all have worlds/saves
            "game_dir": True,
        }
