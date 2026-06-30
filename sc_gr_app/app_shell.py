import ctypes
import logging
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

MUTEX_NAME = "Local\\POMP_BETA_INSTANCE" if os.getenv("SC_GR_BETA") == "1" else "Local\\POMP_INSTANCE"
WINDOW_TITLE = "PO Management Platform Beta" if os.getenv("SC_GR_BETA") == "1" else "PO Management Platform"
DEV_MODE = os.getenv("SC_GR_DEV") == "1"
BETA_MODE = os.getenv("SC_GR_BETA") == "1"
MIN_WIDTH, MIN_HEIGHT = 1100, 700
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1280, 820


def _setup_logging():
    """Beta builds: write debug log to the desktop. Release builds: no file logging."""
    if not BETA_MODE:
        return
    desktop = Path.home() / "Desktop"
    log_path = desktop / "pomp-debug.log"
    try:
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        fh = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root.addHandler(fh)
    except OSError:
        pass  # can't log — nothing we can do at this early stage

# Store WNDPROC callback reference to prevent garbage collection
_tray_wndproc = None

# ── Win32 API type-safety setup ──────────────────────────────────────────
# Without restype, ctypes defaults to c_int (32-bit), which truncates
# 64-bit pointers (HWND, WNDPROC, LONG_PTR) and corrupts window state.
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# ── WNDPROC callback type (64-bit window procedure) ────────────────────
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong,   # LRESULT
    ctypes.c_void_p,     # HWND
    ctypes.c_uint,       # UINT
    ctypes.c_ulonglong,  # WPARAM
    ctypes.c_longlong,   # LPARAM
)

# HWND / HANDLE / LONG_PTR — must be pointer-width on 64-bit
_user32.FindWindowW.restype = ctypes.c_void_p
_user32.FindWindowW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
_user32.GetWindowLongPtrW.restype = ctypes.c_longlong
_user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_longlong
_user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, WNDPROC]
_user32.CallWindowProcW.restype = ctypes.c_longlong
_user32.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong]
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
    folder = "pomp-beta" if BETA_MODE else "pomp"
    base = Path(os.getenv("LOCALAPPDATA") or Path.home()) / folder / "webview2"
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("WEBVIEW2_USER_DATA_FOLDER", str(base))
    return base


def _check_update():
    """Check for and apply updates from shared drive. Called before _init_database.
    Exits the process if an update is found and launched, or on fatal errors."""
    from sc_gr_app.update import (
        _releases_dir,
        fetch_manifest,
        is_update_available,
        verify_manifest,
        sha256_file,
    )

    try:
        default_config()
    except OSError as exc:
        _show_error_and_exit(
            "PO Management Platform — Update Error",
            f"Unable to access shared drive.\n\nError: {exc}\n\nVerify the shared drive is accessible.",
        )

    manifest = fetch_manifest()
    if manifest is None:
        if os.getenv("SC_GR_DEV") == "1":
            return
        if BETA_MODE:
            return  # beta releases folder may not exist yet
        releases_dir = _releases_dir()
        manifest_path = releases_dir / "manifest.json"
        if not releases_dir.exists():
            detail = f"Releases folder not found:\n{releases_dir}"
        elif not manifest_path.exists():
            detail = f"Update manifest not found:\n{manifest_path}"
        else:
            detail = f"Failed to read update manifest:\n{manifest_path}"
        _show_error_and_exit(
            "PO Management Platform — Update Error",
            f"{detail}\n\nVerify the shared drive is accessible.",
        )

    if not is_update_available(manifest):
        return

    if not verify_manifest(manifest):
        _show_error_and_exit(
            "PO Management Platform — Update Error",
            "Update manifest is invalid. Contact your administrator.",
        )

    new_version = manifest["version"]
    changelog = manifest.get("changelog_cn", "")
    body = f"Found version {new_version}\n\n{changelog}\n\nClick OK to install the update. The app will restart automatically."
    rc = _user32.MessageBoxW(0, body, "PO Management Platform — Update Available", 0x40 | 0x01)  # MB_ICONINFORMATION | MB_OKCANCEL
    if rc != 1:  # IDOK
        sys.exit(0)

    installer_name = manifest["gui"]["installer"]
    expected_hash = manifest["gui"]["sha256"]
    releases_dir = _releases_dir()
    installer_src = releases_dir / installer_name
    temp_dir = Path(os.getenv("TEMP")) / "pomp-update"
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        _show_error_and_exit(
            "PO Management Platform — Update Error",
            "Failed to create temporary directory for the update. Check disk space.",
        )
    installer_dst = temp_dir / installer_name

    try:
        import shutil
        shutil.copy2(installer_src, installer_dst)
    except OSError:
        _show_error_and_exit(
            "PO Management Platform — Update Error",
            "Failed to copy the update. Verify the shared drive is accessible.",
        )

    actual_hash = sha256_file(installer_dst)
    if actual_hash != expected_hash:
        _show_error_and_exit(
            "PO Management Platform — Update Error",
            "Update file is corrupted. Contact your administrator.",
        )

    install_dir = Path(sys.executable).parent
    try:
        import subprocess
        subprocess.Popen(
            [
                str(installer_dst),
                "/SILENT",
                f"/DIR={install_dir}",
            ],
        )
    except OSError:
        _show_error_and_exit(
            "PO Management Platform — Update Error",
            "Failed to start the installer. Contact your administrator.",
        )

    sys.exit(0)


def _setup_tray(window):
    """Minimize to tray on close using native Win32 Shell_NotifyIcon.

    No external dependencies — uses only user32 + shell32 via ctypes.
    """
    from ctypes import wintypes

    logger = logging.getLogger(__name__)

    # Extract small icon from the EXE (embedded by PyInstaller via app.spec icon=)
    _shell32 = ctypes.windll.shell32
    ExtractIconExW = _shell32.ExtractIconExW
    ExtractIconExW.argtypes = [ctypes.c_wchar_p, ctypes.c_int,
                               ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    ExtractIconExW.restype = ctypes.c_uint
    hIconLarge = ctypes.c_void_p()
    hIconSmall = ctypes.c_void_p()
    count = ExtractIconExW(sys.executable, 0,
                           ctypes.byref(hIconLarge), ctypes.byref(hIconSmall), 1)
    if count == 0 or not hIconSmall:
        # Fallback: try large icon
        if hIconLarge:
            hIcon = hIconLarge
        else:
            logger.warning("Tray: ExtractIconExW failed, GetLastError=%s",
                           ctypes.get_last_error())
            return
    else:
        hIcon = hIconSmall
        # We took the small icon; destroy the large one to avoid leak
        if hIconLarge:
            _user32.DestroyIcon(hIconLarge)

    _allow_close = [False]

    # ── constants ──────────────────────────────────────────────────────
    WM_TRAYICON = 0x8000 + 100
    WM_COMMAND  = 0x0111
    IDM_SHOW    = 1001
    IDM_EXIT    = 1002
    MF_STRING   = 0
    TPM_RIGHTBUTTON = 2
    TPM_BOTTOMALIGN = 0x20

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize",           wintypes.DWORD),
            ("hWnd",             wintypes.HWND),
            ("uID",              wintypes.UINT),
            ("uFlags",           wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon",            wintypes.HICON),
            ("szTip",            wintypes.WCHAR * 128),
        ]

    nid = NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.uID = 1
    nid.uFlags = 1 | 2 | 4          # NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAYICON
    nid.hIcon = hIcon
    nid.szTip = WINDOW_TITLE

    __shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
    __shell32.Shell_NotifyIconW.restype = wintypes.BOOL

    _user32.CreatePopupMenu.restype = ctypes.c_void_p
    _user32.AppendMenuW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.UINT_PTR, wintypes.LPCWSTR]
    _user32.AppendMenuW.restype = wintypes.BOOL
    _user32.DestroyMenu.argtypes = [ctypes.c_void_p]
    _user32.DestroyMenu.restype = wintypes.BOOL
    _user32.GetCursorPos.argtypes = [ctypes.c_void_p]
    _user32.GetCursorPos.restype = wintypes.BOOL

    def _on_shown():
        import time
        for _ in range(20):
            hwnd = _user32.FindWindowW(None, WINDOW_TITLE)
            if hwnd:
                nid.hWnd = hwnd
                _shell32.Shell_NotifyIconW(0, ctypes.byref(nid))  # NIM_ADD
                _subclass_window(hwnd)
                return
            time.sleep(0.05)
        logger.warning("Tray: could not find window HWND after 1s")

    def _subclass_window(hwnd):
        """Intercept WM_CLOSE (hide to tray) and tray icon messages."""
        global _tray_wndproc

        GWLP_WNDPROC = -4
        WM_CLOSE = 0x0010

        original = _user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)

        @WNDPROC
        def wnd_proc(hwnd_, msg, wparam, lparam):
            # ── close button → hide to tray ──────────────────────────
            if msg == WM_CLOSE and not _allow_close[0]:
                _user32.ShowWindow(hwnd_, 0)  # SW_HIDE
                return 0

            # ── tray icon right-click → context menu ──────────────────
            if msg == WM_TRAYICON and lparam == 0x0205:  # WM_RBUTTONUP
                pt = POINT()
                _user32.GetCursorPos(ctypes.byref(pt))
                hMenu = _user32.CreatePopupMenu()
                _user32.AppendMenuW(hMenu, MF_STRING, IDM_SHOW, "Show Window")
                _user32.AppendMenuW(hMenu, MF_STRING, IDM_EXIT, "Exit")
                _user32.SetForegroundWindow(hwnd_)
                _user32.TrackPopupMenu(hMenu, TPM_BOTTOMALIGN | TPM_RIGHTBUTTON,
                                       pt.x, pt.y, 0, hwnd_, None)
                _user32.PostMessageW(hwnd_, 0, 0, 0)  # benign message to dismiss menu
                _user32.DestroyMenu(hMenu)
                return 0

            # ── tray icon double-click → restore window ──────────────
            if msg == WM_TRAYICON and lparam == 0x0203:  # WM_LBUTTONDBLCLK
                window.show()
                window.restore()
                return 0

            # ── context menu commands ────────────────────────────────
            if msg == WM_COMMAND:
                if wparam == IDM_SHOW:
                    window.show()
                    window.restore()
                    return 0
                if wparam == IDM_EXIT:
                    _allow_close[0] = True
                    _shell32.Shell_NotifyIconW(2, ctypes.byref(nid))  # NIM_DELETE
                    _user32.DestroyIcon(hIcon)
                    window.destroy()
                    os._exit(0)

            return _user32.CallWindowProcW(
                ctypes.c_void_p(original), hwnd_, msg, wparam, lparam)

        _user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, wnd_proc)
        _tray_wndproc = wnd_proc  # prevent GC

    window.events.shown += _on_shown


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
    _setup_logging()

    _check_update()

    config, init_error = _init_database()
    if init_error and not DEV_MODE:
        _show_error_and_exit("PO Management Platform — Database Error", init_error)

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

    _setup_tray(window)

    webview.start(debug=DEV_MODE)
