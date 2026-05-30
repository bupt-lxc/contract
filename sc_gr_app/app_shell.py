import ctypes
import os
import sys
import threading
from pathlib import Path

import webview
from webview.platforms.edgechromium import EdgeChrome

from sc_gr_app import __version__
from sc_gr_app.api.bridge import ApiBridge
from sc_gr_app.config import default_config
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.user_service import seed_users

MUTEX_NAME = "Local\\SC_GR_MANAGEMENT_INSTANCE"
WINDOW_TITLE = "SC GR Management"
DEV_MODE = os.getenv("SC_GR_DEV") == "1"
MIN_WIDTH, MIN_HEIGHT = 1100, 700
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1280, 820


def _patch_webview2():
    _original = EdgeChrome.on_webview_ready
    def _patched(self, sender, args):
        _original(self, sender, args)
        if not args.IsSuccess:
            return
        settings = sender.CoreWebView2.Settings
        settings.AreBrowserAcceleratorKeysEnabled = False
        settings.AreDefaultContextMenusEnabled = True
        settings.AreDevToolsEnabled = DEV_MODE
    EdgeChrome.on_webview_ready = _patched


def _single_instance_check():
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() != 183:
        return
    hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
    if hwnd:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.ShowWindow(hwnd, 9)
    sys.exit(0)


def _webview2_storage():
    base = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "sc-gr-management" / "webview2"
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(base))
    return base


def _check_update(window):
    """Async check for updates on startup. Fail silently if unreachable."""
    # Placeholder — replace UPDATE_URL with actual update server when available


def _setup_tray(window):
    """Minimize to tray on close. Tray icon with context menu."""
    try:
        from pystray import Icon, Menu, MenuItem
        from PIL import Image
    except ImportError:
        return

    icon_path = Path(__file__).parent / "icons" / "tray.png"
    if not icon_path.exists():
        return

    image = Image.open(icon_path)

    def show_window(icon, item):
        window.show()
        window.restore()

    def exit_app(icon, item):
        icon.stop()
        window.destroy()
        os._exit(0)

    icon = Icon("sc-gr-mgmt", image, WINDOW_TITLE, Menu(
        MenuItem("Show Window", show_window, default=True),
        MenuItem("Exit", exit_app)
    ))

    def _on_closing():
        window.hide()

    window.events.closing += _on_closing

    threading.Thread(target=icon.run, daemon=True).start()
    return icon


def _show_error_and_exit(title: str, message: str):
    """Show a Windows error dialog and exit."""
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
    except Exception:
        pass
    sys.exit(1)


def _init_database():
    """Initialize database. Returns (config, error_message)."""
    config = default_config()
    try:
        migrate(config)
        seed_users(config)
        return config, None
    except Exception as exc:
        if DEV_MODE:
            return config, str(exc)
        db_dir = config.db_path.parent
        msg = (
            f"Unable to connect to database.\n\n"
            f"Location: {db_dir}\n"
            f"Error: {exc}\n\n"
            f"Verify the shared drive is accessible and try again.\n"
            f"If you need offline access, set SC_GR_DEV=1."
        )
        return config, msg


def run_app():
    _single_instance_check()
    _patch_webview2()

    config, init_error = _init_database()
    if init_error and not DEV_MODE:
        _show_error_and_exit("SC GR Management — Database Error", init_error)

    html_path = Path(__file__).parent / "web" / "index.html"
    storage_path = _webview2_storage()
    bridge = ApiBridge(config)

    if DEV_MODE:
        url = "http://localhost:5173"
    else:
        url = f"file://{html_path}"

    window = webview.create_window(
        WINDOW_TITLE,
        url=url,
        js_api=bridge,
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        text_select=True,
    )

    _check_update(window)
    _setup_tray(window)

    webview.start(debug=DEV_MODE)
