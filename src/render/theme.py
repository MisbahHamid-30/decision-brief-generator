"""Shared visual identity for every output format."""

PALETTE = {
    "green":      "#0FA958",   # primary
    "deep":       "#046A38",   # headers, emphasis
    "ink":        "#1A1A1A",   # body text
    "slate":      "#5C6B73",   # secondary text, axes
    "red":        "#D64545",   # losses, breaches
    "amber":      "#E8A33D",   # watch items
    "mist":       "#F4F6F5",   # backgrounds, banding
    "line":       "#DCE2E0",   # rules and gridlines
    "white":      "#FFFFFF",
}

# without the leading hash, for pptxgenjs
HEX = {k: v.lstrip("#") for k, v in PALETTE.items()}

FONT_HEAD = "Cambria"
FONT_BODY = "Calibri"

CHART_DPI = 160


def mpl_style():
    """Matplotlib rcParams. Called once before drawing."""
    return {
        "figure.facecolor": PALETTE["white"],
        "axes.facecolor": PALETTE["white"],
        "axes.edgecolor": PALETTE["line"],
        "axes.labelcolor": PALETTE["slate"],
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlecolor": PALETTE["ink"],
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": PALETTE["line"],
        "grid.linewidth": 0.8,
        "xtick.color": PALETTE["slate"],
        "ytick.color": PALETTE["slate"],
        "text.color": PALETTE["ink"],
        "font.size": 10,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans"],
        "legend.frameon": False,
        "figure.dpi": CHART_DPI,
        "savefig.dpi": CHART_DPI,
        "savefig.bbox": "tight",
        "savefig.facecolor": PALETTE["white"],
    }


def fmt_aed(v: float, decimals: int = 0) -> str:
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e6:
        return f"{sign}AED {a/1e6:,.2f}m"
    if a >= 1e3:
        return f"{sign}AED {a/1e3:,.0f}k"
    return f"{sign}AED {a:,.{decimals}f}"
