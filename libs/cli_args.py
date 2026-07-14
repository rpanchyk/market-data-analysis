"""Shared paths, timeframe tables, and argparse helpers for the pipeline.

Paths (project root = parent of ``libs/``):

- ``ROOT``, ``DATA`` (``data/``), ``RESULTS`` (``results/``)
- ``ohlc_path(symbol, tf)`` -> ``data/{SYMBOL}_{tf}.csv``
- ``trends_path(symbol, tf)`` -> ``data/{SYMBOL}_{tf}_trends_corrections.csv``
- ``report_stem(symbol, tf)`` -> ``{SYMBOL}_{tf}_trends_corrections``
- ``pip_size(symbol)`` -> ``0.01`` for JPY / XAU / XAG quotes, else ``0.0001``

Timeframes: ``TF_RULES`` (canonical -> pandas resample), ``TF_ALIASES``,
``normalize_tf`` / ``normalize_symbol``, default TF ``h1``.

CLI parsing (used by clean / convert / analyze / export / histogram / compare):

- ``parse_symbol(parser)`` — symbol only (positional or ``--symbol``)
- ``parse_symbol_tf(parser)`` — symbol + TF; TF via second positional,
  sole positional after ``--symbol``, or ``--tf`` (default ``h1``;
  ``--symbol`` / ``--tf`` override positionals)
- ``parse_tf(parser)`` — TF only (for ``compare_symbols.py``)
- ``discover_trends_symbols(tf)`` — symbols with existing trends CSV

Example for a pipeline script::

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    symbol, tf, args = parse_symbol_tf(parser)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows consoles are often cp1252; keep CLI help/errors printable.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"

TF_RULES: dict[str, str] = {
    "m5": "5min",
    "m15": "15min",
    "m30": "30min",
    "h1": "1h",
    "h4": "4h",
    "d1": "1D",
    "w1": "1W-MON",
}

TF_ALIASES: dict[str, str] = {
    "5m": "m5",
    "15m": "m15",
    "30m": "m30",
    "1h": "h1",
    "60m": "h1",
    "4h": "h4",
    "240m": "h4",
    "1d": "d1",
    "d": "d1",
    "1w": "w1",
    "w": "w1",
}

DEFAULT_TF = "h1"
DEFAULT_PIP = 0.0001
JPY_PIP = 0.01
METAL_PIP = 0.01  # XAUUSD / XAGUSD typically quoted to 0.01


def pip_size(symbol: str) -> float:
    """Price increment of 1 pip for ``symbol`` (JPY/XAU/XAG quote -> 0.01)."""
    sym = symbol.strip().upper()
    if len(sym) >= 6 and sym[3:6] == "JPY":
        return JPY_PIP
    if sym.endswith("JPY"):
        return JPY_PIP
    if sym.startswith("XAU") or sym.startswith("XAG"):
        return METAL_PIP
    return DEFAULT_PIP


def normalize_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not symbol.isalnum():
        raise argparse.ArgumentTypeError(f"Invalid symbol: {raw!r}")
    return symbol


def normalize_tf(raw: str) -> str:
    key = raw.strip().lower().replace(" ", "")
    if key in TF_RULES:
        return key
    if key in TF_ALIASES:
        return TF_ALIASES[key]
    raise argparse.ArgumentTypeError(
        f"Unknown timeframe {raw!r}. Use one of: {', '.join(TF_RULES)}"
    )


def add_symbol_tf_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach shared SYMBOL/TF positionals and ``--symbol`` / ``--tf`` flags."""
    parser.add_argument(
        "positionals",
        nargs="*",
        help="[SYMBOL] [TF]  - or just [TF] when --symbol is set",
    )
    parser.add_argument(
        "--symbol",
        dest="symbol_opt",
        type=normalize_symbol,
        help="Instrument symbol, e.g. EURUSD or AUDCAD",
    )
    parser.add_argument(
        "--tf",
        dest="tf_opt",
        type=normalize_tf,
        help="Timeframe (default: h1; overrides positional TF if both given)",
    )


def resolve_symbol_tf(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve ``(symbol, tf)`` from args produced by ``add_symbol_tf_arguments``."""
    pos = args.positionals
    if args.symbol_opt:
        symbol = args.symbol_opt
        if len(pos) > 1:
            raise ValueError(
                f"Too many positional args after --symbol: {pos!r} "
                "(expected optional TF only)"
            )
        tf_pos = normalize_tf(pos[0]) if pos else None
    else:
        if not pos:
            raise ValueError(
                "Symbol required: pass it as first argument or --symbol"
            )
        symbol = normalize_symbol(pos[0])
        if len(pos) > 2:
            raise ValueError(
                f"Too many positional args: {pos!r} (expected SYMBOL [TF])"
            )
        tf_pos = normalize_tf(pos[1]) if len(pos) == 2 else None

    tf = args.tf_opt or tf_pos or DEFAULT_TF
    return symbol, tf


def add_symbol_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach symbol-only args (positional or ``--symbol``) for clean_data."""
    parser.add_argument(
        "symbol_pos",
        nargs="?",
        type=normalize_symbol,
        help="Instrument symbol (or use --symbol)",
    )
    parser.add_argument(
        "--symbol",
        dest="symbol_opt",
        type=normalize_symbol,
        help="Instrument symbol, e.g. EURUSD or AUDCAD",
    )


def resolve_symbol(args: argparse.Namespace) -> str:
    """Resolve symbol from args produced by ``add_symbol_arguments``."""
    symbol = args.symbol_opt or args.symbol_pos
    if not symbol:
        raise ValueError("Symbol required: pass it as first argument or --symbol")
    return symbol


def parse_symbol(parser: argparse.ArgumentParser | None = None) -> tuple[str, argparse.Namespace]:
    """Parse argv for symbol-only CLIs; return ``(symbol, namespace)``.

    Extra flags must be added to ``parser`` before calling this.
    """
    p = parser or argparse.ArgumentParser()
    add_symbol_arguments(p)
    args = p.parse_args()
    try:
        symbol = resolve_symbol(args)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
    return symbol, args


def parse_symbol_tf(
    parser: argparse.ArgumentParser | None = None,
) -> tuple[str, str, argparse.Namespace]:
    """Parse argv; return (symbol, tf, full namespace).

    Extra flags must be added to `parser` before calling this.
    """
    p = parser or argparse.ArgumentParser()
    add_symbol_tf_arguments(p)
    args = p.parse_args()
    try:
        symbol, tf = resolve_symbol_tf(args)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
    return symbol, tf, args


def ohlc_path(symbol: str, tf: str) -> Path:
    """``data/{SYMBOL}_{tf}.csv``."""
    return DATA / f"{symbol}_{tf}.csv"


def trends_path(symbol: str, tf: str) -> Path:
    """``data/{SYMBOL}_{tf}_trends_corrections.csv``."""
    return DATA / f"{symbol}_{tf}_trends_corrections.csv"


def report_stem(symbol: str, tf: str) -> str:
    """Basename stem for trends report files (no extension)."""
    return f"{symbol}_{tf}_trends_corrections"


def compare_stem(tf: str) -> str:
    """Basename stem for cross-symbol comparison report."""
    return f"compare_{tf}_correction_coverage"


def discover_trends_symbols(tf: str) -> list[str]:
    """Symbols that already have ``data/{SYMBOL}_{tf}_trends_corrections.csv``."""
    suffix = f"_{tf}_trends_corrections.csv"
    symbols: list[str] = []
    for path in sorted(DATA.glob(f"*{suffix}")):
        if path.name.endswith(suffix):
            symbols.append(path.name[: -len(suffix)])
    return symbols


def parse_tf(parser: argparse.ArgumentParser | None = None) -> tuple[str, argparse.Namespace]:
    """Parse optional TF (positional or ``--tf``, default ``h1``). No symbol required."""
    p = parser or argparse.ArgumentParser()
    p.add_argument(
        "tf_pos",
        nargs="?",
        type=normalize_tf,
        help="Timeframe (default: h1)",
    )
    p.add_argument(
        "--tf",
        dest="tf_opt",
        type=normalize_tf,
        help="Timeframe (overrides positional if both given)",
    )
    args = p.parse_args()
    try:
        tf = args.tf_opt or args.tf_pos or DEFAULT_TF
    except argparse.ArgumentTypeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
    return tf, args
