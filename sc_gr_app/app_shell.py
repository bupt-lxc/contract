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

    webview.create_window(
        title="SC GR Management",
        url=str(Path(__file__).parent / "web" / "index.html"),
        js_api=ApiBridge(config),
        width=1280,
        height=820,
        min_size=(1100, 700),
    )
    webview.start(debug=True)
