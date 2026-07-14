"""Run the full per-symbol pipeline (clean -> convert -> analyze -> export).

Reads ``config.yml`` for defaults and per-symbol overrides (e.g. XAUUSD threshold).
Explicit CLI flags override the config.

    python run_pipeline.py --all
    python run_pipeline.py EURUSD
    python run_pipeline.py EURUSD h1
    python run_pipeline.py --symbol USDJPY --tf h1 --pdf
    python run_pipeline.py GBPUSD --compare
    python run_pipeline.py XAUUSD          # threshold from config (2000)
    python run_pipeline.py --config path/to/config.yml --all --no-pdf

Requires the same packages as the individual pipeline scripts, plus PyYAML.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from libs.cli_args import (
    ROOT,
    add_symbol_tf_arguments,
    normalize_symbol,
    normalize_tf,
    resolve_symbol_tf,
)
from libs.config import (
    add_config_argument,
    load_and_apply,
    configured_symbols,
    resolve_compare_pdf,
    resolve_symbol_run,
    should_compare,
)


def run_step(args: list[str]) -> None:
    print("+", " ".join(args), flush=True)
    proc = subprocess.run(args, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def cfg_flag(config_path: Path) -> list[str]:
    return ["--config", str(config_path)]


def run_one(settings, py: str, config_path: Path) -> None:
    symbol = settings.symbol
    tf = settings.tf
    conf = cfg_flag(config_path)

    if not settings.skip_clean:
        run_step([py, str(ROOT / "clean_data.py"), "--symbol", symbol, *conf])
    if not settings.skip_convert:
        run_step(
            [py, str(ROOT / "convert_m1.py"), "--symbol", symbol, "--tf", tf, *conf]
        )

    analyze = [
        py,
        str(ROOT / "analyze_trends_corrections.py"),
        "--symbol",
        symbol,
        "--tf",
        tf,
        "--days",
        str(settings.days),
        "--threshold",
        str(settings.threshold),
        *conf,
    ]
    if settings.pip_size is not None:
        analyze.extend(["--pip-size", str(settings.pip_size)])
    run_step(analyze)

    export_cmd = [
        py,
        str(ROOT / "export_presentation.py"),
        "--symbol",
        symbol,
        "--tf",
        tf,
        "--top",
        str(settings.top),
        "--pdf" if settings.pdf else "--no-pdf",
        *conf,
    ]
    run_step(export_cmd)
    print(f"Pipeline done: {symbol} {tf} (threshold={settings.threshold})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every symbol listed under symbols: in config.yml",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Max-correction window in calendar days (overrides config)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=None,
        help="ZigZag minimum swing size in pips (overrides config)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Top-N chart in export (overrides config)",
    )
    parser.add_argument(
        "--pdf",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Write PDF in export/compare (overrides config)",
    )
    parser.add_argument(
        "--skip-clean",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Skip clean_data.py (overrides config)",
    )
    parser.add_argument(
        "--skip-convert",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Skip convert_m1.py (overrides config)",
    )
    parser.add_argument(
        "--compare",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Refresh compare_symbols.py after runs (overrides config)",
    )
    add_symbol_tf_arguments(parser)
    args = parser.parse_args()

    cfg = load_and_apply(args.config)
    config_path = cfg.path

    symbols: list[str] = []
    tf_cli: str | None = args.tf_opt
    if args.all:
        symbols = configured_symbols(cfg)
        if not symbols:
            print("No symbols in config.yml under 'symbols:'", file=sys.stderr)
            raise SystemExit(2)
        if args.positionals:
            if len(args.positionals) == 1 and not args.symbol_opt:
                try:
                    tf_cli = normalize_tf(args.positionals[0])
                except Exception:
                    print(
                        "--all does not take a symbol; use TF via --tf or alone",
                        file=sys.stderr,
                    )
                    raise SystemExit(2)
            elif args.positionals:
                print("Do not pass SYMBOL with --all", file=sys.stderr)
                raise SystemExit(2)
        if args.symbol_opt:
            print("Do not pass --symbol with --all", file=sys.stderr)
            raise SystemExit(2)
    else:
        try:
            symbol, tf_from_cli = resolve_symbol_tf(args)
        except (ValueError, argparse.ArgumentTypeError) as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(2)
        symbols = [symbol]
        if args.tf_opt or (args.symbol_opt and args.positionals) or (
            not args.symbol_opt and len(args.positionals) == 2
        ):
            tf_cli = tf_from_cli
        else:
            tf_cli = args.tf_opt

    py = sys.executable
    last_tf = None
    for sym in symbols:
        settings = resolve_symbol_run(
            cfg,
            sym,
            tf=tf_cli,
            days=args.days,
            threshold=args.threshold,
            top=args.top,
            pdf=args.pdf,
            skip_clean=args.skip_clean,
            skip_convert=args.skip_convert,
        )
        print(
            f"=== {settings.symbol} {settings.tf} "
            f"threshold={settings.threshold} days={settings.days} ===",
            flush=True,
        )
        run_one(settings, py, config_path)
        last_tf = settings.tf

    do_compare = should_compare(cfg, args.compare)
    if do_compare and last_tf:
        cmp_pdf = resolve_compare_pdf(cfg, args.pdf)
        cmp_cmd = [
            py,
            str(ROOT / "compare_symbols.py"),
            "--tf",
            last_tf,
            *cfg_flag(config_path),
        ]
        cmp_symbols = cfg.compare.get("symbols")
        if isinstance(cmp_symbols, list) and cmp_symbols:
            cmp_cmd.append("--symbols")
            cmp_cmd.extend(normalize_symbol(str(s)) for s in cmp_symbols)
        elif args.all and cfg.symbols:
            cmp_cmd.append("--symbols")
            cmp_cmd.extend(configured_symbols(cfg))
        cmp_cmd.append("--pdf" if cmp_pdf else "--no-pdf")
        run_step(cmp_cmd)

    print(f"All done ({len(symbols)} symbol(s))")


if __name__ == "__main__":
    main()
