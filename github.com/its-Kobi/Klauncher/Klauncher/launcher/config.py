import json
from pathlib import Path
from typing import Any, Dict, Optional

from launcher import paths

DEFAULT_CONFIG: Dict[str, Any] = {
    "selected_profile": None,
    "selected_version": None,
    "java_path": "",
    "game_directory": str(paths.get_data_dir() / "game"),
    "ram_gb": 2,
    "custom_jvm_args": "",
    "minimize_to_tray": True,
    "show_logs_on_main": False,
}

class Config:
    """Persistent JSON configuration manager."""

    def __init__(self, config_file: Path):
        self.config_file = config_file
        self.data: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.load()

    def load(self) -> None:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.data.update(loaded)
            except Exception:
                pass

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()