"""Lightweight data/report integrity checks for production readiness.

    python verify_data.py
    python verify_data.py --tf h1
    python verify_data.py --config config.yml --tf h1

Exit code 0 = OK, 1 = problems found.
"""

from __future__ import annotations

import argparse
import csv
import sys

import pandas as pd

import libs.cli_args as cli_args
from libs.cli_args import (
    compare_stem,
    discover_trends_symbols,
    parse_tf,
    pip_size,
)
from libs.config import (
    add_config_argument,
    configured_symbols,
    load_and_apply,
    resolve_symbol_run,
)


REQUIRED_TREND_COLS = {
    "trend_rank",
    "direction",
    "trend_pips",
    "trend_start",
    "trend_end",
    "trend_bars",
    "correction_days",
    "zigzag_threshold_pips",
    "max_correction_pips",
    "max_correction_pct",
    "gap_to_start_pips",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    tf, args = parse_tf(parser)
    cfg = load_and_apply(args.config)

    data = cli_args.DATA
    results = cli_args.RESULTS
    require_pdf = bool(cfg.defaults.get("pdf", True))
    require_compare_pdf = (
        bool(cfg.compare["pdf"])
        if "pdf" in cfg.compare and cfg.compare["pdf"] is not None
        else require_pdf
    )

    issues: list[str] = []
    configured = configured_symbols(cfg)
    discovered = discover_trends_symbols(tf)
    symbols = configured or discovered
    if configured:
        missing_cfg = [s for s in configured if s not in discovered]
        for s in missing_cfg:
            issues.append(f"{s}: in config.yml but missing trends CSV for TF={tf}")
        # Also check extras on disk not in config (info only via print)
        extras = [s for s in discovered if s not in configured]
        if extras:
            print(f"Note: trends on disk not in config: {', '.join(extras)}")

    if not symbols:
        issues.append(f"No symbols to verify for TF={tf}")
    else:
        print(f"TF={tf} symbols: {', '.join(symbols)}")

    for symbol in symbols:
        m1 = data / f"{symbol}_m1.csv"
        ohlc = data / f"{symbol}_{tf}.csv"
        trends = data / f"{symbol}_{tf}_trends_corrections.csv"
        expected = [
            ("m1", m1),
            ("ohlc", ohlc),
            ("trends", trends),
            ("html", results / f"{symbol}_{tf}_trends_corrections.html"),
            ("rcsv", results / f"{symbol}_{tf}_trends_corrections.csv"),
        ]
        if require_pdf:
            expected.append(("pdf", results / f"{symbol}_{tf}_trends_corrections.pdf"))
        for label, path in expected:
            if not path.exists():
                issues.append(f"{symbol}: missing {label} ({path.name})")

        if m1.exists():
            with m1.open(newline="", encoding="utf-8") as fin:
                row = next(csv.reader(fin), None)
            if not row or len(row) != 6:
                issues.append(
                    f"{symbol}: m1 expected 6 cols, got {0 if not row else len(row)}"
                )

        if not trends.exists():
            continue
        df = pd.read_csv(trends)
        missing = REQUIRED_TREND_COLS - set(df.columns)
        if missing:
            issues.append(f"{symbol}: missing columns {sorted(missing)}")
        if df.empty:
            issues.append(f"{symbol}: empty trends CSV")
        if "trend_bars" in df.columns and int((df["trend_bars"] < 0).sum()) > 0:
            issues.append(
                f"{symbol}: {(df['trend_bars'] < 0).sum()} rows with negative trend_bars"
            )
        if "zigzag_threshold_pips" in df.columns and symbol in cfg.symbols:
            expected_thr = resolve_symbol_run(cfg, symbol, tf=tf).threshold
            actual_thr = int(df["zigzag_threshold_pips"].iloc[0])
            if actual_thr != expected_thr:
                issues.append(
                    f"{symbol}: zigzag_threshold_pips={actual_thr} "
                    f"!= config threshold={expected_thr}"
                )

        if "trend_pips" in df.columns and not df.empty:
            max_trend = float(df["trend_pips"].max())
            print(
                f"  {symbol}: n={len(df)} pip={pip_size(symbol)} max_trend={max_trend:.1f}"
            )
        else:
            print(f"  {symbol}: n={len(df)} (no trend_pips)")

    stem = compare_stem(tf)
    for ext in (".csv", ".html"):
        path = results / f"{stem}{ext}"
        if not path.exists():
            issues.append(f"missing compare report {path.name}")
    if require_compare_pdf:
        path = results / f"{stem}.pdf"
        if not path.exists():
            issues.append(f"missing compare report {path.name}")

    cmp_csv = results / f"{stem}.csv"
    if cmp_csv.exists() and discovered:
        cmp = pd.read_csv(cmp_csv)
        check_set = set(configured) if configured else set(discovered)
        if set(cmp["symbol"]) != check_set and set(cmp["symbol"]) != set(discovered):
            # Allow compare of subset (configured) or full disk discovery
            if configured and set(cmp["symbol"]) != set(configured):
                issues.append(
                    f"compare CSV symbols {sorted(cmp['symbol'])} "
                    f"!= config {configured}"
                )

    if issues:
        print("FAIL")
        for item in issues:
            print(f" - {item}")
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
