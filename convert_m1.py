"""Aggregate M1 OHLC CSV into a higher timeframe.

Reads:  data/{SYMBOL}_m1.csv  (date,time,open,high,low,close - no header)
Writes: data/{SYMBOL}_{tf}.csv  (same format)

Run from project root or from anywhere:

    python convert_m1.py EURUSD
    python convert_m1.py EURUSD h1
    python convert_m1.py --symbol AUDCAD
    python convert_m1.py --symbol AUDCAD m15
    python convert_m1.py EURUSD --tf h4

Supported TF: m5, m15, m30, h1, h4, d1, w1 (default: h1)
Symbol: positional first arg or --symbol (required one of them)

Requires: pandas; PyYAML if using --config
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

import libs.cli_args as cli_args
from libs.cli_args import TF_RULES, ohlc_path, parse_symbol_tf
from libs.config import add_config_argument, load_and_apply


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    symbol, tf, args = parse_symbol_tf(parser)
    load_and_apply(args.config)

    rule = TF_RULES[tf]
    src = cli_args.DATA / f"{symbol}_m1.csv"
    dst = ohlc_path(symbol, tf)

    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        sys.exit(1)

    cli_args.DATA.mkdir(parents=True, exist_ok=True)
    print(f"Reading {src.name}...")
    df = pd.read_csv(
        src,
        header=None,
        names=["date", "time", "open", "high", "low", "close"],
        dtype={
            "date": str,
            "time": str,
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
        },
    )
    print(f"M1 bars: {len(df):,}")
    if df.empty:
        print("Empty M1 file", file=sys.stderr)
        sys.exit(1)

    df["datetime"] = pd.to_datetime(
        df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M"
    )
    df = df.set_index("datetime").sort_index()

    bars = (
        df.resample(rule)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    if bars.empty:
        print("No bars after resampling", file=sys.stderr)
        sys.exit(1)

    out = pd.DataFrame(
        {
            "date": bars.index.strftime("%Y.%m.%d"),
            "time": bars.index.strftime("%H:%M"),
            "open": bars["open"],
            "high": bars["high"],
            "low": bars["low"],
            "close": bars["close"],
        }
    )
    out.to_csv(dst, index=False, header=False, float_format="%.5f")
    print(f"{tf.upper()} bars: {len(out):,}")
    print(f"Saved: {dst}")


if __name__ == "__main__":
    main()
