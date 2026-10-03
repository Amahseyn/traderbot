import json

from traderbot.terminal_cli import main as terminal_main


def test_terminal_catalog(capsys):
    terminal_main(["catalog", "--implemented-only"])
    out = json.loads(capsys.readouterr().out)
    assert any(c["id"] == "run" for c in out["commands"])
    assert out["strategies"]
    assert all(s["implemented"] for s in out["strategies"])


def test_terminal_run_max_steps(keys, monkeypatch):
    pub, priv = keys
    bar = {
        "symbol": "BTCIRT",
        "resolution": "60",
        "timestamp": 1,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1.0,
    }
    seen: list[int] = []

    def source():
        seen.append(1)
        return bar if len(seen) == 1 else None

    class FakeBot:
        def __init__(self, traders, interval_sec=60.0):
            self.traders = traders

        def run(self, max_steps=None):
            steps = max_steps or 1
            for _ in range(steps):
                for trader in self.traders:
                    trader.step()

    monkeypatch.setenv("NOBITEX_API_PUBLIC_KEY", pub)
    monkeypatch.setenv("NOBITEX_API_PRIVATE_KEY", priv)
    monkeypatch.setattr("traderbot.terminal.live.incremental_bar_source", lambda **_k: source)
    monkeypatch.setattr("traderbot.terminal.live.Bot", FakeBot)

    terminal_main(
        [
            "run",
            "--strategy",
            "sma_cross",
            "--max-steps",
            "2",
            "--poll-sec",
            "0.01",
        ]
    )


def test_terminal_once(monkeypatch, capsys):
    bar = {
        "symbol": "BTCIRT",
        "resolution": "60",
        "timestamp": 99,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 2.0,
        "volume": 1.0,
    }
    monkeypatch.setattr("traderbot.terminal.once.fetch_latest_closed_bar", lambda **_k: bar)
    terminal_main(["once", "--strategy", "sma_cross"])
    row = json.loads(capsys.readouterr().out)
    assert row["event"] == "once"
    assert row["strategy_id"] == "sma_cross"
    assert row["timestamp"] == 99


def test_terminal_replay(tmp_path, capsys):
    csv = tmp_path / "bars.csv"
    csv.write_text(
        "symbol,resolution,timestamp,datetime_utc,open,high,low,close,volume\n"
        "BTCIRT,60,1,1970-01-01T00:00:01+00:00,1,1,1,1,1\n"
        "BTCIRT,60,2,1970-01-01T00:00:02+00:00,2,2,2,2,1\n",
        encoding="utf-8",
    )
    terminal_main(["replay", str(csv), "--strategy", "sma_cross", "--emit-holds"])
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0]["action"] == "hold"
