from __future__ import annotations

from dataclasses import asdict

from traderbot.algorithms.registry import list_strategies
from traderbot.terminal.catalog import catalog_dict


def register_catalog_routes(app) -> None:
    @app.get("/api/catalog/strategies")
    def api_catalog_strategies(implemented_only: bool = False):
        return [asdict(entry) for entry in list_strategies(implemented_only=implemented_only)]

    @app.get("/api/catalog/models")
    def api_catalog_models(implemented_only: bool = False):
        return []

    @app.get("/api/catalog/terminal")
    def api_catalog_terminal(implemented_only: bool = False):
        return catalog_dict(implemented_only=implemented_only)
