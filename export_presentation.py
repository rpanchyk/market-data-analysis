"""Export interactive trends/corrections report into results/.

Reads: data/{SYMBOL}_{tf}_trends_corrections.csv
Writes:
  results/{SYMBOL}_{tf}_trends_corrections.html  (Plotly, hover tooltips)
  results/{SYMBOL}_{tf}_trends_corrections.pdf   (optional, via kaleido)
  results/{SYMBOL}_{tf}_trends_corrections.csv   (copy)

Run from project root or from anywhere:

    python export_presentation.py EURUSD
    python export_presentation.py EURUSD h1
    python export_presentation.py --symbol AUDCAD --tf h1
    python export_presentation.py EURUSD --top 100 --pdf
    python export_presentation.py --symbol EURUSD --no-pdf

In the HTML: кнопка «Зберегти PDF» відкриває діалог друку браузера
(обери «Зберегти як PDF»).

Requires: pandas, plotly, kaleido, matplotlib (for --pdf)
"""

from __future__ import annotations

import argparse
import shutil
import sys

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from libs.charts import bar_fig, chart_section, figures_to_pdf, pip_hist
from libs.cli_args import parse_symbol_tf, report_stem, trends_path
from libs.config import add_config_argument, load_and_apply
import libs.cli_args as cli_args


def build_page(
    *,
    title: str,
    csv_name: str,
    period: str,
    days: int,
    threshold: int,
    n: int,
    trend_median: float,
    approach_median: float,
    approach_pct_median: float,
    chart_sections: list[str],
) -> str:
    charts = "\n".join(chart_sections)
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
  <p class="sub">
    ZigZag >={threshold} pips · макс. корекція за {days} днів · {period} · {n:,} трендів
    · наведіть курсор на стовпчик для підказки · назву графіка можна виділити й скопіювати
  </p>
  <div class="stats">
    <div class="stat"><div class="v">{n:,}</div><div class="l">Трендів</div></div>
    <div class="stat"><div class="v">{trend_median}</div><div class="l">Медіана тренду (pips)</div></div>
    <div class="stat"><div class="v">{approach_median}</div><div class="l">Медіана макс. корекції (pips)</div></div>
    <div class="stat"><div class="v">{approach_pct_median:.0f}%</div><div class="l">Медіана макс. корекції %</div></div>
  </div>
  <p class="notes">
    Перша корекція - наступний ZigZag-леґ. Макс. корекція (Max correction) - найбільше
    наближення до початку тренду протягом {days} календарних днів після кінця тренду.
    Повні дати: <code>{csv_name}</code> у цій папці.
  </p>
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_argument(parser)
    parser.add_argument("--top", type=int, default=100, help="Top-N trends chart")
    parser.add_argument(
        "--pdf",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Also write PDF via kaleido/matplotlib (default: on)",
    )
    symbol, tf, args = parse_symbol_tf(parser)
    load_and_apply(args.config)
    out = cli_args.RESULTS
    stem = report_stem(symbol, tf)
    src = trends_path(symbol, tf)
    title = f"{symbol} {tf.upper()} - тренди та корекції"

    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        sys.exit(1)

    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(src)
    if df.empty:
        print(f"Empty trends file: {src}", file=sys.stderr)
        sys.exit(1)
    days = int(df["correction_days"].iloc[0])
    if "zigzag_threshold_pips" in df.columns:
        threshold = int(df["zigzag_threshold_pips"].iloc[0])
    else:
        threshold = 100
    shutil.copy2(src, out / src.name)

    period = f"{str(df['trend_start'].min())[:7]}-{str(df['trend_end'].max())[:7]}"

    bin_start = max(int(threshold), 50)
    edges = list(range(bin_start, bin_start + 851, 50)) + [10000]
    pip_cats = [
        f"{a}+" if b >= 10000 else f"{a}-{b}"
        for a, b in zip(edges[:-1], edges[1:])
    ]
    pct_edges = list(range(0, 201, 20)) + [10000]
    pct_cats = [
        f"{a}+" if b >= 10000 else f"{a}-{b}"
        for a, b in zip(pct_edges[:-1], pct_edges[1:])
    ]

    trend_counts = pip_hist(df["trend_pips"], edges, pip_cats)
    corr_counts = pip_hist(df["correction_pips"], edges, pip_cats)
    approach_counts = pip_hist(df["max_correction_pips"], edges, pip_cats)
    first_pct = pip_hist(df["correction_pct"], pct_edges, pct_cats)
    approach_pct = pip_hist(df["max_correction_pct"], pct_edges, pct_cats)

    top = df.head(args.top)
    labels = []
    hover_trend = []
    for r in top.itertuples():
        arrow = "↑" if r.direction == "up" else "↓"
        labels.append(f"{r.trend_start[:10]}->{r.trend_end[5:10]} {arrow}")
        hover_trend.append(
            "<br>".join(
                [
                    f"<b>Тренд {arrow}</b>",
                    f"start: {r.trend_start}",
                    f"end: {r.trend_end}",
                    f"trend: {r.trend_pips} pips",
                    f"1st corr: {r.correction_pips} pips"
                    f" ({r.correction_start} -> {r.correction_end})",
                    f"макс. корекція {days}д: {r.max_correction_pips} pips"
                    f" ({r.max_correction_start} -> {r.max_correction_end})",
                    f"gap to start: {r.gap_to_start_pips} pips",
                ]
            )
        )

    # Top chart with richer hover (same customdata for all series)
    top_fig = go.Figure()
    series_top = [
        ("Тренд", [round(float(x), 1) for x in top.trend_pips]),
        ("Перша корекція", [round(float(x), 1) for x in top.correction_pips]),
        (
            f"Макс. корекція {days}д",
            [round(float(x), 1) for x in top.max_correction_pips],
        ),
    ]
    for name, values in series_top:
        custom = [
            f"{h}<br><b>{name}:</b> {val} pips" for h, val in zip(hover_trend, values)
        ]
        top_fig.add_trace(
            go.Bar(
                y=labels,
                x=values,
                name=name,
                orientation="h",
                hovertemplate="%{customdata}<extra></extra>",
                customdata=custom,
            )
        )
    top_fig.update_layout(
        title=None,
        barmode="group",
        template="plotly_white",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.02,
            x=0,
            xanchor="left",
            bgcolor="rgba(255,255,255,0.95)",
        ),
        margin=dict(l=150, r=40, t=20, b=80),
        height=max(700, args.top * 18),
        hovermode="closest",
        xaxis_title="pips",
        yaxis_title="Період тренду",
        yaxis=dict(autorange="reversed"),
        font=dict(family="Segoe UI, system-ui, sans-serif", size=12),
    )

    top_title = f"Топ-{args.top} трендів: тренд / перша корекція / макс. корекція"
    charts_spec: list[tuple[str, go.Figure]] = [
        (
            "Розподіл розміру тренду (pips)",
            bar_fig(
                pip_cats,
                [("Кількість трендів", [float(v) for v in trend_counts])],
                xlabel="Розмір тренду (pips)",
                ylabel="Кількість",
            ),
        ),
        (
            f"Перша корекція vs макс. корекція ({days} днів)",
            bar_fig(
                pip_cats,
                [
                    ("Перша ZigZag-корекція", [float(v) for v in corr_counts]),
                    (f"Макс. корекція ({days}д)", [float(v) for v in approach_counts]),
                ],
                xlabel="Розмір (pips)",
                ylabel="Кількість",
            ),
        ),
        (
            "Перша корекція (% від тренду)",
            bar_fig(
                pct_cats,
                [("Кількість", [float(v) for v in first_pct])],
                xlabel="correction_pct",
                ylabel="Кількість",
                height=400,
            ),
        ),
        (
            f"Макс. корекція (% від тренду, {days}д)",
            bar_fig(
                pct_cats,
                [("Кількість", [float(v) for v in approach_pct])],
                xlabel="max_correction_pct",
                ylabel="Кількість",
                height=400,
            ),
        ),
        (top_title, top_fig),
    ]
    chart_sections = [
        chart_section(chart_title, fig, f"chart-{i}")
        for i, (chart_title, fig) in enumerate(charts_spec)
    ]

    n = len(df)
    trend_median = round(float(df.trend_pips.median()), 1)
    max_corr_median = round(float(df.max_correction_pips.median()), 1)
    max_corr_pct_median = round(float(df.max_correction_pct.median()), 1)

    html = build_page(
        title=title,
        csv_name=src.name,
        period=period,
        days=days,
        threshold=threshold,
        n=n,
        approach_median=max_corr_median,
        approach_pct_median=max_corr_pct_median,
        trend_median=trend_median,
        chart_sections=chart_sections,
    )
    html_path = out / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"Saved HTML: {html_path}")
    print(f"Data copy: {out / src.name}")

    if args.pdf:
        pdf_path = out / f"{stem}.pdf"
        try:
            figures_to_pdf(
                pdf_path,
                title=title,
                subtitle=(
                    f"ZigZag >={threshold} pips · макс. корекція за {days} днів · "
                    f"{period} · {n:,} трендів"
                ),
                stats=[
                    ("Трендів", f"{n:,}"),
                    ("Медіана тренду (pips)", str(trend_median)),
                    ("Медіана макс. корекції (pips)", str(max_corr_median)),
                    ("Медіана макс. корекції %", f"{max_corr_pct_median:.0f}%"),
                ],
                charts=charts_spec,
            )
            size_mb = pdf_path.stat().st_size / (1024 * 1024)
            print(f"Saved PDF: {pdf_path} ({size_mb:.1f} MB)")
        except Exception as exc:
            print(f"PDF skip: {exc}", file=sys.stderr)
            print(
                "Можна зберегти PDF з HTML: кнопка «Зберегти PDF» -> «Зберегти як PDF».",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
