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

# Store WNDPROC callback reference to prevent garbage collection
_tray_wndproc = None

# ── Win32 API type-safety setup ──────────────────────────────────────────
# Without restype, ctypes defaults to c_int (32-bit), which truncates
# 64-bit pointers (HWND, WNDPROC, LONG_PTR) and corrupts window state.
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# HWND / HANDLE / LONG_PTR — must be pointer-width on 64-bit
_user32.FindWindowW.restype = ctypes.c_void_p
_user32.FindWindowW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
_user32.GetWindowLongPtrW.restype = ctypes.c_longlong
_user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_longlong
_user32.CallWindowProcW.restype = ctypes.c_longlong
_user32.ShowWindow.restype = ctypes.c_bool
_user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.SetForegroundWindow.restype = ctypes.c_bool
_user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
_user32.MessageBoxW.restype = ctypes.c_int
_user32.MessageBoxW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]

# Mutex handle
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]


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
    mutex = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if _kernel32.GetLastError() != 183:
        return
    hwnd = _user32.FindWindowW(None, WINDOW_TITLE)
    if hwnd:
        # SW_SHOW (5) reveals a window hidden to tray; SW_RESTORE (9) handles minimized
        _user32.ShowWindow(hwnd, 5)    # SW_SHOW
        _user32.ShowWindow(hwnd, 9)    # SW_RESTORE
        _user32.SetForegroundWindow(hwnd)
    sys.exit(0)


def _webview2_storage():
    base = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "sc-gr-management" / "webview2"
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(base))
    return base


def _check_update(window):
    """Async check for updates on startup. Fail silently if unreachable."""
    # Placeholder — replace UPDATE_URL with actual update server when available


def _hook_close(hwnd, allow_close):
    """Subclass the Win32 window to hide on close instead of destroying."""
    global _tray_wndproc

    GWLP_WNDPROC = -4
    WM_CLOSE = 0x0010

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong,   # LRESULT
        ctypes.c_void_p,     # HWND
        ctypes.c_uint,       # UINT
        ctypes.c_ulonglong,  # WPARAM
        ctypes.c_longlong,   # LPARAM
    )

    original = _user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)

    @WNDPROC
    def wnd_proc(hwnd_, msg, wparam, lparam):
        if msg == WM_CLOSE and not allow_close[0]:
            _user32.ShowWindow(hwnd_, 0)  # SW_HIDE
            return 0
        return _user32.CallWindowProcW(
            ctypes.c_void_p(original), hwnd_, msg, wparam, lparam,
        )

    _user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, wnd_proc)
    _tray_wndproc = wnd_proc  # prevent GC


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

    _allow_close = [False]  # mutable container shared across closures

    def show_window(icon, item):
        window.show()
        window.restore()

    def exit_app(icon, item):
        _allow_close[0] = True
        icon.stop()
        window.destroy()
        os._exit(0)

    def _on_shown():
        """Hook WM_CLOSE after the native window is ready."""
        hwnd = _user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            _hook_close(hwnd, _allow_close)

    window.events.shown += _on_shown

    icon = Icon("sc-gr-mgmt", image, WINDOW_TITLE, Menu(
        MenuItem("Show Window", show_window, default=True),
        MenuItem("Exit", exit_app),
    ))

    threading.Thread(target=icon.run, daemon=True).start()
    return icon


def _show_error_and_exit(title: str, message: str):
    """Show a Windows error dialog and exit."""
    try:
        _user32.MessageBoxW(0, message, title, 0x10)  # MB_ICONERROR
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
