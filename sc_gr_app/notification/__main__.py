"""Entry point for the notification script.

Usage:
    uv run python -m sc_gr_app.notification                    # poll loop (default: 5min)
    uv run python -m sc_gr_app.notification --poll-interval 60 # custom interval
    uv run python -m sc_gr_app.notification --run-once         # one cycle + exit
    uv run python -m sc_gr_app.notification --thresholds-only  # only threshold check
    uv run python -m sc_gr_app.notification --draft            # save to Drafts folder (dev mode)
"""

import argparse
import logging
import sys

from sc_gr_app.config import default_config
from sc_gr_app.notification import engine, sender


def main():
    parser = argparse.ArgumentParser(description="Email notification script")
    parser.add_argument("--poll-interval", type=int, default=300,
                        help="Seconds between queue checks (default: 300)")
    parser.add_argument("--run-once", action="store_true",
                        help="Run one cycle and exit")
    parser.add_argument("--thresholds-only", action="store_true",
                        help="Run only the threshold check and exit")
    parser.add_argument("--draft", action="store_true",
                        help="Save emails to Drafts folder instead of sending (dev mode)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    if args.draft:
        sender.set_draft_mode(True)

    config = default_config()
    logging.info("Using database: %s", config.db_path)

    # Update check for run-once and thresholds-only modes
    if args.run_once or args.thresholds_only:
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
    import os
    import shutil
    from pathlib import Path

    from sc_gr_app.update import fetch_manifest, is_update_available, verify_manifest, sha256_file

    manifest = fetch_manifest(config)
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

    try:
        if old_exe.exists():
            old_exe.unlink()
        current_exe.rename(old_exe)
        shutil.copy2(package_dst, current_exe)
    except OSError:
        logging.warning("Failed to replace notification exe, skipping")
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
