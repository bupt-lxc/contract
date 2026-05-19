from pathlib import Path

import webview

from sc_gr_app.api.bridge import ApiBridge
from sc_gr_app.config import default_config
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.user_service import seed_default_admin


def run_app() -> None:
    config = default_config()
    migrate(config)
    seed_default_admin(config)
    html_path = Path(__file__).parent / "web" / "index.html"
    bridge = ApiBridge(config)

    webview.create_window(
        "SC GR Management",
        url=str(html_path),
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(1100, 700),
    )
    webview.start(debug=True)
