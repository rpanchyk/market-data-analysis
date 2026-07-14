"""Detect ZigZag swings and save trend/correction pairs in pips.

Reads:  data/{SYMBOL}_{tf}.csv
Writes: data/{SYMBOL}_{tf}_trends_corrections.csv  (sorted by trend_pips desc)

For each trend (ZigZag leg A->B) two corrections are measured:

1. first_correction - next ZigZag leg B->C (first opposite swing)
   dates: correction_start (= trend_end), correction_end
2. max_correction (Max correction / макс. корекція) - deepest move back
   toward trend start A within CORRECTION_DAYS calendar days after B
   (parameter, default 30)
   dates: max_correction_start (= trend_end), max_correction_end

Trend dates: trend_start, trend_end

Run from project root or from anywhere:

    python analyze_trends_corrections.py EURUSD
    python analyze_trends_corrections.py EURUSD h1
    python analyze_trends_corrections.py --symbol AUDCAD --tf h1
    python analyze_trends_corrections.py EURUSD --days 30 --threshold 100

Requires: pandas, numpy
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from libs.cli_args import ohlc_path, parse_symbol_tf, trends_path
from libs.config import add_config_argument, load_and_apply, resolve_pip_size, resolve_symbol_run
import libs.cli_args as cli_args


def zigzag_pivots(
    high: np.ndarray, low: np.ndarray, thr: float
) -> list[tuple[int, float, str]]:
    """Return confirmed ZigZag pivots as (index, price, 'H'|'L') in time order.

    Confirmation of a candidate extreme only happens on bars *after* that
    extreme (classic ZigZag). Starting the scan before the candidate caused
    reverse legs with earlier indices (negative trend_bars).
    """
    n = len(high)
    pivots: list[tuple[int, float, str]] = []

    ext_i, ext_price = 0, high[0]
    low_i, low_p = 0, low[0]

    for i in range(1, n):
        if high[i] >= ext_price:
            ext_price, ext_i = high[i], i
        if low[i] <= low_p:
            low_p, low_i = low[i], i
        if ext_price - low_p < thr:
            continue
        if ext_i > low_i:
            pivots.append((low_i, low_p, "L"))
            mode = "up"
            cand_i, cand_p = ext_i, high[ext_i]
        else:
            pivots.append((ext_i, ext_price, "H"))
            mode = "down"
            cand_i, cand_p = low_i, low[low_i]
        break
    else:
        raise RuntimeError("No initial swing found")

    # Scan only after the first candidate extreme so confirmation is in the future
    for i in range(cand_i + 1, n):
        if mode == "up":
            if high[i] >= cand_p:
                cand_p, cand_i = high[i], i
            elif cand_p - low[i] >= thr:
                pivots.append((cand_i, cand_p, "H"))
                mode = "down"
                cand_i, cand_p = i, low[i]
        else:
            if low[i] <= cand_p:
                cand_p, cand_i = low[i], i
            elif high[i] - cand_p >= thr:
                pivots.append((cand_i, cand_p, "L"))
                mode = "up"
                cand_i, cand_p = i, high[i]

    return pivots


def max_correction_to_start(
    df: pd.DataFrame,
    *,
    trend_end_i: int,
    start_price: float,
    end_price: float,
    direction: str,
    days: int,
    pip: float,
) -> dict:
    """Deepest move back toward trend start within `days` after trend end.

    For an uptrend, uses the lowest low in the window.
    For a downtrend, uses the highest high in the window.
    """
    end_dt = df.at[trend_end_i, "dt"]
    window_end = end_dt + pd.Timedelta(days=days)
    # bars strictly after trend end, within calendar window
    sl = df.iloc[trend_end_i + 1 :]
    sl = sl.loc[sl["dt"] <= window_end]
    if sl.empty:
        return {
            "max_correction_pips": np.nan,
            "max_correction_pct": np.nan,
            "gap_to_start_pips": np.nan,
            "max_correction_time": "",
            "max_correction_price": np.nan,
            "max_correction_bars": 0,
        }

    trend_pips = abs(end_price - start_price) / pip
    if direction == "up":
        idx = sl["low"].idxmin()
        extreme = float(sl.at[idx, "low"])
        approach = end_price - extreme  # toward lower start
    else:
        idx = sl["high"].idxmax()
        extreme = float(sl.at[idx, "high"])
        approach = extreme - end_price  # toward higher start

    approach = max(approach, 0.0)
    approach_pips = approach / pip
    gap_to_start = abs(extreme - start_price) / pip

    return {
        "max_correction_pips": round(approach_pips, 1),
        "max_correction_pct": round(100.0 * approach_pips / trend_pips, 1)
        if trend_pips
        else np.nan,
        "gap_to_start_pips": round(gap_to_start, 1),
        "max_correction_time": df.at[idx, "dt"].strftime("%Y.%m.%d %H:%M"),
        "max_correction_price": round(extreme, 5),
        "max_correction_bars": int(idx - trend_end_i),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Calendar days after trend end to search max correction (default: from config.yml)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="ZigZag minimum swing size in pips (default: from config.yml)",
    )
    parser.add_argument(
        "--pip-size",
        type=float,
        default=None,
        help="Override pip size (default: config symbols.*.pip_size or heuristic)",
    )
    add_config_argument(parser)
    symbol, tf, args = parse_symbol_tf(parser)
    cfg = load_and_apply(args.config)
    # TF already resolved by CLI (default h1); still apply symbol threshold/days/pip.
    run = resolve_symbol_run(
        cfg,
        symbol,
        tf=tf,
        days=args.days,
        threshold=args.threshold,
    )
    days = run.days
    threshold_pips = run.threshold
    pip = resolve_pip_size(symbol, args.pip_size if args.pip_size is not None else run.pip_size)

    src = ohlc_path(symbol, tf)
    dst = trends_path(symbol, tf)
    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        sys.exit(1)

    cli_args.DATA.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(
        src, header=None, names=["date", "time", "open", "high", "low", "close"]
    )
    if df.empty:
        print(f"Empty OHLC file: {src}", file=sys.stderr)
        sys.exit(1)
    df["dt"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M")

    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    thr = threshold_pips * pip
    try:
        pivots = zigzag_pivots(high, low, thr)
    except RuntimeError as exc:
        print(f"{symbol} {tf}: {exc} (threshold={threshold_pips} pips)", file=sys.stderr)
        sys.exit(1)
    if len(pivots) < 2:
        print(
            f"{symbol} {tf}: not enough ZigZag pivots ({len(pivots)}) "
            f"for threshold={threshold_pips} pips",
            file=sys.stderr,
        )
        sys.exit(1)

    rows = []
    # Every confirmed leg A->B; first correction needs B->C
    for k in range(len(pivots) - 1):
        a_i, a_p, _ = pivots[k]
        b_i, b_p, _ = pivots[k + 1]
        if b_i <= a_i:
            continue

        trend_pips = abs(b_p - a_p) / pip
        direction = "up" if b_p > a_p else "down"

        trend_start = df.at[a_i, "dt"].strftime("%Y.%m.%d %H:%M")
        trend_end = df.at[b_i, "dt"].strftime("%Y.%m.%d %H:%M")

        if k + 2 < len(pivots):
            c_i, c_p, _ = pivots[k + 2]
            if c_i <= b_i:
                first_pips = first_pct = np.nan
                corr_start = corr_end = ""
                first_end_price = np.nan
                first_bars = 0
            else:
                first_pips = abs(c_p - b_p) / pip
                first_pct = 100.0 * first_pips / trend_pips if trend_pips else np.nan
                corr_start = trend_end
                corr_end = df.at[c_i, "dt"].strftime("%Y.%m.%d %H:%M")
                first_end_price = round(c_p, 5)
                first_bars = int(c_i - b_i)
        else:
            first_pips = first_pct = np.nan
            corr_start = corr_end = ""
            first_end_price = np.nan
            first_bars = 0

        approach = max_correction_to_start(
            df,
            trend_end_i=b_i,
            start_price=a_p,
            end_price=b_p,
            direction=direction,
            days=days,
            pip=pip,
        )

        rows.append(
            {
                "trend_rank": 0,
                "direction": direction,
                "trend_pips": round(trend_pips, 1),
                "trend_start": trend_start,
                "trend_end": trend_end,
                "trend_start_price": round(a_p, 5),
                "trend_end_price": round(b_p, 5),
                "trend_bars": int(b_i - a_i),
                "correction_pips": round(first_pips, 1)
                if not np.isnan(first_pips)
                else np.nan,
                "correction_pct": round(first_pct, 1)
                if not np.isnan(first_pct)
                else np.nan,
                "correction_start": corr_start,
                "correction_end": corr_end,
                "correction_end_price": first_end_price,
                "correction_bars": first_bars,
                "correction_days": days,
                "zigzag_threshold_pips": threshold_pips,
                "max_correction_pips": approach["max_correction_pips"],
                "max_correction_pct": approach["max_correction_pct"],
                "gap_to_start_pips": approach["gap_to_start_pips"],
                "max_correction_start": trend_end if approach["max_correction_time"] else "",
                "max_correction_end": approach["max_correction_time"],
                "max_correction_price": approach["max_correction_price"],
                "max_correction_bars": approach["max_correction_bars"],
            }
        )

    out = (
        pd.DataFrame(rows)
        .sort_values("trend_pips", ascending=False)
        .reset_index(drop=True)
    )
    if out.empty:
        print("No chronological ZigZag trends found", file=sys.stderr)
        sys.exit(1)
    out["trend_rank"] = out.index + 1
    out.to_csv(dst, index=False)

    print(f"Symbol: {symbol}  TF: {tf}")
    print(f"Pip size: {pip}")
    print(f"Threshold: {threshold_pips} pips")
    print(f"Max-correction window: {days} days")
    print(f"Pivots: {len(pivots)}")
    print(f"Trend rows: {len(out)}")
    print(f"Saved: {dst}")
    print()
    cols = [
        "trend_rank",
        "direction",
        "trend_pips",
        "trend_start",
        "trend_end",
        "correction_pips",
        "correction_start",
        "correction_end",
        "max_correction_pips",
        "max_correction_start",
        "max_correction_end",
    ]
    print(out[cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
