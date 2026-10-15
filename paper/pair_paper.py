"""PAPER ONLY: Nobitex pair-trading paper runner. Public candles only, simulated fills, no keys, no orders."""
import argparse, csv, json, os, sys, time, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from traderbot.backtesting.eval_data import fetch_history_bars, nobitex_symbol
from traderbot.algorithms.registry import pair_algorithm_for_id
from traderbot.backtesting.pair_engine import run_pair_backtest_for_exchange

p = argparse.ArgumentParser()
p.add_argument("--src", default="btc"); p.add_argument("--hedge", default="eth")
p.add_argument("--dst", default="rls"); p.add_argument("--interval", default="60")
p.add_argument("--poll-sec", type=int, default=120); p.add_argument("--out", required=True)
p.add_argument("--fee", type=float, default=0.0025); p.add_argument("--slippage", type=float, default=0.0005)
a = p.parse_args()
dom, hed = nobitex_symbol(a.src, a.dst), nobitex_symbol(a.hedge, a.dst)
params = dict(lookback_period=60, entry_threshold=2.0, exit_threshold=0.5)
start = int(time.time()); months = 1 if a.interval in ("1","5","15","60") else 3
csvp = a.out + ".csv"
new = not os.path.exists(csvp)
with open(csvp, "a", newline="") as f:
    w = csv.writer(f)
    if new: w.writerow(["ts_local","bar_ts","dominant_close","hedge_close","z","equity","return_pct","n_trades","last_trade"])
print(json.dumps({"event":"start","mode":"PAPER","dom":dom,"hedge":hed,"interval":a.interval,"params":params}), flush=True)
last_bar = None
while True:
    try:
        d = fetch_history_bars(exchange="nobitex", symbol_key=dom, resolution=a.interval, months=months, use_cache=False)
        h = fetch_history_bars(exchange="nobitex", symbol_key=hed, resolution=a.interval, months=months, use_cache=False)
        lb = params["lookback_period"] + 5
        sec = {"60":3600,"240":14400}.get(a.interval, 3600)
        # warm-up bars before session start + all bars since
        def cut(b): 
            idx = [i for i,x in enumerate(b) if int(x["timestamp"]) >= start - sec]
            i0 = max(0, (idx[0] if idx else len(b)) - lb); return b[i0:]
        d2, h2 = cut(d), cut(h)
        algo = pair_algorithm_for_id("pair_trading", **params)
        r = run_pair_backtest_for_exchange("nobitex", algo, d2, h2, fee_rate=a.fee, slippage_rate=a.slippage, initial_cash=1000.0)
        bt = int(d2[-1]["timestamp"]); z = algo.last_z_score
        live_tr = [t for t in r.trades if t.timestamp >= start - sec]
        lt = vars(live_tr[-1]) if live_tr else ""
        if bt != last_bar:
            with open(csvp, "a", newline="") as f:
                csv.writer(f).writerow([dt.datetime.now().isoformat(timespec="seconds"), bt, d2[-1]["close"], h2[-1]["close"], z, round(r.final_equity,4), round(r.return_pct,4), len(live_tr), json.dumps(lt) if lt else ""])
            last_bar = bt
        print(json.dumps({"event":"status","bar_ts":bt,"z":z,"equity":r.final_equity,"return_pct":r.return_pct,"trades_since_start":len(live_tr)}), flush=True)
    except Exception as e:
        print(json.dumps({"event":"error","error":repr(e)}), flush=True)
    time.sleep(a.poll_sec)
