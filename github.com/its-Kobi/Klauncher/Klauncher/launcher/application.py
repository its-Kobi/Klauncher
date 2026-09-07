from __future__ import annotations
from PySide6.QtCore import QObject, Signal
from launcher import paths
from launcher.config import Config
from launcher.profiles import ProfileManager
from launcher.version_manager import VersionManager
from launcher.minecraft_launcher import MinecraftLauncher
from launcher.instances.manager import InstanceManager
from launcher.java.manager import JavaManager
try:
    from launcher.auth.manager import MicrosoftAuthManager
    HAS_MS = True
except:
    HAS_MS=False
    MicrosoftAuthManager=None

class Application(QObject):
    _instance=None
    profiles_updated = Signal()
    instances_changed = Signal(list)

    def __new__(cls, *a, **kw):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, '_inited', False):
            return
        super().__init__()
        self._inited=True
        paths.ensure_directories()
        (paths.get_data_dir() / "instances").mkdir(exist_ok=True)
        (paths.get_data_dir() / "java").mkdir(exist_ok=True)
        self.config = Config(paths.get_data_dir() / "config.json")
        self.profile_manager = ProfileManager(paths.get_data_dir() / "profiles.json")
        self.microsoft_manager = MicrosoftAuthManager() if HAS_MS and MicrosoftAuthManager else None
        self.version_manager = VersionManager()
        self.minecraft_launcher = MinecraftLauncher()
        self.instance_manager = InstanceManager()
        self.java_manager = JavaManager()
        # bridge
        self.instance_manager.instances_changed.connect(self.instances_changed.emit)

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls()
        return cls._instance

def get_app():
    return Application.get()
