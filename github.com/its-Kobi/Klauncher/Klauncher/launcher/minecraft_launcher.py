from pathlib import Path
from typing import Optional
import threading

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal, QThread

from launcher.launch_pipeline import LaunchPreparationError, prepare_launch
from launcher.java_detector import get_java_version


class LaunchWorker(QThread):
    finished_plan = Signal(object)
    failed = Signal(str)
    log = Signal(str)

    def __init__(self, java_path, version_id, username, uuid, game_dir, ram_gb, custom_jvm_args, data_dir_override, access_token="0", user_type="legacy", xuid=None):
        super().__init__()
        self.java_path = java_path
        self.version_id = version_id
        self.username = username
        self.uuid = uuid
        self.game_dir = game_dir
        self.ram_gb = ram_gb
        self.custom_jvm_args = custom_jvm_args
        self.data_dir_override = data_dir_override
        self.access_token = access_token
        self.user_type = user_type
        self.xuid = xuid
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            plan = prepare_launch(
                java_path=self.java_path,
                version_id=self.version_id,
                username=self.username,
                uuid=self.uuid,
                game_dir=self.game_dir,
                ram_gb=self.ram_gb,
                custom_jvm_args=self.custom_jvm_args,
                data_dir=self.data_dir_override,
                log=self.log.emit,
                allow_download=True,
                access_token=self.access_token,
                user_type=self.user_type,
                xuid=self.xuid,
            )
            if self._cancelled:
                self.failed.emit("Launch cancelled by user")
                return
            self.finished_plan.emit(plan)
        except LaunchPreparationError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unexpected launch error: {exc}")


class MinecraftLauncher(QObject):
    """Starts Minecraft from a metadata-driven launch plan (async preparation)."""

    log_message = Signal(str)
    process_finished = Signal(int)
    process_started = Signal()
    launch_failed = Signal(str)
    launch_cancelled = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.process: Optional[QProcess] = None
        self._worker: Optional[LaunchWorker] = None
        self._preparing = False

    def launch(self,
               java_path: str,
               version_id: str,
               username: str,
               uuid: str,
               game_dir: Path,
               ram_gb: int,
               custom_jvm_args: str = "",
               data_dir_override: Optional[Path] = None,
               access_token: str = "0",
               user_type: str = "legacy",
               xuid: Optional[str] = None) -> None:
        if self._preparing:
            self.log_message.emit("Launch already preparing - please wait")
            return
        if self.process and self.process.state() != QProcess.NotRunning:
            self.log_message.emit("Minecraft already running")
            return
        self._preparing = True
        self.log_message.emit(f"Preparing launch for {version_id}...")
        # Never log access_token
        self._worker = LaunchWorker(java_path, version_id, username, uuid, game_dir, ram_gb, custom_jvm_args, data_dir_override, access_token, user_type, xuid)
        self._worker.log.connect(self.log_message)
        self._worker.finished_plan.connect(self._on_plan_ready)
        self._worker.failed.connect(self._on_prepare_failed)
        self._worker.start()

    def cancel_launch(self):
        if self._worker and self._preparing:
            self._worker.cancel()
            self._worker.wait(2000)
            self._worker = None
            self._preparing = False
            self.log_message.emit("Launch cancelled")
            self.launch_cancelled.emit()
            return True
        if self.process and self.process.state() != QProcess.NotRunning:
            # terminate only our child
            self.log_message.emit("Stopping Minecraft process...")
            self.process.terminate()
            # give 3s then kill
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, self._force_kill)
            return True
        return False

    def _force_kill(self):
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.log_message.emit("Process killed")

    def _on_plan_ready(self, plan):
        self._preparing = False
        self._worker = None
        java_ver = get_java_version(plan.java_path)
        if java_ver:
            self.log_message.emit(f"Detected Java version: {java_ver}")

        self.process = QProcess(self)
        self.process.setProgram(plan.java_path)
        self.process.setArguments(plan.full_args)
        self.process.setWorkingDirectory(str(plan.game_dir))
        env = QProcessEnvironment.systemEnvironment()
        self.process.setProcessEnvironment(env)
        # Merge channels to avoid missing output, but keep separate signals
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._on_process_finished)
        self.process.errorOccurred.connect(self._on_process_error)

        self.log_message.emit(f"Launching Minecraft {plan.version_id} with Java {plan.java_path}")
        # Note: GUI errors (Swing JOptionPane) won't appear in stdout/stderr - they are native windows
        self.log_message.emit("Note: Some mod errors show as separate windows (Swing) and won't appear in log.")
        self.process.start()
        # Check if failed to start immediately
        if not self.process.waitForStarted(5000):
            self.log_message.emit(f"Failed to start process: {self.process.errorString()}")
            self.launch_failed.emit(self.process.errorString())
        else:
            self.process_started.emit()

    def _on_prepare_failed(self, msg):
        self._preparing = False
        self._worker = None
        self.log_message.emit(msg)
        self.log_message.emit("Launch preparation failed. Aborting.")
        self.launch_failed.emit(msg)

    def _read_stdout(self):
        if self.process:
            data = self.process.readAllStandardOutput()
            text = bytes(data).decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line.strip():
                    self.log_message.emit(line)

    def _read_stderr(self):
        if self.process:
            data = self.process.readAllStandardError()
            text = bytes(data).decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line.strip():
                    self.log_message.emit(line)

    def _on_process_finished(self, exit_code, exit_status):
        self.log_message.emit(f"Process finished with exit code {exit_code}")
        if exit_code != 0:
            self.log_message.emit("If a separate error window appeared, it was a Swing/Java UI dialog (e.g. Badlion agent check) not captured in stdout.")
        self.process_finished.emit(exit_code)

    def _on_process_error(self, error):
        err_str = self.process.errorString() if self.process else "Unknown error"
        self.log_message.emit(f"Process error: {err_str}")

    def is_running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def is_preparing(self) -> bool:
        return self._preparing
