import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_SEED = bytes(range(32))


@pytest.fixture
def keys():
    private = Ed25519PrivateKey.from_private_bytes(_SEED)
    private_b64 = base64.urlsafe_b64encode(_SEED).decode().rstrip("=")
    pub = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.urlsafe_b64encode(pub).decode().rstrip("="), private_b64


@pytest.fixture(autouse=True)
def hermetic_data_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRADERBOT_DB", str(tmp_path / "hermetic-traderbot.db"))
