from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from lab.store.database import open_database
from traderbot.analysis.pairs.models import (
    CandidatePair,
    RankedPairResult,
    RankingSnapshot,
    RankTransition,
)


def record_pair_discovery_run(
    *,
    job_id: str | None = None,
    exchange: str = "hyperliquid",
    timeframe: str = "60",
    config: dict[str, Any],
    summary: dict[str, Any],
    candidates: list[CandidatePair],
    ranked_pairs: list[RankedPairResult],
    transitions: list[RankTransition],
    snapshot: RankingSnapshot | None = None,
    finished_at_utc: str | None = None,
) -> str:
    """
    Persist discovery run, candidate pairs, qualification results,
    ranking snapshot, and ranking transitions into SQLite data/traderbot.db.
    """
    run_id = job_id or str(uuid.uuid4())
    now_utc = finished_at_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    conn = open_database()
    try:
        # 1. Insert pair_discovery_runs
        conn.execute(
            """
            INSERT INTO pair_discovery_runs (
                id, job_id, exchange, timeframe, status, config_json, summary_json, created_at_utc, finished_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                summary_json = excluded.summary_json,
                finished_at_utc = excluded.finished_at_utc
            """,
            (
                run_id,
                job_id,
                exchange,
                timeframe,
                "completed",
                json.dumps(config),
                json.dumps(summary),
                now_utc,
                now_utc,
            ),
        )

        # 2. Insert pair_candidates
        for cand in candidates:
            cand_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO pair_candidates (
                    id, run_id, pair_id, symbol_a, symbol_b, correlation, candidate_category
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cand_id,
                    run_id,
                    cand.pair_id,
                    cand.symbol_a,
                    cand.symbol_b,
                    cand.correlation,
                    cand.category.value,
                ),
            )

        # 3. Insert pair_qualification_results
        for res in ranked_pairs:
            qual_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO pair_qualification_results (
                    id, run_id, pair_id, qualification_status, cointegration_status,
                    hedge_ratio, half_life_bars, cointegration_pvalue, adf_statistic, rejection_reasons_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    qual_id,
                    run_id,
                    res.pair_id,
                    res.qualification_status,
                    res.cointegration_status,
                    res.hedge_ratio,
                    res.half_life_bars,
                    res.cointegration_pvalue,
                    res.adf_statistic,
                    json.dumps(res.rejection_reasons),
                ),
            )

        # 4. Insert pair_ranking_snapshots (for ranked pairs)
        snapshot_ts = snapshot.snapshot_timestamp if snapshot else int(time.time())
        for res in ranked_pairs:
            if res.ranking_position is not None:
                snap_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO pair_ranking_snapshots (
                        id, run_id, snapshot_timestamp, pair_id, ranking_position,
                        pair_quality_score, liquidity_score, stability_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snap_id,
                        run_id,
                        snapshot_ts,
                        res.pair_id,
                        res.ranking_position,
                        res.pair_quality_score,
                        res.liquidity_score,
                        res.stability_score,
                    ),
                )

        # 5. Insert pair_ranking_changes
        for trans in transitions:
            trans_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO pair_ranking_changes (
                    id, run_id, pair_id, previous_rank, new_rank, change_type, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trans_id,
                    run_id,
                    trans.pair_id,
                    trans.previous_rank,
                    trans.new_rank,
                    trans.change_type.value,
                    trans.reason,
                ),
            )

        conn.commit()
    finally:
        conn.close()

    return run_id


def fetch_latest_pair_ranking(
    exchange: str = "hyperliquid",
    timeframe: str = "60",
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch the most recent ranked pairs for the given exchange and timeframe.
    """
    conn = open_database()
    try:
        # Find latest run
        row = conn.execute(
            """
            SELECT id FROM pair_discovery_runs
            WHERE exchange = ? AND timeframe = ? AND status = 'completed'
            ORDER BY created_at_utc DESC
            LIMIT 1
            """,
            (exchange, timeframe),
        ).fetchone()

        if row is None:
            return []

        latest_run_id = row[0]
        results = conn.execute(
            """
            SELECT s.pair_id, s.ranking_position, s.pair_quality_score, s.liquidity_score, s.stability_score,
                   s.snapshot_timestamp,
                   q.qualification_status, q.cointegration_status, q.hedge_ratio, q.half_life_bars,
                   q.rejection_reasons_json, c.symbol_a, c.symbol_b, c.correlation
            FROM pair_ranking_snapshots s
            JOIN pair_qualification_results q ON s.run_id = q.run_id AND s.pair_id = q.pair_id
            JOIN pair_candidates c ON s.run_id = c.run_id AND s.pair_id = c.pair_id
            WHERE s.run_id = ?
            ORDER BY s.ranking_position ASC
            LIMIT ?
            """,
            (latest_run_id, top_n),
        ).fetchall()

        output = []
        for r in results:
            item = {
                "pair_id": r["pair_id"],
                "exchange": exchange,
                "symbol_a": r["symbol_a"],
                "symbol_b": r["symbol_b"],
                "timeframe": timeframe,
                "correlation": round(float(r["correlation"]), 4),
                "cointegration_status": r["cointegration_status"],
                "hedge_ratio": round(float(r["hedge_ratio"]), 6),
                "half_life_bars": round(float(r["half_life_bars"]), 2) if r["half_life_bars"] is not None else None,
                "liquidity_score": round(float(r["liquidity_score"]), 2),
                "stability_score": round(float(r["stability_score"]), 2),
                "pair_quality_score": round(float(r["pair_quality_score"]), 2),
                "ranking_position": int(r["ranking_position"]),
                "qualification_status": r["qualification_status"],
                "rejection_reasons": json.loads(r["rejection_reasons_json"]),
                "last_updated": int(r["snapshot_timestamp"]),
            }
            output.append(item)

        return output
    finally:
        conn.close()


def fetch_pair_ranking_history(pair_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Fetch ranking transitions and score history for a specific pair."""
    conn = open_database()
    try:
        rows = conn.execute(
            """
            SELECT c.run_id, c.previous_rank, c.new_rank, c.change_type, c.reason, r.created_at_utc
            FROM pair_ranking_changes c
            JOIN pair_discovery_runs r ON c.run_id = r.id
            WHERE c.pair_id = ?
            ORDER BY r.created_at_utc DESC
            LIMIT ?
            """,
            (pair_id, limit),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_pair_discovery_runs(exchange: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """List recent pair discovery runs with summaries."""
    conn = open_database()
    try:
        if exchange:
            rows = conn.execute(
                """
                SELECT id, job_id, exchange, timeframe, status, summary_json, created_at_utc, finished_at_utc
                FROM pair_discovery_runs
                WHERE exchange = ?
                ORDER BY created_at_utc DESC
                LIMIT ?
                """,
                (exchange, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, job_id, exchange, timeframe, status, summary_json, created_at_utc, finished_at_utc
                FROM pair_discovery_runs
                ORDER BY created_at_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        out = []
        for row in rows:
            d = dict(row)
            try:
                d["summary"] = json.loads(d.pop("summary_json"))
            except Exception:
                d["summary"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def record_pair_strategy_signal(
    *,
    pair_id: str,
    action: str,
    spread: float,
    z_score: float,
    dominant_price: float,
    hedge_price: float,
    hedge_ratio: float,
    dominant_qty: float,
    hedge_qty: float,
    run_id: str | None = None,
    timestamp_utc: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Persist an evaluated pair strategy signal."""
    signal_id = str(uuid.uuid4())
    now_utc = timestamp_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta_json = json.dumps(metadata or {})
    conn = open_database()
    try:
        conn.execute(
            """
            INSERT INTO pair_strategy_signals (
                id, run_id, pair_id, timestamp_utc, action, spread, z_score,
                dominant_price, hedge_price, hedge_ratio, dominant_qty, hedge_qty, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                run_id,
                pair_id,
                now_utc,
                action,
                spread,
                z_score,
                dominant_price,
                hedge_price,
                hedge_ratio,
                dominant_qty,
                hedge_qty,
                meta_json,
            ),
        )
        conn.commit()
        return signal_id
    finally:
        conn.close()


def fetch_pair_strategy_signals(
    pair_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch recent strategy signals for a pair."""
    conn = open_database()
    try:
        rows = conn.execute(
            """
            SELECT id, run_id, pair_id, timestamp_utc, action, spread, z_score,
                   dominant_price, hedge_price, hedge_ratio, dominant_qty, hedge_qty, metadata_json
            FROM pair_strategy_signals
            WHERE pair_id = ?
            ORDER BY timestamp_utc DESC
            LIMIT ?
            """,
            (pair_id, limit),
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            try:
                d["metadata"] = json.loads(d.pop("metadata_json"))
            except Exception:
                d["metadata"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def record_pair_paper_position(
    *,
    pair_id: str,
    entry_spread: float,
    leg_a_qty: float,
    leg_b_qty: float,
    entry_price_a: float,
    entry_price_b: float,
    entry_z_score: float | None = None,
    opened_at_utc: str | None = None,
    snapshot: dict[str, Any] | None = None,
) -> str:
    """Record an opening pair paper position."""
    pos_id = str(uuid.uuid4())
    now_utc = opened_at_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    snap_json = json.dumps(snapshot or {})
    conn = open_database()
    try:
        conn.execute(
            """
            INSERT INTO pair_paper_positions (
                id, pair_id, status, opened_at_utc, entry_spread, entry_z_score,
                leg_a_qty, leg_b_qty, entry_price_a, entry_price_b, snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pos_id,
                pair_id,
                "OPEN",
                now_utc,
                entry_spread,
                entry_z_score,
                leg_a_qty,
                leg_b_qty,
                entry_price_a,
                entry_price_b,
                snap_json,
            ),
        )
        conn.commit()
        return pos_id
    finally:
        conn.close()


def update_pair_paper_position(
    *,
    position_id: str,
    unrealized_pnl: float,
    total_fees: float,
    total_funding: float,
    snapshot: dict[str, Any] | None = None,
) -> None:
    """Update mark-to-market status and PnL of an open position."""
    snap_json = json.dumps(snapshot or {})
    conn = open_database()
    try:
        conn.execute(
            """
            UPDATE pair_paper_positions
            SET unrealized_pnl = ?, total_fees = ?, total_funding = ?, snapshot_json = ?
            WHERE id = ?
            """,
            (unrealized_pnl, total_fees, total_funding, snap_json, position_id),
        )
        conn.commit()
    finally:
        conn.close()


def close_pair_paper_position(
    *,
    position_id: str,
    exit_spread: float,
    exit_price_a: float,
    exit_price_b: float,
    realized_pnl: float,
    total_fees: float,
    total_funding: float,
    exit_z_score: float | None = None,
    closed_at_utc: str | None = None,
    status: str = "CLOSED",
    snapshot: dict[str, Any] | None = None,
) -> None:
    """Record closing of a pair position."""
    now_utc = closed_at_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    snap_json = json.dumps(snapshot or {})
    conn = open_database()
    try:
        conn.execute(
            """
            UPDATE pair_paper_positions
            SET status = ?, closed_at_utc = ?, exit_spread = ?, exit_z_score = ?,
                exit_price_a = ?, exit_price_b = ?, realized_pnl = ?, unrealized_pnl = 0.0,
                total_fees = ?, total_funding = ?, snapshot_json = ?
            WHERE id = ?
            """,
            (
                status,
                now_utc,
                exit_spread,
                exit_z_score,
                exit_price_a,
                exit_price_b,
                realized_pnl,
                total_fees,
                total_funding,
                snap_json,
                position_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def fetch_active_pair_paper_positions() -> list[dict[str, Any]]:
    """Retrieve all open pair paper positions."""
    conn = open_database()
    try:
        rows = conn.execute(
            """
            SELECT id, pair_id, status, opened_at_utc, entry_spread, entry_z_score,
                   leg_a_qty, leg_b_qty, entry_price_a, entry_price_b,
                   realized_pnl, unrealized_pnl, total_fees, total_funding, snapshot_json
            FROM pair_paper_positions
            WHERE status = 'OPEN'
            ORDER BY opened_at_utc DESC
            """
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            try:
                d["snapshot"] = json.loads(d.pop("snapshot_json"))
            except Exception:
                d["snapshot"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def fetch_pair_paper_position_history(
    pair_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch history of closed and open pair positions."""
    conn = open_database()
    try:
        if pair_id:
            rows = conn.execute(
                """
                SELECT id, pair_id, status, opened_at_utc, closed_at_utc, entry_spread, exit_spread,
                       entry_z_score, exit_z_score, leg_a_qty, leg_b_qty, entry_price_a, entry_price_b,
                       exit_price_a, exit_price_b, realized_pnl, unrealized_pnl, total_fees, total_funding,
                       snapshot_json
                FROM pair_paper_positions
                WHERE pair_id = ?
                ORDER BY opened_at_utc DESC
                LIMIT ?
                """,
                (pair_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, pair_id, status, opened_at_utc, closed_at_utc, entry_spread, exit_spread,
                       entry_z_score, exit_z_score, leg_a_qty, leg_b_qty, entry_price_a, entry_price_b,
                       exit_price_a, exit_price_b, realized_pnl, unrealized_pnl, total_fees, total_funding,
                       snapshot_json
                FROM pair_paper_positions
                ORDER BY opened_at_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            try:
                d["snapshot"] = json.loads(d.pop("snapshot_json"))
            except Exception:
                d["snapshot"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def record_pair_execution_event(
    *,
    position_id: str | None,
    pair_id: str,
    leg: str,
    action: str,
    requested_qty: float,
    filled_qty: float,
    fill_price: float,
    fee: float = 0.0,
    slippage: float = 0.0,
    execution_status: str = "FILLED",
    timestamp_utc: str | None = None,
    notes: str | None = None,
) -> str:
    """Record an individual execution event (fill, partial fill, unwind)."""
    event_id = str(uuid.uuid4())
    now_utc = timestamp_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = open_database()
    try:
        conn.execute(
            """
            INSERT INTO pair_execution_events (
                id, position_id, pair_id, timestamp_utc, leg, action,
                requested_qty, filled_qty, fill_price, fee, slippage, execution_status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                position_id,
                pair_id,
                now_utc,
                leg,
                action,
                requested_qty,
                filled_qty,
                fill_price,
                fee,
                slippage,
                execution_status,
                notes,
            ),
        )
        conn.commit()
        return event_id
    finally:
        conn.close()


def fetch_pair_execution_events(
    pair_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve execution events for a pair."""
    conn = open_database()
    try:
        rows = conn.execute(
            """
            SELECT id, position_id, pair_id, timestamp_utc, leg, action,
                   requested_qty, filled_qty, fill_price, fee, slippage, execution_status, notes
            FROM pair_execution_events
            WHERE pair_id = ?
            ORDER BY timestamp_utc DESC
            LIMIT ?
            """,
            (pair_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def record_pair_risk_decision(
    *,
    pair_id: str,
    check_type: str,
    verdict: str,
    reason: str,
    metrics: dict[str, Any] | None = None,
    timestamp_utc: str | None = None,
) -> str:
    """Record an audited risk check verdict."""
    decision_id = str(uuid.uuid4())
    now_utc = timestamp_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    metrics_json = json.dumps(metrics or {})
    conn = open_database()
    try:
        conn.execute(
            """
            INSERT INTO pair_risk_decisions (
                id, pair_id, timestamp_utc, check_type, verdict, reason, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (decision_id, pair_id, now_utc, check_type, verdict, reason, metrics_json),
        )
        conn.commit()
        return decision_id
    finally:
        conn.close()


def fetch_pair_risk_decisions(
    pair_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Fetch risk decisions for a pair."""
    conn = open_database()
    try:
        rows = conn.execute(
            """
            SELECT id, pair_id, timestamp_utc, check_type, verdict, reason, metrics_json
            FROM pair_risk_decisions
            WHERE pair_id = ?
            ORDER BY timestamp_utc DESC
            LIMIT ?
            """,
            (pair_id, limit),
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            try:
                d["metrics"] = json.loads(d.pop("metrics_json"))
            except Exception:
                d["metrics"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


