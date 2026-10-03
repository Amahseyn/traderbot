import base64
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def sign_request(
    *,
    private_key_b64: str,
    method: str,
    full_path: str,
    body = "",
    timestamp: str | None = None,
) -> tuple[str, str]:
    raw = private_key_b64.strip()
    padding = "=" * (-len(raw) % 4)
    try:
        key_bytes = base64.urlsafe_b64decode(raw + padding)
    except Exception:
        key_bytes = base64.b64decode(raw + padding)

    ts = timestamp or str(int(time.time()))
    message = f"{ts}{method.upper()}{full_path}{body}".encode()
    key = Ed25519PrivateKey.from_private_bytes(key_bytes)
    return base64.b64encode(key.sign(message)).decode(), ts
