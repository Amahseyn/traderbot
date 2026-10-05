from __future__ import annotations

import json
import os
import sys

from auth.envfile import load_env_file
from traderbot.nobitex.client import NobitexClient, NobitexClientError


def nobitex_keys_configured() -> bool:
    load_env_file()
    pub = os.environ.get("NOBITEX_API_PUBLIC_KEY", "").strip()
    priv = os.environ.get("NOBITEX_API_PRIVATE_KEY", "").strip()
    return bool(pub and priv)


def print_nobitex_profile() -> None:
    load_env_file()
    try:
        data = NobitexClient.from_env().request("GET", "/users/profile")
    except NobitexClientError as exc:
        print(exc, file=sys.stderr)
        if exc.body is not None:
            print(json.dumps(exc.body, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(data, ensure_ascii=False, indent=2))
