"""FastAPI routes for dynamic pair discovery and ranking."""

from __future__ import annotations

from typing import Any

from traderbot.analysis.pairs.persistence import (
    fetch_latest_pair_ranking,
    fetch_pair_ranking_history,
    list_pair_discovery_runs,
)


def register_pair_routes(app, get_connection=None) -> None:
    from fastapi import HTTPException, Query

    @app.post("/api/pairs/discovery")
    def api_trigger_pair_discovery(body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Trigger pair discovery run (synchronous if bars_by_symbol provided, asynchronous otherwise)."""
        payload = body or {}
        bars_by_symbol = payload.get("bars_by_symbol")
        is_sync = bool(payload.get("sync", False)) or bool(bars_by_symbol)

        if is_sync and bars_by_symbol:
            from traderbot.analysis.pairs.engine import PairDiscoveryConfig, PairDiscoveryEngine
            from traderbot.analysis.pairs.models import DynamicRankingConfig

            exchange = str(payload.get("exchange") or "hyperliquid").lower()
            timeframe = str(payload.get("timeframe") or "60")
            top_n = int(payload.get("top_n") or 10)
            job_id = str(payload.get("job_id") or "") or None

            config = PairDiscoveryConfig(
                exchange=exchange,
                timeframe=timeframe,
                ranking_config=DynamicRankingConfig(top_n=top_n),
                persist=True,
            )
            engine = PairDiscoveryEngine(config)
            all_output, snapshot, transitions, summary = engine.run_discovery(
                bars_by_symbol=bars_by_symbol,
                job_id=job_id,
            )
            return {
                "status": "completed",
                "summary": summary,
                "ranked_pairs": [p.to_dict() for p in snapshot.ranked_pairs],
                "transitions": [
                    {
                        "pair_id": t.pair_id,
                        "previous_rank": t.previous_rank,
                        "new_rank": t.new_rank,
                        "change_type": t.change_type.value,
                        "reason": t.reason,
                    }
                    for t in transitions
                ],
            }

        if get_connection is not None:
            from lab.jobs import JOB_STATUS_QUEUED, _insert_job, _start_inprocess
            from lab.tasks import run_pair_discovery_task

            conn = get_connection()
            try:
                job_id = _insert_job(conn, "pair-discovery", payload)
            finally:
                conn.close()
            task_body = {**payload, "job_id": job_id}
            _start_inprocess(
                get_connection,
                job_id,
                "pair-discovery",
                lambda: run_pair_discovery_task(task_body),
            )
            return {"id": job_id, "status": JOB_STATUS_QUEUED}

        raise HTTPException(status_code=500, detail="Database connection provider not configured")

    @app.get("/api/pairs/rankings")
    def api_get_pair_rankings(
        exchange: str = Query("hyperliquid"),
        timeframe: str = Query("60"),
        top_n: int = Query(10, ge=1, le=100),
    ) -> dict[str, Any]:
        """Fetch latest dynamically ranked cointegrated pairs."""
        ranked = fetch_latest_pair_ranking(exchange=exchange, timeframe=timeframe, top_n=top_n)
        return {
            "exchange": exchange,
            "timeframe": timeframe,
            "count": len(ranked),
            "pairs": ranked,
        }

    @app.get("/api/pairs/history")
    def api_get_pair_history(
        pair_id: str = Query(..., description="Target pair id, e.g. hyperliquid:BTC-ETH"),
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        """Fetch ranking changes and score transitions for a specific pair."""
        history = fetch_pair_ranking_history(pair_id=pair_id, limit=limit)
        return {
            "pair_id": pair_id,
            "count": len(history),
            "history": history,
        }

    @app.get("/api/pairs/runs")
    def api_list_pair_discovery_runs(
        exchange: str | None = Query(None),
        limit: int = Query(50, ge=1, le=100),
    ) -> dict[str, Any]:
        """List past pair discovery runs with summary statistics."""
        runs = list_pair_discovery_runs(exchange=exchange, limit=limit)
        return {
            "count": len(runs),
            "runs": runs,
        }

    @app.get("/api/pairs/markets")
    def api_get_pair_markets(
        exchange: str = Query("hyperliquid"),
        run_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """Retrieve eligible tradable markets and rejected markets with reasons."""
        from lab.store.database import open_database
        import json

        conn = open_database()
        try:
            if run_id:
                row = conn.execute(
                    "SELECT summary_json FROM pair_discovery_runs WHERE id = ?",
                    (run_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT summary_json FROM pair_discovery_runs WHERE exchange = ? ORDER BY created_at_utc DESC LIMIT 1",
                    (exchange,),
                ).fetchone()

            summary = json.loads(row[0]) if row and row[0] else {}
            return {
                "exchange": exchange,
                "tradable_markets": summary.get("top_pairs", []),
                "total_scanned": summary.get("total_markets_scanned", 0),
                "tradable_count": summary.get("tradable_markets", 0),
                "rejected_count": summary.get("rejected_markets", 0),
                "rejected_markets": summary.get("rejected_details", {}),
            }
        finally:
            conn.close()

    @app.get("/api/pairs/candidates")
    def api_get_pair_candidates(
        run_id: str | None = Query(None),
        limit: int = Query(100, ge=1, le=500),
        category: str | None = Query(None),
    ) -> dict[str, Any]:
        """Retrieve pre-screened candidate pairs partitioned by correlation category."""
        from lab.store.database import open_database

        conn = open_database()
        try:
            target_run_id = run_id
            if not target_run_id:
                latest = conn.execute(
                    "SELECT id FROM pair_discovery_runs ORDER BY created_at_utc DESC LIMIT 1"
                ).fetchone()
                if latest:
                    target_run_id = latest[0]

            if not target_run_id:
                return {"run_id": None, "count": 0, "candidates": []}

            if category:
                rows = conn.execute(
                    """
                    SELECT id, run_id, pair_id, symbol_a, symbol_b, correlation, candidate_category
                    FROM pair_candidates
                    WHERE run_id = ? AND candidate_category = ?
                    LIMIT ?
                    """,
                    (target_run_id, category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, run_id, pair_id, symbol_a, symbol_b, correlation, candidate_category
                    FROM pair_candidates
                    WHERE run_id = ?
                    LIMIT ?
                    """,
                    (target_run_id, limit),
                ).fetchall()

            return {
                "run_id": target_run_id,
                "count": len(rows),
                "candidates": [dict(r) for r in rows],
            }
        finally:
            conn.close()

    @app.get("/api/pairs/correlation")
    def api_get_pair_correlation_matrix(
        run_id: str | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
    ) -> dict[str, Any]:
        """Retrieve return correlation summary and rankings."""
        from lab.store.database import open_database

        conn = open_database()
        try:
            target_run_id = run_id
            if not target_run_id:
                latest = conn.execute(
                    "SELECT id FROM pair_discovery_runs ORDER BY created_at_utc DESC LIMIT 1"
                ).fetchone()
                if latest:
                    target_run_id = latest[0]

            if not target_run_id:
                return {"run_id": None, "count": 0, "pairs": []}

            rows = conn.execute(
                """
                SELECT id, run_id, pair_id, symbol_a, symbol_b, correlation, candidate_category
                FROM pair_candidates
                WHERE run_id = ?
                ORDER BY correlation DESC
                LIMIT ?
                """,
                (target_run_id, limit),
            ).fetchall()

            return {
                "run_id": target_run_id,
                "count": len(rows),
                "pairs": [dict(r) for r in rows],
            }
        finally:
            conn.close()

    @app.get("/api/pairs/cointegration")
    def api_get_pair_cointegration(
        run_id: str | None = Query(None),
        status: str | None = Query(None),
        limit: int = Query(100, ge=1, le=500),
    ) -> dict[str, Any]:
        """Retrieve cointegration qualification results with MacKinnon surfaces, half-life, and Chow test status."""
        from lab.store.database import open_database
        import json

        conn = open_database()
        try:
            target_run_id = run_id
            if not target_run_id:
                latest = conn.execute(
                    "SELECT id FROM pair_discovery_runs ORDER BY created_at_utc DESC LIMIT 1"
                ).fetchone()
                if latest:
                    target_run_id = latest[0]

            if not target_run_id:
                return {"run_id": None, "count": 0, "results": []}

            if status:
                rows = conn.execute(
                    """
                    SELECT id, run_id, pair_id, qualification_status, cointegration_status,
                           hedge_ratio, half_life_bars, cointegration_pvalue, adf_statistic, rejection_reasons_json
                    FROM pair_qualification_results
                    WHERE run_id = ? AND qualification_status = ?
                    LIMIT ?
                    """,
                    (target_run_id, status.upper(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, run_id, pair_id, qualification_status, cointegration_status,
                           hedge_ratio, half_life_bars, cointegration_pvalue, adf_statistic, rejection_reasons_json
                    FROM pair_qualification_results
                    WHERE run_id = ?
                    LIMIT ?
                    """,
                    (target_run_id, limit),
                ).fetchall()

            results = []
            for r in rows:
                d = dict(r)
                try:
                    d["rejection_reasons"] = json.loads(d.pop("rejection_reasons_json"))
                except Exception:
                    d["rejection_reasons"] = []
                results.append(d)

            return {
                "run_id": target_run_id,
                "count": len(results),
                "results": results,
            }
        finally:
            conn.close()

    @app.get("/api/pairs/paper/positions")
    def api_get_paper_positions(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        """Retrieve active paper positions and closed trade history."""
        from traderbot.analysis.pairs.persistence import (
            fetch_active_pair_paper_positions,
            fetch_pair_paper_position_history,
        )

        active = fetch_active_pair_paper_positions()
        history = fetch_pair_paper_position_history(limit=limit)
        return {
            "active_count": len(active),
            "active_positions": active,
            "history_count": len(history),
            "history": history,
        }

    @app.post("/api/pairs/paper/emergency-exit")
    def api_emergency_exit_pair(body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute an audited emergency flatten for an open pair or entire portfolio."""
        import time
        from traderbot.analysis.pairs.persistence import (
            fetch_active_pair_paper_positions,
            close_pair_paper_position,
            record_pair_risk_decision,
        )

        payload = body or {}
        target_pair = payload.get("pair_id")
        reason = str(payload.get("reason") or "operator_emergency_exit")
        operator = str(payload.get("operator") or "operator")

        active = fetch_active_pair_paper_positions()
        flattens = []
        for pos in active:
            if not target_pair or pos["pair_id"] == target_pair:
                record_pair_risk_decision(
                    pair_id=pos["pair_id"],
                    check_type="EMERGENCY",
                    verdict="EMERGENCY_EXIT",
                    reason=f"{reason} by {operator}",
                )
                close_pair_paper_position(
                    position_id=pos["id"],
                    exit_spread=pos.get("entry_spread", 0.0),
                    exit_price_a=pos.get("entry_price_a", 0.0),
                    exit_price_b=pos.get("entry_price_b", 0.0),
                    realized_pnl=pos.get("unrealized_pnl", 0.0),
                    total_fees=pos.get("total_fees", 0.0),
                    total_funding=pos.get("total_funding", 0.0),
                    status="EMERGENCY_EXIT",
                )
                flattens.append(pos["pair_id"])

        return {
            "status": "ok",
            "flattened_pairs": flattens,
            "reason": reason,
            "operator": operator,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }


