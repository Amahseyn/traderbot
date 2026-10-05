from __future__ import annotations

from dataclasses import asdict

from traderbot.algorithms.registry import list_strategies
from traderbot.terminal.catalog import catalog_dict


def register_catalog_routes(app) -> None:
    from fastapi import HTTPException, Query

    @app.get("/api/catalog/strategies")
    def api_catalog_strategies(implemented_only: bool = False):
        return [asdict(entry) for entry in list_strategies(implemented_only=implemented_only)]

    @app.get("/api/catalog/terminal")
    def api_catalog_terminal(implemented_only: bool = False):
        return catalog_dict(implemented_only=implemented_only)

    @app.get("/api/catalog/strategy-params")
    def api_catalog_strategy_params(strategy_id: str = Query(...)):
        from traderbot.algorithms.cli_args import default_strategy_namespace
        from traderbot.algorithms.registry import strategy_param_names

        try:
            names = strategy_param_names(strategy_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        defaults = vars(default_strategy_namespace())
        fields: list[dict[str, object]] = []
        for name in names:
            default = defaults.get(name)
            if isinstance(default, bool):
                kind = "bool"
            elif isinstance(default, int):
                kind = "int"
            elif isinstance(default, float):
                kind = "float"
            elif default is None:
                kind = "optional_float"
            else:
                kind = "string"
            fields.append({"name": name, "kind": kind, "default": default})
        return {"strategy_id": strategy_id, "params": fields}
