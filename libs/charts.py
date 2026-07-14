"""Shared Plotly chart helpers and PDF export for presentations."""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
from matplotlib.backends.backend_pdf import PdfPages

# A4 landscape (inches)
_PAGE_W = 11.69
_PAGE_H = 8.27


def _wrap_text(text: str, width: int) -> str:
    """Wrap long lines so cover text stays inside the page."""
    parts: list[str] = []
    for para in str(text).splitlines() or [""]:
        wrapped = textwrap.wrap(para, width=width, break_long_words=True)
        parts.extend(wrapped if wrapped else [""])
    return "\n".join(parts)


def figures_to_pdf(
    pdf_path: Path,
    *,
    title: str,
    subtitle: str,
    stats: list[tuple[str, str]],
    charts: list[tuple[str, go.Figure]],
) -> None:
    """Write a multi-page PDF with cover stats + one chart per page.

    Writes to a temp file first and only replaces the destination on success,
    so a failed render never deletes an existing valid PDF.
    """
    pdf_path = pdf_path.resolve()
    tmp_path = pdf_path.with_suffix(".tmp.pdf")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        with PdfPages(tmp_path) as pdf:
            fig, ax = plt.subplots(figsize=(_PAGE_W, _PAGE_H))
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis("off")
            ax.text(
                0.04,
                0.92,
                _wrap_text(title, 55),
                fontsize=20,
                fontweight="bold",
                va="top",
                ha="left",
                transform=ax.transAxes,
                clip_on=True,
            )
            ax.text(
                0.04,
                0.78,
                _wrap_text(subtitle, 100),
                fontsize=10,
                color="#5c574f",
                va="top",
                ha="left",
                linespacing=1.35,
                transform=ax.transAxes,
                clip_on=True,
            )
            y = 0.58
            for label, value in stats:
                ax.text(
                    0.04,
                    y,
                    str(value),
                    fontsize=18,
                    fontweight="bold",
                    va="top",
                    transform=ax.transAxes,
                )
                ax.text(
                    0.04,
                    y - 0.05,
                    str(label),
                    fontsize=10,
                    color="#5c574f",
                    va="top",
                    transform=ax.transAxes,
                )
                y -= 0.13
            # Same page width as chart pages (figure width = _PAGE_W, no tight crop)
            pdf.savefig(fig, bbox_inches=None, pad_inches=0)
            plt.close(fig)

            for chart_title, plotly_fig in charts:
                height_px = min(int(plotly_fig.layout.height or 440), 2200)
                width_px = 1100
                export_fig = go.Figure(plotly_fig)
                export_fig.update_layout(height=height_px)
                png = export_fig.to_image(
                    format="png", width=width_px, height=height_px, scale=1
                )
                img = plt.imread(io.BytesIO(png), format="png")
                # Tall pages OK for readability; width must match cover (_PAGE_W)
                page_h = min(_PAGE_W * (height_px / width_px) + 0.9, 30)
                fig, ax = plt.subplots(figsize=(_PAGE_W, page_h))
                fig.subplots_adjust(left=0.04, right=0.96, top=0.92, bottom=0.05)
                ax.axis("off")
                ax.set_title(
                    _wrap_text(chart_title, 90), fontsize=12, loc="left", pad=8
                )
                ax.imshow(img)
                # No bbox_inches="tight" — it changes MediaBox width vs the cover page
                pdf.savefig(fig, bbox_inches=None, pad_inches=0)
                plt.close(fig)

        tmp_path.replace(pdf_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def pip_hist(series: pd.Series, edges: list[int], labels: list[str]) -> list[int]:
    return (
        pd.cut(series.dropna(), bins=edges, right=False, labels=labels)
        .value_counts()
        .reindex(labels)
        .fillna(0)
        .astype(int)
        .tolist()
    )


def bar_fig(
    categories: list[str],
    series: list[tuple[str, list[float]]],
    *,
    xlabel: str,
    ylabel: str,
    horizontal: bool = False,
    height: int | None = None,
) -> go.Figure:
    fig = go.Figure()
    for name, values in series:
        custom = [
            f"<b>{name}</b><br>{xlabel}: {cat}<br>{ylabel}: {val}"
            for cat, val in zip(categories, values)
        ]
        if horizontal:
            fig.add_trace(
                go.Bar(
                    y=categories,
                    x=values,
                    name=name,
                    orientation="h",
                    hovertemplate="%{customdata}<extra></extra>",
                    customdata=custom,
                )
            )
        else:
            fig.add_trace(
                go.Bar(
                    x=categories,
                    y=values,
                    name=name,
                    hovertemplate="%{customdata}<extra></extra>",
                    customdata=custom,
                )
            )

    fig.update_layout(
        title=None,
        barmode="group",
        template="plotly_white",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.18,
            x=0,
            xanchor="left",
        ),
        margin=dict(l=60, r=30, t=20, b=90),
        height=height or (max(520, 18 * len(categories)) if horizontal else 440),
        hovermode="closest",
        xaxis_title=ylabel if horizontal else xlabel,
        yaxis_title=xlabel if horizontal else ylabel,
        font=dict(family="Segoe UI, system-ui, sans-serif", size=13),
    )
    if horizontal:
        fig.update_yaxes(autorange="reversed")
    return fig


def fig_to_div(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )


def chart_section(title: str, fig: go.Figure, div_id: str) -> str:
    """HTML card with selectable title above the Plotly chart."""
    return f"""  <section class="card">
    <h2 class="chart-title">{title}</h2>
    {fig_to_div(fig, div_id)}
  </section>"""
