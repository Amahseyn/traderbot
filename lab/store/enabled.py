import os


def store_recording_enabled() -> bool:
    value = os.environ.get("TRADERBOT_STORE", "1").strip().lower()
    return value not in ("0", "false", "no", "off")
