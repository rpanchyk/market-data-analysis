"""Compare correction coverage across all symbols for one timeframe.

Reads every data/{SYMBOL}_{tf}_trends_corrections.csv found for the TF.
Writes:
  results/compare_{tf}_correction_coverage.csv
  results/compare_{tf}_correction_coverage.html
  results/compare_{tf}_correction_coverage.pdf   (optional)

Run from project root:

    python compare_symbols.py
    python compare_symbols.py h1
    python compare_symbols.py --tf h1 --pdf
    python compare_symbols.py --tf h1 --symbols EURUSD GBPUSD AUDCAD
    python compare_symbols.py --no-pdf

Requires: pandas, plotly, kaleido, matplotlib (for --pdf)
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from libs.charts import bar_fig, chart_section, figures_to_pdf
from libs.cli_args import (
    compare_stem,
    discover_trends_symbols,
    normalize_symbol,
    parse_tf,
    trends_path,
)
from libs.config import add_config_argument, load_and_apply
import libs.cli_args as cli_args


def symbol_stats(symbol: str, df: pd.DataFrame) -> dict:
    mc = df["max_correction_pct"].dropna()
    fc = df["correction_pct"].dropna()
    days = int(df["correction_days"].iloc[0]) if "correction_days" in df.columns else None
    return {
        "symbol": symbol,
        "n_trends": len(df),
        "correction_days": days,
        "zigzag_threshold_pips": (
            int(df["zigzag_threshold_pips"].iloc[0])
            if "zigzag_threshold_pips" in df.columns
            else None
        ),
        "trend_pips_median": round(float(df["trend_pips"].median()), 1),
        "trend_pips_mean": round(float(df["trend_pips"].mean()), 1),
        "first_corr_pct_median": round(float(fc.median()), 1),
        "first_corr_pct_mean": round(float(fc.mean()), 1),
        "max_corr_pct_median": round(float(mc.median()), 1),
        "max_corr_pct_mean": round(float(mc.mean()), 1),
        "gap_to_start_pips_median": round(float(df["gap_to_start_pips"].median()), 1),
        "cover_ge_50_pct": round(100.0 * float((mc >= 50).mean()), 1),
        "cover_ge_80_pct": round(100.0 * float((mc >= 80).mean()), 1),
        "cover_ge_100_pct": round(100.0 * float((mc >= 100).mean()), 1),
        "first_ge_50_pct": round(100.0 * float((fc >= 50).mean()), 1),
        "first_ge_100_pct": round(100.0 * float((fc >= 100).mean()), 1),
        "period_start": str(df["trend_start"].min())[:10],
        "period_end": str(df["trend_end"].max())[:10],
    }


def build_compare_page(
    *,
    title: str,
    subtitle: str,
    winner: str,
    winner_med: float,
    winner_cover: float,
    n_symbols: int,
    table_html: str,
    chart_sections: list[str],
    csv_name: str,
    mixed_warning: str = "",
) -> str:
    charts = "\n".join(chart_sections)
    warn_html = (
        f'<p class="warn"><strong>Увага:</strong> {mixed_warning}</p>'
        if mixed_warning
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <script type="text/javascript">{get_plotlyjs()}</script>
  <style>
    :root {{
      --bg: #f7f6f3;
      --ink: #1c1b19;
      --muted: #5c574f;
      --line: #ddd8ce;
      --card: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.45;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 64px;
    }}
    h1 {{ font-size: 28px; margin: 0 0 6px; font-weight: 650; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      margin: 0 0 18px;
    }}
    .pdf-btn {{
      border: 1px solid var(--line);
      background: var(--card);
      color: var(--ink);
      border-radius: 6px;
      padding: 8px 14px;
      font-size: 13px;
      cursor: pointer;
    }}
    .pdf-btn:hover {{ background: #efece4; }}
    .sub {{ color: var(--muted); font-size: 14px; margin-bottom: 24px; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .stat {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
    }}
    .stat .v {{ font-size: 22px; font-weight: 650; }}
    .stat .l {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
    .notes {{
      color: var(--muted);
      font-size: 14px;
      margin: 0 0 20px;
    }}
    .warn {{
      background: #f7efe3;
      border: 1px solid #e0c993;
      color: #5c4a1f;
      border-radius: 8px;
      padding: 12px 14px;
      font-size: 14px;
      margin: 0 0 20px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 12px 4px;
      margin-bottom: 16px;
    }}
    .chart-title {{
      margin: 0 0 4px;
      padding: 0 4px;
      font-size: 16px;
      font-weight: 650;
      user-select: text;
      cursor: text;
    }}
    table.compare {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    table.compare th, table.compare td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
    }}
    table.compare th {{
      color: var(--muted);
      font-weight: 600;
      font-size: 12px;
    }}
    table.compare tr.winner td {{
      font-weight: 650;
      background: #f0eee8;
    }}
    @media (max-width: 800px) {{
      .stats {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      .toolbar, .modebar, .modebar-container {{ display: none !important; }}
      .card {{
        break-inside: avoid;
        page-break-inside: avoid;
        border-color: #ccc;
      }}
      main {{ max-width: none; padding: 0; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <div class="toolbar">
    <button type="button" class="pdf-btn" id="save-pdf-btn">Зберегти PDF</button>
    <span class="sub" style="margin:0">Відкриє діалог друку - обери «Зберегти як PDF»</span>
  </div>
  <p class="sub">{subtitle}</p>
  {warn_html}
  <div class="stats">
    <div class="stat"><div class="v">{winner}</div><div class="l">Найкраще перекриття</div></div>
    <div class="stat"><div class="v">{winner_med:.0f}%</div><div class="l">Медіана макс. корекції</div></div>
    <div class="stat"><div class="v">{winner_cover:.0f}%</div><div class="l">Трендів з покриттям >=100%</div></div>
    <div class="stat"><div class="v">{n_symbols}</div><div class="l">Символів у порівнянні</div></div>
  </div>
  <p class="notes">
    Перекриття = макс. корекція (% від тренду) за вікном після кінця тренду.
    100% = повернення до старту тренду; &gt;100% = вихід за старт.
    Повні дані: <code>{csv_name}</code> у цій папці.
  </p>
  <section class="card">
    <h2 class="chart-title">Таблиця порівняння (сортування за медіаною макс. корекції %)</h2>
    {table_html}
  </section>
{charts}
</main>
<script>
document.getElementById("save-pdf-btn").addEventListener("click", function () {{
  window.print();
}});
</script>
</body>
</html>
"""


def table_html(cmp: pd.DataFrame) -> str:
    winner = str(cmp.iloc[0]["symbol"])
    cols = [
        ("symbol", "Символ"),
        ("n_trends", "Трендів"),
        ("max_corr_pct_median", "Макс. corr % (мед.)"),
        ("cover_ge_100_pct", ">=100%"),
        ("cover_ge_80_pct", ">=80%"),
        ("first_corr_pct_median", "1-ша corr % (мед.)"),
        ("trend_pips_median", "Тренд pips (мед.)"),
        ("gap_to_start_pips_median", "Gap to start (мед.)"),
        ("period_start", "Від"),
        ("period_end", "До"),
    ]
    head = "".join(f"<th>{label}</th>" for _, label in cols)
    body_rows = []
    for _, row in cmp.iterrows():
        cls = ' class="winner"' if row["symbol"] == winner else ""
        cells = "".join(f"<td>{row[c]}</td>" for c, _ in cols)
        body_rows.append(f"<tr{cls}>{cells}</tr>")
    return (
        f'<table class="compare"><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    parser.add_argument(
        "--symbols",
        nargs="+",
        type=normalize_symbol,
        help="Limit to these symbols (default: all with trends CSV for the TF)",
    )
    parser.add_argument(
        "--pdf",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also write PDF via kaleido/matplotlib (default: on)",
    )
    tf, args = parse_tf(parser)
    load_and_apply(args.config)
    out = cli_args.RESULTS

    out.mkdir(parents=True, exist_ok=True)
    available = discover_trends_symbols(tf)
    if not available:
        print(f"No trends CSVs found for TF={tf} in data/", file=sys.stderr)
        sys.exit(1)

    symbols = args.symbols or available
    missing = [s for s in symbols if s not in available]
    if missing:
        print(
            f"Missing trends CSV for: {', '.join(missing)} (TF={tf})",
            file=sys.stderr,
        )
        sys.exit(1)

    rows = []
    days_set: set[int] = set()
    thr_set: set[int] = set()
    for symbol in symbols:
        src = trends_path(symbol, tf)
        df = pd.read_csv(src)
        stats = symbol_stats(symbol, df)
        if stats["correction_days"] is not None:
            days_set.add(int(stats["correction_days"]))
        if stats.get("zigzag_threshold_pips") is not None:
            thr_set.add(int(stats["zigzag_threshold_pips"]))
        rows.append(stats)

    cmp = (
        pd.DataFrame(rows)
        .sort_values("max_corr_pct_median", ascending=False)
        .reset_index(drop=True)
    )
    cmp.insert(0, "rank", cmp.index + 1)

    stem = compare_stem(tf)
    csv_path = out / f"{stem}.csv"
    cmp.to_csv(csv_path, index=False)
    print(f"Saved CSV: {csv_path}")

    cats = cmp["symbol"].tolist()
    if len(days_set) == 1:
        days_txt = str(next(iter(days_set)))
    elif days_set:
        days_txt = ",".join(str(d) for d in sorted(days_set))
    else:
        days_txt = "?"
    if len(thr_set) == 1:
        thr_txt = str(next(iter(thr_set)))
    elif thr_set:
        thr_txt = ",".join(str(t) for t in sorted(thr_set))
    else:
        thr_txt = "100"
    winner = str(cmp.iloc[0]["symbol"])
    winner_med = float(cmp.iloc[0]["max_corr_pct_median"])
    winner_cover = float(cmp.iloc[0]["cover_ge_100_pct"])

    mixed_parts: list[str] = []
    if len(thr_set) > 1:
        mixed_parts.append(
            f"різні ZigZag threshold: {', '.join(str(t) for t in sorted(thr_set))} pips"
        )
    if len(days_set) > 1:
        mixed_parts.append(
            f"різні correction_days: {', '.join(str(d) for d in sorted(days_set))}"
        )
    mixed_warning = ""
    if mixed_parts:
        mixed_warning = (
            "Порівняння змішує когорти з "
            + "; ".join(mixed_parts)
            + ". Рейтинг за % корекції орієнтовний — абсолютні pips між символами "
            "з різним порогом непорівнянні."
        )
        print(f"WARNING: {mixed_warning}", file=sys.stderr)

    charts_spec: list[tuple[str, go.Figure]] = [
        (
            "Медіана макс. корекції (% від тренду)",
            bar_fig(
                cats,
                [("Макс. корекція % (медіана)", [float(x) for x in cmp.max_corr_pct_median])],
                xlabel="Символ",
                ylabel="% від тренду",
                height=400,
            ),
        ),
        (
            "Частка трендів з покриттям >=100% / >=80%",
            bar_fig(
                cats,
                [
                    (">=100%", [float(x) for x in cmp.cover_ge_100_pct]),
                    (">=80%", [float(x) for x in cmp.cover_ge_80_pct]),
                ],
                xlabel="Символ",
                ylabel="% трендів",
                height=400,
            ),
        ),
        (
            "Медіана першої ZigZag-корекції (% від тренду)",
            bar_fig(
                cats,
                [("Перша корекція % (медіана)", [float(x) for x in cmp.first_corr_pct_median])],
                xlabel="Символ",
                ylabel="% від тренду",
                height=400,
            ),
        ),
        (
            "Медіана розміру тренду (pips)",
            bar_fig(
                cats,
                [("Тренд pips (медіана)", [float(x) for x in cmp.trend_pips_median])],
                xlabel="Символ",
                ylabel="pips",
                height=400,
            ),
        ),
        (
            "Кількість трендів",
            bar_fig(
                cats,
                [("Трендів", [float(x) for x in cmp.n_trends])],
                xlabel="Символ",
                ylabel="Кількість",
                height=400,
            ),
        ),
    ]

    title = f"Порівняння символів - перекриття корекцією ({tf.upper()})"
    subtitle = (
        f"ZigZag >={thr_txt} pips · макс. корекція за {days_txt} днів · "
        f"{len(symbols)} символів · лідер: {winner}"
    )

    html = build_compare_page(
        title=title,
        subtitle=subtitle,
        winner=winner,
        winner_med=winner_med,
        winner_cover=winner_cover,
        n_symbols=len(symbols),
        table_html=table_html(cmp),
        chart_sections=[
            chart_section(t, fig, f"cmp-{i}") for i, (t, fig) in enumerate(charts_spec)
        ],
        csv_name=csv_path.name,
        mixed_warning=mixed_warning,
    )
    html_path = out / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"Saved HTML: {html_path}")
    print(f"Winner: {winner} (median max corr {winner_med}%, cover>=100% {winner_cover}%)")

    if args.pdf:
        pdf_path = out / f"{stem}.pdf"
        try:
            figures_to_pdf(
                pdf_path,
                title=title,
                subtitle=(
                    subtitle
                    + ("\n\nWARNING: " + mixed_warning if mixed_warning else "")
                ),
                stats=[
                    ("Найкраще перекриття", winner),
                    ("Медіана макс. корекції", f"{winner_med:.0f}%"),
                    ("Покриття >=100%", f"{winner_cover:.0f}%"),
                    ("Символів", str(len(symbols))),
                ],
                charts=charts_spec,
            )
            size_mb = pdf_path.stat().st_size / (1024 * 1024)
            print(f"Saved PDF: {pdf_path} ({size_mb:.1f} MB)")
        except Exception as exc:
            print(f"PDF skip: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
