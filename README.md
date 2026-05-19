# SC GR Management

Windows desktop SC budget, PO/vendor, and GR management app.

## Development

Install and sync dependencies with uv:

```powershell
uv sync --all-groups
```

Run the test harness:

```powershell
uv run pytest -q
```

Start the desktop app:

```powershell
uv run python -m sc_gr_app.main
```

The app is a client-side pywebview desktop application using SQLite in a shared folder. Business logic runs locally; there is no app server.

## Operations

By default, the app stores its SQLite database at `data/sc_gr.sqlite3` and lock files under `data/locks`. A shared-folder database path is a future operational setup item; configure that later when the deployment location and access model are finalized.

If the app is closed but stale lock files remain, delete only expired `.lock` files from the lock directory after confirming the app is not running or after verifying the recorded owner/session is stale. Do not remove active lock files from a running session.

## Windows Executable

Build the Windows executable with the packaging script:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

The script runs:

```powershell
uv sync --all-groups
uv run pytest -q
uv run pyinstaller packaging/app.spec
```
