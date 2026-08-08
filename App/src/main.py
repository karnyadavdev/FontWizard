import ctypes
import sys
import traceback
from pathlib import Path

from checks import is_admin
from paths import RuntimePaths


def run_as_admin():
    executable = sys.executable

    if getattr(sys, "frozen", False):
        arguments = " ".join(f'"{arg}"' for arg in sys.argv[1:])
        working_dir = None
    else:
        script_path = Path(sys.argv[0]).resolve()
        arguments = " ".join(f'"{arg}"' for arg in (str(script_path), *sys.argv[1:]))
        working_dir = str(script_path.parent)

    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, arguments, working_dir, 1
    )
    if result <= 32:
        return False
    return True


def main():
    if "--no-admin" not in sys.argv and not is_admin():
        if not run_as_admin():
            return 1
        return 0

    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication

    from ui import FontWizardApp

    paths = RuntimePaths.discover()
    paths.ensure_runtime_dirs()
    crash_log = paths.log_root / "crash.log"

    def write_crash_log(text):
        with crash_log.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    def logging_hook(exctype, value, tb):
        err_msg = "".join(traceback.format_exception(exctype, value, tb))
        write_crash_log(err_msg)

    sys.excepthook = logging_hook

    try:
        app = QApplication(sys.argv)
        app.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
        window = FontWizardApp()
        return window.run()
    except Exception:
        write_crash_log(traceback.format_exc())
        raise


if __name__ == "__main__":
    sys.exit(main())
