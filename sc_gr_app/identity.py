import os


def get_7_digit_id() -> str:
    try:
        value = os.getlogin().strip()
        if value:
            return value
    except Exception:
        pass
    return os.getenv("USERNAME", "").strip()


def get_machine_id() -> str:
    return get_7_digit_id()
