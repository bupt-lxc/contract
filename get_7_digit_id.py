"""
Get the current user's 7-character Windows ID.

WorkshopMS uses this rule:
1. Try os.getlogin()
2. If that fails, fall back to the USERNAME environment variable
"""

import os


def get_7_digit_id() -> str:
    try:
        value = os.getlogin().strip()
        if value:
            return value
    except Exception:
        pass
    return os.getenv("USERNAME", "").strip()


if __name__ == "__main__":
    user_id = get_7_digit_id()
    if not user_id:
        raise SystemExit("Failed to get Windows user ID")
    print(user_id)
