import sys
import os

# Enable MEIPASS for resource access in PyInstaller bundles
if hasattr(sys, '_MEIPASS'):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# True filesystem root where the .exe lives
if getattr(sys, 'frozen', False):
    EXE_DIR = os.path.dirname(sys.executable)
else:
    EXE_DIR = os.path.dirname(os.path.abspath(__file__))


# Inject /src into sys.path so all modules are resolvable
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from ui.main_window import MainWindow
from utils.logging_utils import get_logger, set_global_logging_level, install_crash_handlers
from core.config_loader import global_config

def main():
    # Install crash/exit handlers as early as possible
    try:
        install_crash_handlers()
    except Exception:
        pass

    # Apply persisted logging level as early as possible
    try:
        lvl = global_config.get("UserSettings", "logging_level", "Info") or "Info"
        set_global_logging_level(lvl)
    except Exception:
        # Proceed with defaults if config not ready
        pass

    log = get_logger("startup")
    log.info("FaxRetriever 2.0 Starting")

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)

    try:
        # Log graceful application quit via Qt signal in addition to atexit
        app.aboutToQuit.connect(lambda: get_logger("lifecycle").info("Application quitting (Qt aboutToQuit)."))
    except Exception:
        pass

    window = MainWindow(base_dir=BASE_DIR, exe_dir=EXE_DIR)
    window.show()

    exit_code = app.exec_()
    try:
        get_logger("lifecycle").info(f"Application main loop exited with code {exit_code}.")
    except Exception:
        pass
    sys.exit(exit_code)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log = get_logger("fatal")
        log.exception(f"Application failed to start: {e}")
        print(f"Fatal error: {e}")
