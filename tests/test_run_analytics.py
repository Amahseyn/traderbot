from lab.store.run_analytics import compute_run_analytics


def _fill(timestamp, action, position_after, equity_after, price=100.0):
    return {
        "timestamp": timestamp,
        "action": action,
        "price": price,
        "size": 1.0,
        "position_after": position_after,
        "equity_after": equity_after,
    }


def test_compute_run_analytics_round_trips_and_drawdown():
    metrics = {
        "initial_cash": 1000.0,
        "final_equity": 1050.0,
        "total_fees": 3.0,
        "trade_logs": [
            _fill(0, "buy", 1.0, 1000.0),
            _fill(100, "sell", 0.0, 1100.0),
            _fill(200, "buy", 1.0, 1100.0),
            _fill(300, "sell", 0.0, 990.0),
            _fill(400, "buy", 1.0, 990.0),
            _fill(500, "sell", 0.0, 1050.0),
        ],
    }
    result = compute_run_analytics(metrics)
    summary = result["summary"]
    assert summary["round_trips"] == 3
    assert summary["wins"] == 2 and summary["losses"] == 1
    assert summary["net_pnl"] == 50.0
    assert summary["return_pct"] == 5.0
    assert summary["profit_factor"] == round(160 / 110, 4)
    assert summary["max_drawdown_pct"] == -10.0
    assert summary["max_drawdown_abs"] == -110.0
    assert summary["exposure_pct"] == 60.0
    assert summary["max_win_streak"] == 1
    assert summary["sharpe_per_trade"] is not None
    assert result["by_side"][0]["side"] == "long"
    assert len(result["equity_curve"]) == 7


def test_compute_run_analytics_without_logs():
    result = compute_run_analytics({"initial_cash": 1000.0, "final_equity": 1000.0})
    assert result["summary"]["round_trips"] == 0
    assert result["summary"]["win_rate_pct"] is None
    assert result["equity_curve"] == []
