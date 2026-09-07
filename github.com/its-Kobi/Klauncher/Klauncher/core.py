from pathlib import Path
from typing import List, Optional, Dict

from PySide6.QtCore import QObject, Signal, QThread, QTimer

from launcher import paths
from launcher.config import Config
from launcher.profiles import ProfileManager, Profile
from launcher.version_manager import VersionManager
from launcher.minecraft_launcher import MinecraftLauncher
from launcher.java_detector import detect_java, get_java_version
try:
    from launcher.auth.manager import MicrosoftAuthManager
    HAS_MS_AUTH = True
except Exception:
    HAS_MS_AUTH = False
    MicrosoftAuthManager = None  # type: ignore


class JavaDetectWorker(QThread):
    finished_detect = Signal(str, str)  # path, version
    def run(self):
        path = detect_java()
        ver = get_java_version(path) if path else None
        self.finished_detect.emit(path or "", ver or "")


class LauncherCore(QObject):
    # Signals
    profiles_updated = Signal()
    microsoft_login_succeeded = Signal(object)
    microsoft_login_failed = Signal(str)
    microsoft_code_ready = Signal(str, str, int)
    microsoft_accounts_changed = Signal()
    versions_updated = Signal(list)
    installed_versions_changed = Signal(list)
    version_error = Signal(str)
    version_loading_changed = Signal(bool)
    install_started = Signal(str)
    install_progress = Signal(str, int)
    install_log = Signal(str, str)
    install_error = Signal(str, str)
    install_finished = Signal(str)
    log_message = Signal(str)
    process_started = Signal()
    process_finished = Signal(int)
    launch_failed = Signal(str)
    launch_cancelled = Signal()
    java_detected = Signal(str, str)
    external_versions_changed = Signal(list)

    def __init__(self):
        super().__init__()
        paths.ensure_directories()

        self.config = Config(paths.get_data_dir() / "config.json")
        self.profile_manager = ProfileManager(paths.get_data_dir() / "profiles.json")
        self.microsoft_manager = MicrosoftAuthManager() if HAS_MS_AUTH and MicrosoftAuthManager else None

        self.version_manager = VersionManager()
        self.version_manager.versions_loaded.connect(self._on_versions_loaded)
        self.version_manager.error.connect(self._on_version_error)
        self.version_manager.loading_changed.connect(self._on_version_loading_changed)
        self.version_manager.installed_versions_changed.connect(self._on_installed_versions_changed)
        self.version_manager.install_started.connect(self.install_started)
        self.version_manager.install_progress.connect(self.install_progress)
        self.version_manager.install_log.connect(self.install_log)
        self.version_manager.install_error.connect(self.install_error)
        self.version_manager.install_finished.connect(self.install_finished)

        self.minecraft_launcher = MinecraftLauncher()
        self.minecraft_launcher.log_message.connect(self.log_message)
        self.minecraft_launcher.process_started.connect(self._on_process_started)
        self.minecraft_launcher.process_finished.connect(self._on_process_finished)
        self.minecraft_launcher.launch_failed.connect(self.launch_failed)
        self.minecraft_launcher.launch_cancelled.connect(self.launch_cancelled)

        self.detected_java_path: Optional[str] = None
        self.java_version: Optional[str] = None
        self._java_worker: Optional[JavaDetectWorker] = None
        self._installed_cache: Optional[list] = None
        self._installed_cache_dirty = True

        # Async java detection - don't block GUI
        self._start_java_detection()

        self.profiles_updated.emit()
        # Defer expensive scan slightly to let UI show
        QTimer.singleShot(100, self.scan_installed_versions)

    def _start_java_detection(self):
        # Try quick cache: if config has java_path use it, else async
        cfg_path = self.config.get("java_path")
        if cfg_path and Path(cfg_path).exists():
            self.detected_java_path = cfg_path
            # still async get version
            self._java_worker = JavaDetectWorker()
            self._java_worker.finished_detect.connect(self._on_java_detected)
            self._java_worker.start()
        else:
            self._java_worker = JavaDetectWorker()
            self._java_worker.finished_detect.connect(self._on_java_detected)
            self._java_worker.start()

    def _on_java_detected(self, path: str, ver: str):
        self.detected_java_path = path or None
        self.java_version = ver or None
        self.java_detected.emit(path, ver)
        self._java_worker = None

    def refresh_java_detection(self):
        if self._java_worker and self._java_worker.isRunning():
            return
        self._java_worker = JavaDetectWorker()
        self._java_worker.finished_detect.connect(self._on_java_detected)
        self._java_worker.start()

    def scan_installed_versions(self):
        # Use cache if not dirty
        if not self._installed_cache_dirty and self._installed_cache is not None:
            self._on_installed_versions_changed(self._installed_cache)
            return
        all_versions = self.version_manager.get_all_installed_versions()
        self._installed_cache = all_versions
        self._installed_cache_dirty = False
        self._on_installed_versions_changed(all_versions)

    def mark_installed_dirty(self):
        self._installed_cache_dirty = True

    def _on_process_started(self):
        self.process_started.emit()

    def _on_process_finished(self, exit_code):
        self.process_finished.emit(exit_code)

    def _on_versions_loaded(self, versions: list):
        self.versions_updated.emit(versions)

    def _on_version_error(self, error_msg: str):
        self.version_error.emit(error_msg)

    def _on_version_loading_changed(self, loading: bool):
        self.version_loading_changed.emit(loading)

    def _on_installed_versions_changed(self, installed: list):
        self._installed_cache = installed
        self._installed_cache_dirty = False
        self.installed_versions_changed.emit(installed)

    # Public methods
    def fetch_versions(self, force_refresh: bool = False):
        self.version_manager.fetch_versions(force_refresh)

    def get_available_versions(self) -> list:
        return self.version_manager.get_available_versions()

    def get_installed_versions(self) -> list:
        if not self._installed_cache_dirty and self._installed_cache is not None:
            return list(self._installed_cache)
        return self.version_manager.get_all_installed_versions()

    def install_version(self, version_id: str):
        self.mark_installed_dirty()
        self.version_manager.install_version(version_id)

    def create_profile(self, username: str) -> Optional[Profile]:
        try:
            profile = self.profile_manager.create_profile(username)
            self.profiles_updated.emit()
            return profile
        except ValueError as e:
            self.log_message.emit(str(e))
            return None

    def delete_profile(self, profile_uuid: str) -> None:
        self.profile_manager.delete_profile(profile_uuid)
        self.profiles_updated.emit()

    def list_profiles(self) -> List[Profile]:
        return self.profile_manager.list_profiles()

    def list_microsoft_accounts(self) -> List:
        if self.microsoft_manager:
            return self.microsoft_manager.list_accounts()
        return []

    def list_all_accounts(self) -> List[Dict]:
        # Combined for UI: returns dicts with account_type
        result = []
        for p in self.profile_manager.list_profiles():
            result.append({"uuid": p.uuid, "username": p.username, "type": "offline", "profile": p})
        if self.microsoft_manager:
            for acc in self.microsoft_manager.list_accounts():
                result.append({"uuid": acc.uuid, "username": acc.username, "type": "microsoft", "profile": acc})
        return result

    def get_profile(self, profile_uuid: str) -> Optional[Profile]:
        # Check offline first
        p = self.profile_manager.get_profile(profile_uuid)
        if p:
            return p
        # Check microsoft
        if self.microsoft_manager:
            acc = self.microsoft_manager.get_account(profile_uuid)
            if acc:
                # Return a Profile-like object for compatibility
                return Profile(username=acc.username, uuid=acc.uuid, account_type="microsoft")
        return None

    def is_microsoft_account(self, uuid: str) -> bool:
        if self.microsoft_manager:
            return self.microsoft_manager.get_account(uuid) is not None
        return False

    def launch_minecraft(self, profile_uuid: str, version_id: str,
                         version_source: str = "klauncher") -> None:
        # Resolve profile: offline or microsoft; do not assume offline
        is_ms = self.is_microsoft_account(profile_uuid)
        if is_ms:
            acc = self.microsoft_manager.get_account(profile_uuid) if self.microsoft_manager else None
            if not acc:
                self.log_message.emit("Microsoft account not found")
                return
            # Refresh token if needed and get launch credentials
            token_info = self.microsoft_manager.get_access_token_for_launch(profile_uuid) if self.microsoft_manager else None
            if not token_info:
                self.log_message.emit("Microsoft account token expired or invalid. Please log in again.")
                self.launch_failed.emit("Microsoft account token expired. Please log in again.")
                return
            username = token_info["username"]
            uuid = token_info["uuid"]
            access_token = token_info["access_token"]
            user_type = "msa"
            xuid = token_info.get("xuid")
        else:
            profile = self.get_profile(profile_uuid)
            if not profile:
                self.log_message.emit("No profile selected")
                return
            username = profile.username
            uuid = profile.uuid
            access_token = "0"
            user_type = "legacy"
            xuid = None
        java_path = self.config.get("java_path") or self.detected_java_path
        if not java_path:
            message = "Java not found. Install a compatible JDK or configure the Java path in Settings."
            self.log_message.emit(message)
            self.launch_failed.emit(message)
            return
        # Instance-aware game directory:
        configured = self.config.get("game_directory")
        if version_source == "external":
            game_dir = paths.get_minecraft_dir()
            data_dir_override = paths.get_minecraft_dir()
        else:
            game_dir = Path(configured) if configured else paths.get_data_dir() / "game"
            data_dir_override = None
        game_dir.mkdir(parents=True, exist_ok=True)
        ram = self.config.get("ram_gb", 2)
        custom_args = self.config.get("custom_jvm_args", "")

        self.minecraft_launcher.launch(
            java_path, version_id, username,
            uuid, game_dir, ram, custom_args,
            data_dir_override=data_dir_override,
            access_token=access_token,
            user_type=user_type,
            xuid=xuid,
        )

    def cancel_launch(self) -> bool:
        return self.minecraft_launcher.cancel_launch()

    # --- Microsoft authentication (isolated, never handles passwords) ---
    def start_microsoft_login(self, on_code_callback=None):
        if not self.microsoft_manager:
            self.microsoft_login_failed.emit("Microsoft authentication not available")
            return
        from launcher.auth.microsoft import MicrosoftAuthError
        from launcher.auth.minecraft import MinecraftOwnershipError
        from PySide6.QtCore import QThread, Signal

        class LoginWorker(QThread):
            code_ready = Signal(str, str, int)
            succeeded = Signal(object)
            failed = Signal(str)
            def __init__(self, manager, on_code):
                super().__init__()
                self.manager = manager
                self.on_code = on_code
                self._cancel = False
            def cancel(self):
                self._cancel = True
            def run(self):
                try:
                    def on_code(user_code, uri, expires):
                        self.code_ready.emit(user_code, uri, expires)
                    def cancel_check():
                        return self._cancel
                    # Wrap on_code to emit via signal
                    acc = self.manager.login_device_flow(
                        on_code=lambda uc, uri, exp: self.code_ready.emit(uc, uri, exp),
                        cancel_check=lambda: self._cancel
                    )
                    self.succeeded.emit(acc)
                except Exception as e:
                    # Never expose tokens, strip sensitive data
                    msg = str(e)
                    # Map to user-friendly without tokens
                    if "Minecraft account required" in msg or "does not own" in msg:
                        self.failed.emit("Minecraft account required\nThis Microsoft account does not own Minecraft Java Edition. Please purchase Minecraft Java Edition or sign in with a Microsoft account that owns the game.")
                    elif "cancel" in msg.lower():
                        self.failed.emit("Authentication cancelled")
                    elif "network" in msg.lower():
                        self.failed.emit("Network error during authentication. Please check your connection.")
                    elif "Xbox" in msg:
                        self.failed.emit(f"Xbox authentication failed: {msg}")
                    elif "XSTS" in msg:
                        self.failed.emit(f"Xbox authorization failed: {msg}")
                    elif "Minecraft" in msg:
                        self.failed.emit(f"Minecraft authentication failed: {msg}")
                    else:
                        self.failed.emit(f"Microsoft authentication failed: {msg}")

        self._ms_worker = LoginWorker(self.microsoft_manager, on_code_callback)
        self._ms_worker.code_ready.connect(self._on_ms_code_ready)
        self._ms_worker.succeeded.connect(self._on_ms_success)
        self._ms_worker.failed.connect(self._on_ms_failed)
        self._ms_worker.start()
        # Keep reference
        self.log_message.emit("Started Microsoft device code flow — please authenticate in browser")

    def _on_ms_code_ready(self, code, uri, expires):
        # Emit for UI to open browser; never log tokens, only code/uri (user_code is not secret)
        self.microsoft_code_ready.emit(code, uri, expires)
        self.log_message.emit(f"Microsoft authentication: please sign in at {uri}")

    def _on_ms_success(self, acc):
        self.log_message.emit(f"Microsoft login succeeded: {acc.username}")
        self.microsoft_login_succeeded.emit(acc)
        self.microsoft_accounts_changed.emit()
        self.profiles_updated.emit()
        self._ms_worker = None

    def _on_ms_failed(self, msg):
        # Ensure we never log tokens
        self.log_message.emit(f"Microsoft login failed: {msg}")
        self.microsoft_login_failed.emit(msg)
        self._ms_worker = None

    def cancel_microsoft_login(self):
        if hasattr(self, "_ms_worker") and self._ms_worker and self._ms_worker.isRunning():
            try:
                self._ms_worker.cancel()
            except:
                pass

    def logout_microsoft(self, uuid: str):
        if self.microsoft_manager:
            self.microsoft_manager.logout(uuid)
            self.microsoft_accounts_changed.emit()
            self.profiles_updated.emit()
            # If this was selected, clear selection
            if self.config.get("selected_profile") == uuid:
                self.config.set("selected_profile", None)
            self.log_message.emit("Microsoft account logged out")

    def save_settings(self, settings: dict) -> None:
        for key, value in settings.items():
            self.config.set(key, value)
        if "java_path" in settings:
            new_path = settings["java_path"]
            if new_path:
                self.java_version = get_java_version(new_path)
                self.detected_java_path = new_path
            else:
                self.refresh_java_detection()

    def reset_klauncher_data(self) -> bool:
        try:
            if self.minecraft_launcher.is_running():
                self.log_message.emit("Cannot reset KLauncher data while Minecraft is running.")
                return False
            paths.reset_klauncher_data()
            self.config = Config(paths.get_data_dir() / "config.json")
            self.profile_manager = ProfileManager(paths.get_data_dir() / "profiles.json")
            self.version_manager.manifest_path = paths.get_data_dir() / "cache" / "version_manifest.json"
            self._installed_cache_dirty = True
            self.fetch_versions(force_refresh=True)
            self.scan_installed_versions()
            self.profiles_updated.emit()
            self.log_message.emit(
                "KLauncher data reset successfully. Minecraft directory was not modified."
            )
            return True
        except Exception as e:
            self.log_message.emit(f"KLauncher data reset failed: {str(e)}")
            return False

    def rebuild_klauncher_data(self) -> bool:
        return self.reset_klauncher_data()
