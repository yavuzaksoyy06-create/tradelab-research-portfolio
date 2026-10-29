"""Rebuild public README figures from archived aggregates and synthetic fixtures."""
from pathlib import Path
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from research_workspace.equity_data import synthetic_fixture, analyze_prefix
from research_workspace.equity_indicators import indicator_frame
from research_workspace.equity_zones import historical_zone_bands

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
NAVY, MUTED, RED, GREEN, BLUE = "#182b49", "#63728a", "#c65665", "#138879", "#4477c8"


def style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.spines.left": False, "axes.spines.bottom": False,
                         "axes.labelcolor": MUTED, "text.color": NAVY,
                         "xtick.color": MUTED, "ytick.color": MUTED,
                         "figure.facecolor": "#f7f9fc", "axes.facecolor": "#f7f9fc",
                         "savefig.facecolor": "#f7f9fc", "svg.hashsalt": "tradelab-readme-v1"})


def table_rows(text):
    return [[v.strip() for v in line.strip().strip("|").split("|")]
            for line in text.splitlines() if line.startswith("|")]


def historical_results():
    source = ROOT / "docs" / "v41-historical-research.md"
    text = source.read_text(encoding="utf-8")
    rows = table_rows(text)
    replay = {r[1]: (float(r[5]), int(r[3])) for r in rows if r[0] == "observed_replay"}
    costs = table_rows(text.split("## Cost sensitivity")[1].split("## Verification")[0])
    costs = [(int(r[0]), float(r[1])) for r in costs if r[0] in ("0", "3", "6", "10")]
    assert set(replay) == {"touch", "rejection", "trend_filtered"} and len(costs) == 4
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.1), gridspec_kw={"width_ratios": [1.15, 1]})
    fig.subplots_adjust(left=.14, right=.96, top=.72, bottom=.22, wspace=.40)
    fig.text(.045, .93, "RESEARCH RESULT  /  V4.1", fontsize=11, weight="bold", color=BLUE)
    fig.text(.045, .85, "An attractive chart pattern did not establish an edge.", fontsize=19, weight="bold")
    names = ["touch", "rejection", "trend_filtered"]
    values = [replay[k][0] for k in names]
    labels = ["Support touch", "Rejection", "Trend filtered"]
    ax = axes[0]
    ax.barh(range(3), values, color=RED, height=.5)
    ax.set_yticks(range(3), labels)
    ax.invert_yaxis()
    ax.set_xlim(-160, 12)
    ax.axvline(0, color=MUTED, lw=1)
    ax.set_xlabel("Net simulated P&L (USD)")
    ax.set_title("42-session inspected replay · 3 bp per side", loc="left", fontsize=11, pad=15)
    for i, key in enumerate(names):
        ax.text(values[i] + 4, i, f"-${abs(values[i]):.2f}  /  {replay[key][1]} trades",
                va="center", color="white", fontsize=9, weight="bold") if abs(values[i]) > 50 else ax.text(
                    values[i]-4, i, f"-${abs(values[i]):.2f}  /  {replay[key][1]} trades",
                    va="center", ha="right", fontsize=9, weight="bold")
    ax = axes[1]
    x, y = zip(*costs)
    ax.plot(x, y, color=BLUE, lw=2.3, marker="o", markersize=7)
    ax.axhline(0, color=MUTED, lw=1, linestyle="--")
    ax.set_xticks(x)
    ax.set_ylim(-790, 170)
    ax.set_xlabel("Assumed transaction cost per side (bp)")
    ax.set_ylabel("Net simulated P&L (USD)")
    ax.set_title("Separate 30-session validation · support touch", loc="left", fontsize=11, pad=15)
    for cost, pnl in costs:
        ax.annotate(f"{'+' if pnl >= 0 else '-'}${abs(pnl):.2f}", (cost, pnl),
                    xytext=(0, 13), textcoords="offset points", ha="center", fontsize=9, weight="bold")
    fig.text(.045, .095, "Each replay candidate starts with its own $100,000 shared-cash portfolio across MSFT, SPY and QQQ.",
             fontsize=9, color=MUTED)
    fig.text(.045, .05, "Archived, already-inspected simulations; periods are different and must not be combined. No new market data or backtest.",
             fontsize=9, color=MUTED)
    fig.savefig(OUT / "research-results.png", dpi=180)
    plt.close(fig)
    return {"source": source.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "replay": replay, "validation_cost_cases": costs}


def replay_example():
    bars, meta = synthetic_fixture()
    prefix, features = analyze_prefix(bars, 160)
    indicators = indicator_frame(prefix)
    first = 60
    fig, (ax, volume, rsi) = plt.subplots(3, 1, figsize=(13, 7), sharex=True,
                                         gridspec_kw={"height_ratios": [3.1, .85, .85], "hspace": .13})
    fig.subplots_adjust(left=.075, right=.96, top=.83, bottom=.14)
    fig.text(.045, .95, "CAUSAL REPLAY  /  SYNTHETIC EDUCATIONAL FIXTURE", fontsize=11, weight="bold", color=BLUE)
    fig.text(.045, .89, "A signal becomes visible only when its evidence is known.", fontsize=19, weight="bold")
    for band in historical_zone_bands(features["snapshots"], visible_start=first):
        ax.add_patch(Rectangle((band["start_index"]-.5, band["lower"]),
                              band["end_index"]-band["start_index"]+1,
                              band["upper"]-band["lower"],
                              color=GREEN if band["kind"] == "support" else RED, alpha=.12, lw=0))
    for i in range(first, len(prefix)):
        row = prefix.iloc[i]
        color = GREEN if row.close >= row.open else RED
        ax.vlines(i, row.low, row.high, color=color, linewidth=.8)
        ax.add_patch(Rectangle((i-.3, min(row.open, row.close)), .6,
                              max(abs(row.close-row.open), .004), color=color, lw=0))
        volume.bar(i, row.volume/1000, color=color, width=.6, alpha=.7)
    for period, color in ((9, BLUE), (21, "#9c71b6")):
        ax.plot(range(first, len(prefix)), indicators[f"ema_{period}"].iloc[first:],
                color=color, linewidth=1.6, label=f"EMA {period}")
    for kind, marker, color in (("support", "^", GREEN), ("resistance", "v", RED)):
        pivots = [p for p in features["pivots"] if first <= p["confirmed_index"] < len(prefix) and p["kind"] == kind]
        ax.scatter([p["confirmed_index"] for p in pivots], [p["price"] for p in pivots],
                   marker=marker, c=color, s=40, zorder=5, label=f"Confirmed {kind} pivot")
    ax.legend(loc="upper left", ncol=2, frameon=False, fontsize=8)
    bands = historical_zone_bands(features["snapshots"], visible_start=first)
    lower = min([float(prefix.low.iloc[first:].min())] + [b["lower"] for b in bands])
    upper = max([float(prefix.high.iloc[first:].max())] + [b["upper"] for b in bands])
    ax.set_ylim(lower - .25, upper + .45)
    ax.set_ylabel("Synthetic price units")
    volume.set_ylabel("Volume\n(thousands)", fontsize=9)
    rsi.plot(range(first, len(prefix)), indicators.rsi_14.iloc[first:], color=BLUE, lw=1.5)
    rsi.axhline(30, color=MUTED, lw=.6, linestyle="--")
    rsi.axhline(70, color=MUTED, lw=.6, linestyle="--")
    rsi.set_ylim(0, 100)
    rsi.set_ylabel("RSI (14)")
    rsi.set_xlabel("Completed 15-minute bar index · non-trading gaps omitted")
    ax.set_xlim(first-1, len(prefix))
    for panel in (ax, volume, rsi):
        panel.grid(axis="y", alpha=.12)
    fig.text(.045, .04, "Generated from project code, not a UI screenshot or a market-price chart. Shading uses historical zone states; markers use confirmation bars.",
             fontsize=9, color=MUTED)
    fig.savefig(OUT / "causal-replay.png", dpi=180)
    plt.close(fig)
    return {"source": "research_workspace/equity_data.py::synthetic_fixture", "synthetic": True,
            "visible_bars": len(prefix), "first_displayed_bar_index": first,
            "as_of": prefix.bar_end.iloc[-1].isoformat(), "orders_enabled": meta["orders_enabled"]}


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    style()
    evidence = {"historical_results": historical_results(), "replay_example": replay_example()}
    evidence["figures"] = {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
                           for name in ("research-results.png", "causal-replay.png")}
    (OUT / "readme-figure-sources.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
