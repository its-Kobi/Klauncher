import sys
from PySide6.QtWidgets import QApplication
from launcher.logging_setup import setup_logging
from core import LauncherCore
from ui import SplashScreen

def main():
    setup_logging()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from PySide6.QtCore import QTimer
    splash = SplashScreen()
    splash.show()
    app.processEvents()
    core = LauncherCore()
    try:
        from launcher.application import get_app
        get_app()
    except Exception:
        pass
    def finish_splash():
        from ui.shell.main_window import MainWindow as ShellMainWindow
        window = ShellMainWindow(core)
        splash.finish_and_close()
        QTimer.singleShot(260, lambda: (window.show(), window.raise_()))
        app._main_window = window
    QTimer.singleShot(900, finish_splash)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
