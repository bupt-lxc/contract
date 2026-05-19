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

The app is a client-side pywebview desktop application using SQLite in a shared folder. Business logic runs locally; there is no app server.
