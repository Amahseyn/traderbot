from __future__ import annotations

from pathlib import Path

from traderbot.integrations.finrl_trading.paths import finrl_trading_root, traderbot_root


def load_shared_env() -> list[Path]:
    """Load traderbot + FinRL .env (credentials, API keys)."""
    from auth.envfile import load_env_file

    loaded: list[Path] = []
    tb_env = traderbot_root() / ".env"
    if tb_env.is_file():
        load_env_file(tb_env)
        loaded.append(tb_env)
    finrl_env = finrl_trading_root() / ".env"
    if finrl_env.is_file():
        load_env_file(finrl_env)
        loaded.append(finrl_env)
    return loaded
