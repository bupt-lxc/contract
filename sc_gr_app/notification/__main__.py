"""Entry point for the notification script.

Usage:
    uv run python -m sc_gr_app.notification                    # poll loop (default: 10s)
    uv run python -m sc_gr_app.notification --poll-interval 60 # custom interval
    uv run python -m sc_gr_app.notification --run-once         # one cycle + exit
    uv run python -m sc_gr_app.notification --thresholds-only  # only threshold check
    uv run python -m sc_gr_app.notification --draft            # save to Drafts folder (dev mode)
    uv run python -m sc_gr_app.notification --beta             # force beta database
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from sc_gr_app import __version__
from sc_gr_app.config import default_config
from sc_gr_app.db.migrations import migrate
from sc_gr_app.notification import engine, sender


def _setup_logging() -> None:
    """Configure logging to stdout and a desktop log file.

    The desktop log captures all scan/send/error/status-change events
    so operators can monitor the notification service at a glance.
    """
    desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    log_path = desktop / "pomp-notification.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Stdout handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(fmt)
    root_logger.addHandler(stream_handler)

    # Desktop file handler — captures everything at DEBUG level
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    logging.info("Desktop log: %s", log_path)


def main():
    parser = argparse.ArgumentParser(description="Email notification script")
    parser.add_argument("--poll-interval", type=int, default=10,
                        help="Seconds between queue checks (default: 10)")
    parser.add_argument("--run-once", action="store_true",
                        help="Run one cycle and exit")
    parser.add_argument("--thresholds-only", action="store_true",
                        help="Run only the threshold check and exit")
    parser.add_argument("--draft", action="store_true",
                        help="Save emails to Drafts folder instead of sending (dev mode)")
    parser.add_argument("--beta", action="store_true",
                        help="Force beta database (pomp-beta) regardless of env or exe name")
    args = parser.parse_args()

    if args.beta:
        os.environ["SC_GR_BETA"] = "1"

    one_shot = args.run_once or args.thresholds_only

    _setup_logging()

    logging.info("POMP Notification v%s", __version__)

    if one_shot:
        # Suppress verbose startup logging in one-shot modes (invoked
        # frequently by Task Scheduler — avoid log explosion on stdout).
        logging.getLogger().handlers[0].setLevel(logging.WARNING)

    if args.draft:
        sender.set_draft_mode(True)

    config = default_config()
    if not one_shot:
        logging.info("Notification started. Database: %s", config.db_path)
        logging.info("Poll interval: %ss", args.poll_interval)
        logging.info("Draft mode: %s", args.draft)

    migrate(config)

    # Update check for run-once and thresholds-only modes
    if one_shot:
        _check_for_update(config)

    if args.thresholds_only:
        engine.run_thresholds_only(config)
    elif args.run_once:
        engine.run_once(config)
    else:
        engine.run_poll_loop(config, poll_interval=args.poll_interval)


def _check_for_update(config):
    """Check for notification update. On success, replaces current exe and exits.
    On any failure, logs and returns silently (email delivery takes priority)."""
    import shutil

    from sc_gr_app.update import fetch_manifest, is_update_available, verify_manifest, sha256_file

    # Only perform self-update when running as a bundled executable
    if not getattr(sys, 'frozen', False):
        return

    manifest = fetch_manifest()
    if manifest is None or not is_update_available(manifest):
        return

    if not verify_manifest(manifest):
        logging.warning("Update manifest invalid, skipping update")
        return

    new_version = manifest["version"]
    package_name = manifest["notification"]["package"]
    expected_hash = manifest["notification"]["sha256"]
    releases_dir = config.db_path.parent.parent / "releases"
    package_src = releases_dir / package_name
    temp_dir = Path(os.getenv("TEMP")) / "sc-gr-update"
    temp_dir.mkdir(parents=True, exist_ok=True)
    package_dst = temp_dir / package_name

    try:
        shutil.copy2(package_src, package_dst)
    except OSError:
        logging.warning("Failed to copy notification update from shared drive, skipping")
        return

    actual_hash = sha256_file(package_dst)
    if actual_hash != expected_hash:
        logging.warning("Notification update SHA256 mismatch, skipping")
        return

    current_exe = Path(sys.executable)
    old_exe = current_exe.with_suffix(".exe.old")
    new_exe = current_exe.with_suffix(".exe.new")

    try:
        # Step 1: Copy new exe to a temp name first
        shutil.copy2(package_dst, new_exe)
        # Step 2: Rename current to .old
        if old_exe.exists():
            old_exe.unlink()
        current_exe.rename(old_exe)
        # Step 3: Rename new into place
        new_exe.rename(current_exe)
    except OSError:
        logging.warning("Failed to replace notification exe, skipping")
        # Clean up temp file if it exists
        try:
            if new_exe.exists():
                new_exe.unlink()
        except OSError:
            pass
        # Rollback: if current was renamed to .old, move it back
        try:
            if old_exe.exists() and not current_exe.exists():
                old_exe.rename(current_exe)
        except OSError:
            pass
        return

    # Schedule old file deletion on next reboot
    import ctypes
    try:
        ctypes.windll.kernel32.MoveFileExW(str(old_exe), None, 4)  # MOVEFILE_DELAY_UNTIL_REBOOT = 4
    except Exception:
        pass

    logging.info("Notification updated to v%s, exiting for restart by scheduler", new_version)
    sys.exit(0)


if __name__ == "__main__":
    main()
