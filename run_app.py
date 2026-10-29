"""
Entry point for the packaged (.exe) build.

Starts the Streamlit server pointing at app.py and opens the browser. When
frozen by PyInstaller, app.py / pages / src live inside the bundle, while
config.yaml and data/ are read from the folder next to the .exe.

Important: when a frozen console app writes to a *real* Windows console, the
uvicorn/asyncio startup can crash (the window just flashes and closes). To
avoid that we redirect stdout/stderr to a log file beside the .exe at startup,
which also gives us a log to diagnose any problem.
"""

import os
import sys
import socket
import threading
import time
import webbrowser

PREFERRED_PORT = 8501


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _redirect_output() -> None:
    """Send all output to a log file next to the .exe (frozen builds only)."""
    if not getattr(sys, "frozen", False):
        return
    try:
        print("Starting the Inventory Dashboard...")
        print("A browser tab will open shortly at http://localhost:8501")
        print("Keep this window open while you use it; close it to stop.\n")
    except Exception:
        pass
    try:
        log = open(os.path.join(_base_dir(), "dashboard_log.txt"),
                   "w", encoding="utf-8", buffering=1)
        # OS-level redirect so libraries writing to fd 1/2 are covered too.
        try:
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
        except Exception:
            pass
        sys.stdout = log
        sys.stderr = log
    except Exception:
        pass


def _app_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "app.py")
    return os.path.join(_base_dir(), "app.py")


def _free_port(preferred: int = PREFERRED_PORT) -> int:
    for port in (preferred, 8502, 8503, 8504, 8510, 8888):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            continue
    return preferred


def _open_browser(port: int) -> None:
    time.sleep(5)
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass


def main() -> None:
    os.chdir(_base_dir())
    port = _free_port()
    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()

    sys.argv = [
        "streamlit", "run", _app_path(),
        "--global.developmentMode=false",
        "--server.headless=true",
        f"--server.port={port}",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
        "--theme.base=dark",
        "--theme.primaryColor=#E6B6FA",
        "--theme.backgroundColor=#0D1B3D",
        "--theme.secondaryBackgroundColor=#17264C",
        "--theme.textColor=#EAEAF5",
    ]
    from streamlit.web import cli as stcli
    stcli.main()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # prevents frozen self-spawn issues
    _redirect_output()
    try:
        main()
    except BaseException:
        import traceback
        try:
            with open(os.path.join(_base_dir(), "dashboard_error.txt"),
                      "w", encoding="utf-8") as ef:
                traceback.print_exc(file=ef)
        except Exception:
            pass
        raise
