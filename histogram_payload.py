"""Print histogram / top-N payload used for the trends canvas charts.

Reads: data/{SYMBOL}_{tf}_trends_corrections.csv
Prints JSON to stdout (histogram bins + top-N series including max correction).

Run from project root:

    python histogram_payload.py EURUSD
    python histogram_payload.py EURUSD h1 --top 50
    python histogram_payload.py --symbol AUDCAD --tf h1 --top 100
    python histogram_payload.py EURUSD --top 100 -o payload.json

Requires: pandas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from libs.cli_args import parse_symbol_tf, trends_path


def pip_hist(series: pd.Series, edges: list[int], labels: list[str]) -> list[int]:
    return (
        pd.cut(series.dropna(), bins=edges, right=False, labels=labels)
        .value_counts()
        .reindex(labels)
        .fillna(0)
        .astype(int)
        .tolist()
    )


def histogram_payload(df: pd.DataFrame) -> dict:
    if "zigzag_threshold_pips" in df.columns:
        bin_start = max(int(df["zigzag_threshold_pips"].iloc[0]), 50)
    else:
        bin_start = 100
    edges = list(range(bin_start, bin_start + 851, 50)) + [10000]
    labels = [
        f"{a}+" if b >= 10000 else f"{a}-{b}"
        for a, b in zip(edges[:-1], edges[1:])
    ]

    pct_edges = list(range(0, 201, 20)) + [10000]
    pct_labels = [
        f"{a}+" if b >= 10000 else f"{a}-{b}"
        for a, b in zip(pct_edges[:-1], pct_edges[1:])
    ]

    days = int(df["correction_days"].iloc[0]) if "correction_days" in df.columns else None

    return {
        "pip_cats": labels,
        "trend_counts": pip_hist(df["trend_pips"], edges, labels),
        "corr_counts": pip_hist(df["correction_pips"], edges, labels),
        "max_correction_counts": pip_hist(df["max_correction_pips"], edges, labels),
        "pct_cats": pct_labels,
        "first_pct_counts": pip_hist(df["correction_pct"], pct_edges, pct_labels),
        "max_correction_pct_counts": pip_hist(df["max_correction_pct"], pct_edges, pct_labels),
        "stats": {
            "n": int(len(df)),
            "days": days,
            "trend_mean": round(float(df.trend_pips.mean()), 1),
            "trend_median": round(float(df.trend_pips.median()), 1),
            "trend_max": round(float(df.trend_pips.max()), 1),
            "corr_median": round(float(df.correction_pips.median()), 1),
            "max_correction_median": round(float(df.max_correction_pips.median()), 1),
            "max_correction_pct_median": round(float(df.max_correction_pct.median()), 1),
        },
    }


def top_n_payload(df: pd.DataFrame, n: int) -> dict:
    top = df.head(n)
    labels = []
    for r in top.itertuples():
        arrow = "↑" if r.direction == "up" else "↓"
        start = r.trend_start[:10]
        end = r.trend_end[:10]
        labels.append(f"{start}->{end} {arrow}")
    return {
        "labels": labels,
        "trend": [round(float(x), 1) for x in top.trend_pips],
        "corr": [round(float(x), 1) for x in top.correction_pips],
        "max_correction": [round(float(x), 1) for x in top.max_correction_pips],
        "trend_start": [r.trend_start for r in top.itertuples()],
        "trend_end": [r.trend_end for r in top.itertuples()],
        "correction_start": [r.correction_start for r in top.itertuples()],
        "correction_end": [r.correction_end for r in top.itertuples()],
        "max_correction_start": [r.max_correction_start for r in top.itertuples()],
        "max_correction_end": [r.max_correction_end for r in top.itertuples()],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--top",
        type=int,
        default=100,
        help="How many largest trends to include (default: 100)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write JSON to this file (UTF-8) instead of stdout",
    )
    symbol, tf, args = parse_symbol_tf(parser)
    src = trends_path(symbol, tf)
    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(src)
    if df.empty:
        print(f"Empty trends file: {src}", file=sys.stderr)
        sys.exit(1)
    payload = {
        "histogram": histogram_payload(df),
        "top": top_n_payload(df, args.top),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
