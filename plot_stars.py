from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    panel_bg: str
    border: str
    text: str
    muted: str
    grid: str
    accent: str
    delta_bg: str
    delta_fg: str
    series: tuple[str, ...]


LIGHT_THEME = Theme(
    name="light",
    bg="#ffffff",
    panel_bg="#ffffff",
    border="#d0d7de",
    text="#1f2328",
    muted="#656d76",
    grid="#eaeef2",
    accent="#0969da",
    delta_bg="#dafbe1",
    delta_fg="#116329",
    series=(
        "#0969da",  # blue
        "#8250df",  # purple
        "#bf3989",  # magenta
        "#1a7f37",  # green
        "#bc4c00",  # orange
        "#0e8a9c",  # teal
        "#cf222e",  # crimson
    ),
)

DARK_THEME = Theme(
    name="dark",
    bg="#0d1117",
    panel_bg="#0d1117",
    border="#30363d",
    text="#e6edf3",
    muted="#8b949e",
    grid="#21262d",
    accent="#58a6ff",
    delta_bg="#12261e",
    delta_fg="#3fb950",
    series=(
        "#58a6ff",  # blue
        "#bc8cff",  # purple
        "#f778ba",  # pink
        "#3fb950",  # green
        "#ffa657",  # orange
        "#39c5cf",  # teal
        "#ff7b72",  # coral
    ),
)


def _fmt_stars(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return f"{n:,}"


def _fmt_axis_k(x: float, _pos: int) -> str:
    if x == 0:
        return "0"
    if x >= 1000:
        val = x / 1000
        return f"{val:.0f}k" if val.is_integer() else f"{val:.1f}k"
    return f"{int(x)}"


def _short_repo_name(full_name: str) -> str:
    owner, name = full_name.split("/", 1)
    if owner == "basnijholt":
        return name
    if name == owner or name.startswith(f"{owner}-") or owner in ("mindroom-ai", "pipefunc", "python-adaptive", "python-kasa"):
        return name
    return full_name


def _spread_labels(
    targets: list[float],
    ymin: float,
    ymax: float,
    min_gap: float,
) -> list[float]:
    """Adjust label y-positions upward/downward to eliminate vertical overlaps."""
    if not targets:
        return []
    indexed = sorted(enumerate(targets), key=lambda kv: kv[1])
    ys = [val for _, val in indexed]

    for _ in range(120):
        moved = False
        for i in range(1, len(ys)):
            gap = ys[i] - ys[i - 1]
            if gap < min_gap:
                shift = (min_gap - gap) / 2.0
                ys[i - 1] -= shift
                ys[i] += shift
                moved = True
        ys[0] = max(ys[0], ymin)
        ys[-1] = min(ys[-1], ymax)
        for i in range(len(ys) - 2, -1, -1):
            if ys[i + 1] - ys[i] < min_gap:
                ys[i] = ys[i + 1] - min_gap
        if ys[0] < ymin:
            ys[0] = ymin
            for i in range(1, len(ys)):
                if ys[i] - ys[i - 1] < min_gap:
                    ys[i] = ys[i - 1] + min_gap
        if not moved:
            break

    result = [0.0] * len(targets)
    for (orig_idx, _), y in zip(indexed, ys, strict=True):
        result[orig_idx] = y
    return result


def _gradient_fill(
    ax: plt.Axes,
    x_num: np.ndarray,
    y: np.ndarray,
    color: str,
    alpha_top: float,
    alpha_bottom: float = 0.0,
) -> None:
    """Draw a smooth vertical gradient fill underneath a line plot."""
    if len(x_num) < 2:
        return
    r, g, b, _ = to_rgba(color)
    cmap = LinearSegmentedColormap.from_list(
        "area_grad",
        [(r, g, b, alpha_bottom), (r, g, b, alpha_top)],
    )
    z = np.linspace(0, 1, 256).reshape(-1, 1)
    y_max = float(np.max(y))
    im = ax.imshow(
        z,
        aspect="auto",
        cmap=cmap,
        origin="lower",
        extent=[float(x_num[0]), float(x_num[-1]), 0.0, y_max * 1.02],
        zorder=1,
    )
    verts = np.vstack(
        [
            [x_num[0], 0.0],
            np.column_stack([x_num, y]),
            [x_num[-1], 0.0],
            [x_num[0], 0.0],
        ]
    )
    patch = PathPatch(MplPath(verts), facecolor="none", edgecolor="none")
    ax.add_patch(patch)
    im.set_clip_path(patch)


def _style_axes(ax: plt.Axes, theme: Theme) -> None:
    ax.set_facecolor(theme.panel_bg)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(theme.border)
    ax.spines["bottom"].set_linewidth(0.9)
    ax.yaxis.grid(True, color=theme.grid, linewidth=0.9, zorder=0)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0, colors=theme.muted, labelsize=9.5, pad=6)
    ax.tick_params(axis="x", length=3, color=theme.border, colors=theme.muted, labelsize=9.5, pad=5)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_axis_k))
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def render_stars_dashboard(
    stargazers: list[dict[str, Any]],
    output_path: str,
    theme: Theme,
    top_n_repos: int = 7,
) -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Inter", "Liberation Sans", "DejaVu Sans"],
            "axes.edgecolor": theme.border,
            "figure.facecolor": theme.bg,
            "savefig.facecolor": theme.bg,
        }
    )

    fig, (ax_total, ax_repos) = plt.subplots(
        1,
        2,
        figsize=(14.0, 5.0),
        dpi=220,
        gridspec_kw={"width_ratios": [1.0, 1.0], "wspace": 0.16},
    )
    fig.patch.set_facecolor(theme.bg)

    # --- Left panel: Total stars over time ---
    all_dates = sorted(
        date for info in stargazers for date in info["dates"]
    )
    total_stars = len(all_dates)
    now_dt = all_dates[-1] if all_dates else datetime.now()
    cutoff_1y = now_dt - timedelta(days=365)
    stars_last_year = sum(1 for d in all_dates if d >= cutoff_1y)

    _style_axes(ax_total, theme)
    if all_dates:
        x_num = mdates.date2num(all_dates)
        y_vals = np.arange(1, total_stars + 1, dtype=float)
        # Subsample gently for rendering speed while preserving exact start/end
        if len(x_num) > 1200:
            idx = np.unique(np.linspace(0, len(x_num) - 1, 1200).astype(int))
            x_plot, y_plot = x_num[idx], y_vals[idx]
        else:
            x_plot, y_plot = x_num, y_vals

        _gradient_fill(
            ax_total,
            x_plot,
            y_plot,
            theme.accent,
            alpha_top=0.22 if theme.name == "light" else 0.28,
        )
        ax_total.plot(
            x_plot,
            y_plot,
            color=theme.accent,
            linewidth=2.4,
            solid_capstyle="round",
            zorder=3,
        )
        ax_total.scatter(
            [x_plot[-1]],
            [y_plot[-1]],
            s=85,
            color=theme.accent,
            alpha=0.22,
            edgecolors="none",
            zorder=4,
        )
        ax_total.scatter(
            [x_plot[-1]],
            [y_plot[-1]],
            s=28,
            color=theme.accent,
            edgecolors=theme.bg,
            linewidths=1.4,
            zorder=5,
        )

        x_span = x_plot[-1] - x_plot[0]
        ax_total.set_xlim(x_plot[0] - x_span * 0.02, x_plot[-1] + x_span * 0.05)
        ax_total.set_ylim(0, total_stars * 1.14)

    ax_total.text(
        0.0,
        1.14,
        "TOTAL GITHUB STARS (TOP 20 REPOS)",
        transform=ax_total.transAxes,
        fontsize=8.5,
        fontweight="bold",
        color=theme.muted,
        va="bottom",
    )
    ax_total.text(
        0.0,
        1.035,
        f"{total_stars:,}",
        transform=ax_total.transAxes,
        fontsize=20,
        fontweight="bold",
        color=theme.text,
        va="bottom",
    )
    ax_total.text(
        0.25,
        1.05,
        f"  +{stars_last_year:,} in the last 12 months  ",
        transform=ax_total.transAxes,
        fontsize=8.5,
        fontweight="medium",
        color=theme.delta_fg,
        va="bottom",
        bbox={
            "boxstyle": "round,pad=0.32,rounding_size=0.4",
            "facecolor": theme.delta_bg,
            "edgecolor": "none",
        },
    )

    # --- Right panel: Top N repositories over time with direct labels ---
    _style_axes(ax_repos, theme)
    plotted_repos = [info for info in stargazers if info["dates"]][:top_n_repos]

    end_x_max = 0.0
    start_x_min = float("inf")
    y_max_repo = 0.0
    endpoints: list[tuple[float, float, str, str]] = []

    for i, info in enumerate(plotted_repos):
        dates = info["dates"]
        x_num = mdates.date2num(dates)
        y_vals = np.arange(1, len(dates) + 1, dtype=float)
        color = theme.series[i % len(theme.series)]
        lw = 2.4 if i == 0 else 1.9

        ax_repos.plot(
            x_num,
            y_vals,
            color=color,
            linewidth=lw,
            solid_capstyle="round",
            zorder=4 if i == 0 else 3,
        )
        ax_repos.scatter(
            [x_num[-1]],
            [y_vals[-1]],
            s=22 if i == 0 else 16,
            color=color,
            edgecolors=theme.bg,
            linewidths=1.0,
            zorder=5,
        )
        start_x_min = min(start_x_min, float(x_num[0]))
        end_x_max = max(end_x_max, float(x_num[-1]))
        y_max_repo = max(y_max_repo, float(y_vals[-1]))
        label_name = _short_repo_name(info["full_name"])
        endpoints.append((float(x_num[-1]), float(y_vals[-1]), f"{label_name}  {_fmt_stars(len(dates))}", color))

    if endpoints:
        x_span = max(end_x_max - start_x_min, 365.0)
        y_top = y_max_repo * 1.12
        ax_repos.set_xlim(start_x_min - x_span * 0.02, end_x_max + x_span * 0.03)
        ax_repos.set_ylim(0, y_top)

        target_ys = [ep[1] for ep in endpoints]
        min_gap = y_top * 0.072
        placed_ys = _spread_labels(
            target_ys,
            ymin=y_top * 0.03,
            ymax=y_top * 0.97,
            min_gap=min_gap,
        )

        label_x = end_x_max + x_span * 0.06
        for (ex, ey, label, color), py in zip(endpoints, placed_ys, strict=True):
            ax_repos.plot(
                [ex + x_span * 0.012, label_x - x_span * 0.014],
                [ey, py],
                color=color,
                linewidth=0.85,
                alpha=0.45,
                clip_on=False,
                zorder=2,
            )
            ax_repos.text(
                label_x,
                py,
                label,
                color=color,
                fontsize=8.6,
                fontweight="semibold" if ey == y_max_repo else "medium",
                va="center",
                ha="left",
                clip_on=False,
                zorder=6,
            )

    ax_repos.text(
        0.0,
        1.14,
        f"GROWTH BY REPOSITORY (TOP {len(plotted_repos)})",
        transform=ax_repos.transAxes,
        fontsize=8.5,
        fontweight="bold",
        color=theme.muted,
        va="bottom",
    )
    ax_repos.text(
        0.0,
        1.035,
        "Stars per project",
        transform=ax_repos.transAxes,
        fontsize=15.5,
        fontweight="bold",
        color=theme.text,
        va="bottom",
    )

    fig.subplots_adjust(left=0.05, right=0.815, top=0.79, bottom=0.11, wspace=0.16)
    fig.savefig(output_path, dpi=220, facecolor=theme.bg, edgecolor="none")
    plt.close(fig)


def render_both_themes(
    stargazers: list[dict[str, Any]],
    light_path: str = "stars_light.png",
    dark_path: str = "stars_dark.png",
) -> None:
    render_stars_dashboard(stargazers, light_path, LIGHT_THEME)
    render_stars_dashboard(stargazers, dark_path, DARK_THEME)
