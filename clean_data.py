"""Strip trailing volume/spread columns from raw M1 CSV.

Reads/writes in place: data/{SYMBOL}_m1.csv

Keeps only the first 6 columns: date,time,open,high,low,close
(drops tick volume, volume, spread, and any other trailing fields).

Run from project root or from anywhere:

    python clean_data.py EURUSD
    python clean_data.py --symbol AUDCAD

Requires: none (stdlib only); PyYAML if using --config
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from pathlib import Path

import libs.cli_args as cli_args
from libs.cli_args import parse_symbol
from libs.config import add_config_argument, load_and_apply

KEEP_COLS = 6  # date, time, open, high, low, close


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    symbol, args = parse_symbol(parser)
    load_and_apply(args.config)

    data = cli_args.DATA
    src = data / f"{symbol}_m1.csv"
    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        sys.exit(1)

    data.mkdir(parents=True, exist_ok=True)
    print(f"Cleaning {src.name}...")

    rows = 0
    cols_in = 0
    with src.open("r", newline="", encoding="utf-8") as fin:
        reader = csv.reader(fin)
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=data,
            prefix=f".{symbol}_m1_",
            suffix=".tmp.csv",
            delete=False,
        ) as fout:
            tmp_path = Path(fout.name)
            writer = csv.writer(fout, lineterminator="\n")
            try:
                for row in reader:
                    if not row:
                        continue
                    if cols_in == 0:
                        cols_in = len(row)
                        if cols_in < KEEP_COLS:
                            raise RuntimeError(
                                f"Expected at least {KEEP_COLS} columns, got {cols_in}"
                            )
                    writer.writerow(row[:KEEP_COLS])
                    rows += 1
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

    tmp_path.replace(src)
    dropped = max(cols_in - KEEP_COLS, 0)
    print(f"Rows: {rows:,}")
    print(f"Columns: {cols_in} -> {KEEP_COLS} (dropped {dropped})")
    print(f"Saved: {src}")


if __name__ == "__main__":
    main()
