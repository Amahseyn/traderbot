from __future__ import annotations

from functools import lru_cache

from hyperliquid.info import Info
from hyperliquid.utils import constants


@lru_cache(maxsize=1)
def hyperliquid_info() -> Info:
    return Info(constants.MAINNET_API_URL, skip_ws=True)
