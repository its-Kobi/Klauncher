import os
import shutil
from pathlib import Path

def get_base_dir() -> Path:
    """Return the project root directory (parent of launcher package). Handles PyInstaller frozen exe via sys._MEIPASS."""
    import sys
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

def get_data_dir() -> Path:
    """Return the KLauncher data directory (AppData/KLauncher on Windows)."""
    if os.name == 'nt':
        base = Path(os.getenv('APPDATA', str(Path.home())))
    else:
        base = Path.home()
    data_dir = base / 'KLauncher'
    data_dir.mkdir(exist_ok=True)
    return data_dir

def get_minecraft_dir() -> Path:
    """Return the user's Minecraft directory (.minecraft)."""
    if os.name == 'nt':
        return Path(os.getenv('APPDATA', str(Path.home()))) / '.minecraft'
    else:
        return Path.home() / '.minecraft'

def ensure_directories() -> None:
    """Create all required subdirectories inside the KLauncher data directory."""
    data = get_data_dir()
    for sub in ["versions", "libraries", "assets", "profiles", "cache", "logs", "natives", "game", "instances", "java", "themes", "meta"]:
        (data / sub).mkdir(exist_ok=True, parents=True)

def _is_minecraft_dir(path: Path) -> bool:
    try:
        return path.resolve() == get_minecraft_dir().resolve()
    except OSError:
        return False

def reset_klauncher_data() -> Path:
    """Delete only KLauncher's own data directory and recreate the empty layout.

    Never deletes or writes into the user's .minecraft directory.
    """
    data_dir = get_data_dir()
    minecraft_dir = get_minecraft_dir()
    resolved_data = data_dir.resolve()
    resolved_mc = minecraft_dir.resolve()

    if resolved_data == resolved_mc:
        raise RuntimeError("Refusing to reset: KLauncher data directory is the Minecraft directory.")
    try:
        if resolved_data.is_relative_to(resolved_mc):
            raise RuntimeError("Refusing to reset: KLauncher data directory is inside .minecraft.")
    except AttributeError:
        if str(resolved_data).startswith(str(resolved_mc) + os.sep):
            raise RuntimeError("Refusing to reset: KLauncher data directory is inside .minecraft.")

    if data_dir.exists():
        shutil.rmtree(data_dir)
    ensure_directories()
    return get_data_dir()