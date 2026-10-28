"""Market Cap local service with multi-provider aggregation and SQLite caching."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

import requests

from lab.store.database import default_database_path, open_database
from traderbot.marketcap.seed_data import SEED_COINS_LIST, SEED_GLOBAL_METRICS

__all__ = ["MarketCapService", "get_marketcap_service"]


def _current_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MarketCapService:
    def __init__(
        self,
        *,
        ttl_seconds: float = 60.0,
        request_timeout_seconds: float = 6.0,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._memory_cache: dict[str, tuple[float, Any]] = {}

    def _read_db_cache(self, cache_key: str) -> dict[str, Any] | list[Any] | None:
        try:
            database_path = default_database_path()
            if not database_path.exists():
                return None
            with open_database(database_path) as connection:
                row = connection.execute(
                    "SELECT payload_json, updated_at_utc FROM marketcap_cache WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
                if row is None:
                    return None
                payload = json.loads(str(row[0]))
                return payload
        except Exception:
            return None

    def _write_db_cache(self, cache_key: str, payload: Any) -> None:
        try:
            database_path = default_database_path()
            with open_database(database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO marketcap_cache(cache_key, payload_json, updated_at_utc)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at_utc = excluded.updated_at_utc
                    """,
                    (cache_key, json.dumps(payload), _current_utc_iso()),
                )
                connection.commit()
        except Exception:
            pass

    def _get_from_memory(self, cache_key: str) -> Any | None:
        cached = self._memory_cache.get(cache_key)
        if cached is None:
            return None
        timestamp, value = cached
        if time.time() - timestamp > self._ttl_seconds:
            return None
        return value

    def _set_memory(self, cache_key: str, value: Any) -> None:
        self._memory_cache[cache_key] = (time.time(), value)

    def fetch_global_metrics_remote(self) -> dict[str, Any] | None:
        """Fetch global market metrics from CoinGecko."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TraderBotLab/1.0)"}
        url = "https://api.coingecko.com/api/v3/global"
        try:
            response = requests.get(url, headers=headers, timeout=self._request_timeout_seconds)
            if response.status_code != 200:
                return None
            raw_data = response.json().get("data", {})
            return {
                "total_market_cap_usd": raw_data.get("total_market_cap", {}).get("usd", 0.0),
                "total_volume_24h_usd": raw_data.get("total_volume", {}).get("usd", 0.0),
                "market_cap_change_24h_pct": round(
                    float(raw_data.get("market_cap_change_percentage_24h_usd", 0.0) or 0.0),
                    2,
                ),
                "btc_dominance_pct": round(
                    float(raw_data.get("market_cap_percentage", {}).get("btc", 0.0) or 0.0),
                    2,
                ),
                "eth_dominance_pct": round(
                    float(raw_data.get("market_cap_percentage", {}).get("eth", 0.0) or 0.0),
                    2,
                ),
                "active_cryptocurrencies": int(raw_data.get("active_cryptocurrencies", 0) or 0),
                "last_updated_utc": _current_utc_iso(),
            }
        except Exception:
            return None

    def fetch_coins_remote(self, limit: int = 150) -> list[dict[str, Any]] | None:
        """Fetch coin rankings with sparklines from CoinGecko."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TraderBotLab/1.0)"}
        url = (
            "https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1"
            "&sparkline=true&price_change_percentage=1h,24h,7d"
        )
        try:
            response = requests.get(url, headers=headers, timeout=self._request_timeout_seconds)
            if response.status_code != 200:
                return None
            raw_coins = response.json()
            if not isinstance(raw_coins, list):
                return None
            coins: list[dict[str, Any]] = []
            for item in raw_coins:
                sparkline = item.get("sparkline_in_7d", {}).get("price", [])
                sampled_sparkline = [
                    round(price, 6 if price < 1 else 2)
                    for index, price in enumerate(sparkline)
                    if index % 4 == 0
                ] if sparkline else []
                coins.append({
                    "id": item.get("id"),
                    "symbol": (item.get("symbol") or "").upper(),
                    "name": item.get("name"),
                    "image": item.get("image"),
                    "current_price": item.get("current_price"),
                    "market_cap": item.get("market_cap"),
                    "market_cap_rank": item.get("market_cap_rank"),
                    "fully_diluted_valuation": item.get("fully_diluted_valuation"),
                    "total_volume": item.get("total_volume"),
                    "high_24h": item.get("high_24h"),
                    "low_24h": item.get("low_24h"),
                    "price_change_24h": item.get("price_change_24h"),
                    "price_change_percentage_24h": item.get("price_change_percentage_24h"),
                    "price_change_percentage_1h": item.get("price_change_percentage_1h_in_currency"),
                    "price_change_percentage_7d": item.get("price_change_percentage_7d_in_currency"),
                    "circulating_supply": item.get("circulating_supply"),
                    "total_supply": item.get("total_supply"),
                    "max_supply": item.get("max_supply"),
                    "ath": item.get("ath"),
                    "ath_change_percentage": item.get("ath_change_percentage"),
                    "ath_date": item.get("ath_date"),
                    "atl": item.get("atl"),
                    "atl_change_percentage": item.get("atl_change_percentage"),
                    "atl_date": item.get("atl_date"),
                    "sparkline": sampled_sparkline,
                    "last_updated": item.get("last_updated") or _current_utc_iso(),
                })
            return coins
        except Exception:
            return None

    def fetch_hyperliquid_contexts(self) -> dict[str, dict[str, Any]]:
        """Fetch Hyperliquid perpetual market info and asset contexts."""
        cached = self._get_from_memory("hyperliquid_contexts")
        if cached is not None:
            return cached
        try:
            response = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "metaAndAssetCtxs"},
                timeout=4.0,
            )
            if response.status_code != 200:
                return {}
            payload = response.json()
            universe = payload[0].get("universe", [])
            contexts = payload[1]
            lookup: dict[str, dict[str, Any]] = {}
            for asset_meta, context in zip(universe, contexts):
                symbol = asset_meta.get("name", "").upper()
                if not symbol:
                    continue
                lookup[symbol] = {
                    "funding_rate": float(context.get("funding", 0.0) or 0.0),
                    "open_interest": float(context.get("openInterest", 0.0) or 0.0),
                    "mark_price": float(context.get("markPx", 0.0) or 0.0),
                    "volume_24h_usd": float(context.get("dayNtlVlm", 0.0) or 0.0),
                    "prev_day_price": float(context.get("prevDayPx", 0.0) or 0.0),
                }
            self._set_memory("hyperliquid_contexts", lookup)
            return lookup
        except Exception:
            return {}

    def get_global_metrics(self, *, force_refresh: bool = False) -> dict[str, Any]:
        """Return global crypto market metrics, pulling from memory, remote, db, or seed."""
        cache_key = "global_metrics"
        if not force_refresh:
            cached_memory = self._get_from_memory(cache_key)
            if cached_memory is not None:
                return cached_memory

        if force_refresh or self._memory_cache.get(cache_key) is None:
            remote = self.fetch_global_metrics_remote()
            if remote:
                self._set_memory(cache_key, remote)
                self._write_db_cache(cache_key, remote)
                return remote

        db_cached = self._read_db_cache(cache_key)
        if isinstance(db_cached, dict):
            self._set_memory(cache_key, db_cached)
            return db_cached

        seed = dict(SEED_GLOBAL_METRICS)
        seed["last_updated_utc"] = _current_utc_iso()
        return seed

    def get_all_coins(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Return all coins in universe, enriched with Hyperliquid perp contexts."""
        cache_key = "coins_universe"
        coins: list[dict[str, Any]] | None = None
        if not force_refresh:
            coins = self._get_from_memory(cache_key)

        if coins is None:
            remote_coins = self.fetch_coins_remote(limit=150)
            if remote_coins:
                coins = remote_coins
                self._write_db_cache(cache_key, coins)
            else:
                db_coins = self._read_db_cache(cache_key)
                if isinstance(db_coins, list) and db_coins:
                    coins = db_coins
                else:
                    coins = [dict(item) for item in SEED_COINS_LIST]
            self._set_memory(cache_key, coins)

        hyperliquid_data = self.fetch_hyperliquid_contexts()
        enriched_coins: list[dict[str, Any]] = []
        for coin in coins:
            coin_copy = dict(coin)
            symbol = str(coin_copy.get("symbol") or "").upper()
            hl_info = hyperliquid_data.get(symbol)
            if hl_info:
                coin_copy["hyperliquid"] = {
                    "is_perp_available": True,
                    "funding_rate": hl_info["funding_rate"],
                    "open_interest": hl_info["open_interest"],
                    "mark_price": hl_info["mark_price"],
                    "volume_24h_usd": hl_info["volume_24h_usd"],
                }
            else:
                coin_copy["hyperliquid"] = {
                    "is_perp_available": False,
                    "funding_rate": None,
                    "open_interest": None,
                    "mark_price": None,
                    "volume_24h_usd": None,
                }
            enriched_coins.append(coin_copy)

        return enriched_coins

    def get_coins(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        category: str = "all",
        search: str = "",
        sort_by: str = "market_cap",
        sort_dir: str = "desc",
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Return filtered, sorted, paginated coin list."""
        all_coins = self.get_all_coins(force_refresh=force_refresh)

        filtered = all_coins
        if search.strip():
            query = search.strip().lower()
            filtered = [
                coin for coin in filtered
                if query in str(coin.get("name") or "").lower()
                or query in str(coin.get("symbol") or "").lower()
            ]

        if category == "gainers":
            filtered = [
                coin for coin in filtered
                if (coin.get("price_change_percentage_24h") or 0.0) > 0.0
            ]
            if sort_by == "market_cap":
                sort_by = "price_change_percentage_24h"
                sort_dir = "desc"
        elif category == "losers":
            filtered = [
                coin for coin in filtered
                if (coin.get("price_change_percentage_24h") or 0.0) < 0.0
            ]
            if sort_by == "market_cap":
                sort_by = "price_change_percentage_24h"
                sort_dir = "asc"
        elif category == "hyperliquid":
            filtered = [
                coin for coin in filtered
                if coin.get("hyperliquid", {}).get("is_perp_available")
            ]

        def sort_key(coin: dict[str, Any]) -> Any:
            val = coin.get(sort_by)
            if val is None:
                if sort_by == "name":
                    return ""
                return -float("inf") if sort_dir == "desc" else float("inf")
            if sort_by == "name":
                return str(val).lower()
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        reverse = (sort_dir.lower() == "desc")
        filtered.sort(key=sort_key, reverse=reverse)

        total_count = len(filtered)
        clamped_page = max(1, page)
        clamped_limit = max(1, min(limit, 250))
        start_index = (clamped_page - 1) * clamped_limit
        end_index = start_index + clamped_limit
        page_slice = filtered[start_index:end_index]

        return {
            "coins": page_slice,
            "total": total_count,
            "page": clamped_page,
            "limit": clamped_limit,
            "categories": ["all", "gainers", "losers", "hyperliquid"],
            "last_updated_utc": _current_utc_iso(),
        }

    def get_coin_details(self, coin_id_or_symbol: str) -> dict[str, Any] | None:
        """Find coin profile and enrich with live technical and perp metrics."""
        query = coin_id_or_symbol.strip().lower()
        coins = self.get_all_coins()
        for coin in coins:
            coin_id = str(coin.get("id") or "").lower()
            symbol = str(coin.get("symbol") or "").lower()
            if query in (coin_id, symbol):
                return coin
        return None

    def refresh_cache(self) -> dict[str, Any]:
        """Trigger immediate refresh of global metrics and coin rankings."""
        global_metrics = self.get_global_metrics(force_refresh=True)
        coins = self.get_all_coins(force_refresh=True)
        return {
            "status": "refreshed",
            "coins_count": len(coins),
            "global_metrics": global_metrics,
            "refreshed_at_utc": _current_utc_iso(),
        }


_SERVICE_INSTANCE: MarketCapService | None = None


def get_marketcap_service() -> MarketCapService:
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = MarketCapService()
    return _SERVICE_INSTANCE
