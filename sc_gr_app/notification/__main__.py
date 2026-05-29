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

    if args.thresholds_only:
        engine.run_thresholds_only(config)
    elif args.run_once:
        engine.run_once(config)
    else:
        engine.run_poll_loop(config, poll_interval=args.poll_interval)


if __name__ == "__main__":
    main()
