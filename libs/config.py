"""Load and resolve ``config.yml`` for the pipeline.

CLI explicit values win over per-symbol overrides, which win over ``defaults``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from libs.cli_args import ROOT, normalize_symbol, normalize_tf, pip_size as default_pip_size

DEFAULT_CONFIG_PATH = ROOT / "config.yml"

_DEFAULTS_FALLBACK: dict[str, Any] = {
    "tf": "h1",
    "days": 30,
    "threshold": 100,
    "top": 100,
    "pdf": True,
    "skip_clean": False,
    "skip_convert": False,
    "compare": True,
}


@dataclass(frozen=True)
class SymbolRun:
    """Resolved settings for one pipeline run."""

    symbol: str
    tf: str
    days: int
    threshold: int
    top: int
    pdf: bool
    skip_clean: bool
    skip_convert: bool
    pip_size: float | None  # None -> use libs.cli_args.pip_size(symbol)


@dataclass(frozen=True)
class AppConfig:
    path: Path
    defaults: dict[str, Any]
    symbols: dict[str, dict[str, Any]]
    paths: dict[str, Any]
    compare: dict[str, Any]

    @property
    def data_dir(self) -> Path:
        raw = self.paths.get("data", "data")
        p = Path(raw)
        return p if p.is_absolute() else ROOT / p

    @property
    def results_dir(self) -> Path:
        raw = self.paths.get("results", "results")
        p = Path(raw)
        return p if p.is_absolute() else ROOT / p


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load YAML config; missing file -> in-memory defaults + empty symbols."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.is_absolute():
        cfg_path = (ROOT / cfg_path).resolve()

    raw: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            import yaml
        except ImportError as exc:
            raise SystemExit(
                "PyYAML is required for config.yml. Install: pip install PyYAML"
            ) from exc
        with cfg_path.open(encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            raise SystemExit(f"Invalid config (expected mapping): {cfg_path}")
        raw = loaded
    elif path is not None:
        raise SystemExit(f"Config not found: {cfg_path}")

    defaults = {**_DEFAULTS_FALLBACK, **(raw.get("defaults") or {})}
    symbols_raw = raw.get("symbols") or {}
    if not isinstance(symbols_raw, dict):
        raise SystemExit(f"'symbols' must be a mapping in {cfg_path}")

    symbols: dict[str, dict[str, Any]] = {}
    for key, val in symbols_raw.items():
        sym = normalize_symbol(str(key))
        if val is None:
            val = {}
        if not isinstance(val, dict):
            raise SystemExit(f"symbols.{key} must be a mapping or empty")
        symbols[sym] = dict(val)

    paths = raw.get("paths") or {}
    compare = raw.get("compare") or {}
    if not isinstance(paths, dict) or not isinstance(compare, dict):
        raise SystemExit(f"'paths'/'compare' must be mappings in {cfg_path}")

    return AppConfig(
        path=cfg_path,
        defaults=defaults,
        symbols=symbols,
        paths=paths,
        compare=compare,
    )


def configured_symbols(cfg: AppConfig) -> list[str]:
    """Symbol order from ``symbols:`` section."""
    return list(cfg.symbols.keys())


def _pick(
    key: str,
    cli: Any,
    symbol_over: dict[str, Any],
    defaults: dict[str, Any],
) -> Any:
    if cli is not None:
        return cli
    if key in symbol_over and symbol_over[key] is not None:
        return symbol_over[key]
    return defaults.get(key, _DEFAULTS_FALLBACK.get(key))


def resolve_symbol_run(
    cfg: AppConfig,
    symbol: str,
    *,
    tf: str | None = None,
    days: int | None = None,
    threshold: int | None = None,
    top: int | None = None,
    pdf: bool | None = None,
    skip_clean: bool | None = None,
    skip_convert: bool | None = None,
) -> SymbolRun:
    """Merge defaults + symbols[symbol] + explicit CLI (non-None) overrides."""
    sym = normalize_symbol(symbol)
    over = dict(cfg.symbols.get(sym) or {})
    defaults = cfg.defaults

    tf_val = _pick("tf", tf, over, defaults)
    tf_resolved = normalize_tf(str(tf_val))

    pip_raw = over.get("pip_size", None)
    pip: float | None
    if pip_raw is None:
        pip = None
    else:
        pip = float(pip_raw)

    return SymbolRun(
        symbol=sym,
        tf=tf_resolved,
        days=int(_pick("days", days, over, defaults)),
        threshold=int(_pick("threshold", threshold, over, defaults)),
        top=int(_pick("top", top, over, defaults)),
        pdf=bool(_pick("pdf", pdf, over, defaults)),
        skip_clean=bool(_pick("skip_clean", skip_clean, over, defaults)),
        skip_convert=bool(_pick("skip_convert", skip_convert, over, defaults)),
        pip_size=pip,
    )


def apply_paths(cfg: AppConfig) -> None:
    """Point ``libs.cli_args.DATA`` / ``RESULTS`` at paths from config."""
    import libs.cli_args as cli_args

    cli_args.DATA = cfg.data_dir
    cli_args.RESULTS = cfg.results_dir


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    """Attach ``--config`` pointing at project ``config.yml`` by default."""
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help=f"Path to config.yml (default: {DEFAULT_CONFIG_PATH.name})",
    )


def load_and_apply(path: Path | str | None = None) -> AppConfig:
    """Load config and sync ``DATA`` / ``RESULTS`` paths for this process."""
    cfg = load_config(path)
    apply_paths(cfg)
    return cfg


def resolve_pip_size(symbol: str, override: float | None = None) -> float:
    """Use explicit override, else config ``symbols.*.pip_size``, else heuristic."""
    if override is not None:
        return float(override)
    try:
        cfg = load_config()
        raw = (cfg.symbols.get(normalize_symbol(symbol)) or {}).get("pip_size")
        if raw is not None:
            return float(raw)
    except SystemExit:
        pass
    return default_pip_size(symbol)


def resolve_compare_pdf(cfg: AppConfig, cli_pdf: bool | None) -> bool:
    if cli_pdf is not None:
        return cli_pdf
    if "pdf" in cfg.compare and cfg.compare["pdf"] is not None:
        return bool(cfg.compare["pdf"])
    return bool(cfg.defaults.get("pdf", True))


def should_compare(cfg: AppConfig, cli_compare: bool | None) -> bool:
    if cli_compare is not None:
        return cli_compare
    return bool(cfg.defaults.get("compare", True))
