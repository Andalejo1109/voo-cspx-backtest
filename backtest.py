#!/usr/bin/env python3
"""VOO vs CSPX (10 years) with US withholding for non-residents, plus a growth-portfolio comparison.

Default window: 2016-09-21 to latest available.
Tax assumption: 30% US withholding on VOO dividends (typical non-treaty non-resident).
Irish UCITS (CSPX) already embeds ~15% US withholding inside the fund.
Research / education only — not tax, legal or investment advice.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

START = "2016-09-21"
END = None
NONRESIDENT_WH = 0.30

# Snapshot of @Andalejo1109 eToro book (USD market value, 2026-09-21).
VALUES = {
    "SPYG": 14786.71,
    "SMH": 10053.91,
    "BRK-B": 9468.96,
    "IEMG": 9404.32,
    "VTI": 3525.50,
}
WEIGHTS = {k: v / sum(VALUES.values()) for k, v in VALUES.items()}

C_BG = "#0B1220"
C_PANEL = "#121A2B"
C_GRID = "#243049"
C_TEXT = "#E8EEF7"
C_MUTED = "#9AA8BD"
C_VOO = "#5B8DEF"
C_VOO_TAX = "#A7C4FF"
C_VOO_PX = "#4C6A99"
C_CSPX = "#2EC4B6"
C_PORT = "#F4B942"
C_SMH = "#FF6B4A"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.facecolor": C_PANEL,
    "figure.facecolor": C_BG,
    "savefig.facecolor": C_BG,
    "text.color": C_TEXT,
    "axes.labelcolor": C_TEXT,
    "xtick.color": C_MUTED,
    "ytick.color": C_MUTED,
    "axes.edgecolor": C_GRID,
    "grid.color": C_GRID,
    "grid.linewidth": 0.6,
    "axes.titleweight": "bold",
})


def download():
    tickers = ["VOO", "CSPX.L", *WEIGHTS]
    raw = yf.download(tickers, start=START, end=END, auto_adjust=False, progress=False, threads=True)
    close = raw["Close"].copy().ffill(limit=2)
    adj = raw["Adj Close"].copy().ffill(limit=2)
    both = pd.concat({"close": close, "adj": adj}, axis=1).dropna()
    return both["close"], both["adj"]


def voo_dividends(start, end_ts):
    divs = yf.Ticker("VOO").dividends
    if getattr(divs.index, "tz", None) is not None:
        divs.index = divs.index.tz_convert(None).normalize()
    return divs[(divs.index >= start) & (divs.index <= end_ts)]


def simulate_taxed_voo(close_voo, divs, tax):
    """Reinvest after-withholding dividends into VOO at that day's close."""
    shares = 1.0
    px0 = float(close_voo.iloc[0])
    close_days = close_voo.index.normalize()
    div_map = {}
    for d, v in divs.items():
        key = pd.Timestamp(d).normalize()
        if key not in close_days:
            nxt = close_days[close_days >= key]
            if not len(nxt):
                continue
            key = nxt[0]
        div_map[key] = div_map.get(key, 0.0) + float(v)
    wealth = np.empty(len(close_voo), dtype=float)
    for i, (dt, px) in enumerate(close_voo.items()):
        key = pd.Timestamp(dt).normalize()
        px = float(px)
        if key in div_map and px > 0:
            shares += (div_map[key] * (1.0 - tax)) / px
        wealth[i] = shares * px
    return pd.Series(wealth / px0, index=close_voo.index)


def wealth_from_price(s):
    return s / float(s.iloc[0])


def portfolio_buyhold(adj, weights):
    cols = list(weights)
    w = np.array([weights[c] for c in cols], dtype=float)
    norm = adj[cols] / adj[cols].iloc[0]
    return (norm * w).sum(axis=1).rename("port_bh")


def portfolio_rebalanced(adj, weights, freq="YE"):
    cols = list(weights)
    px = adj[cols]
    w = np.array([weights[c] for c in cols], dtype=float)
    rets = px.pct_change().fillna(0.0)
    period_ends = set(px.resample(freq).last().index)
    holdings = w.copy()
    wealth = np.empty(len(px), dtype=float)
    wealth[0] = 1.0
    dates = px.index
    for i in range(1, len(dates)):
        holdings = holdings * (1.0 + rets.iloc[i].to_numpy())
        wealth[i] = holdings.sum()
        if dates[i] in period_ends:
            holdings = w * wealth[i]
    return pd.Series(wealth, index=dates, name="port_reb")


def cagr(s):
    years = (s.index[-1] - s.index[0]).days / 365.25
    return float(s.iloc[-1] ** (1 / years) - 1)


def max_dd(s):
    return float((s / s.cummax() - 1).min())


def stats_row(name, s):
    return {
        "serie": name,
        "retorno_total_%": (float(s.iloc[-1]) - 1) * 100,
        "multiplo": float(s.iloc[-1]),
        "cagr_%": cagr(s) * 100,
        "max_dd_%": max_dd(s) * 100,
        "final_10k_usd": 10_000 * float(s.iloc[-1]),
    }


def savefig(fig, stem):
    fig.savefig(OUT / f"{stem}.png", bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.svg", bbox_inches="tight")
    plt.close(fig)


def plot_voo_cspx(series):
    fig, ax = plt.subplots(figsize=(12.5, 7.2), dpi=160)
    s_px = series["VOO precio (sin div.)"]
    s_tr = series["VOO TR (0% impuesto)"]
    s_tax = series["VOO TR (30% retención no-residente)"]
    s_c = series["CSPX acumulativo"]
    ax.plot(s_px.index, s_px, color=C_VOO_PX, lw=1.6, ls="--", label="VOO precio (sin reinvertir dividendos)")
    ax.plot(s_tr.index, s_tr, color=C_VOO, lw=2.0, label="VOO total return (0% impuesto sobre div.)")
    ax.plot(s_tax.index, s_tax, color=C_VOO_TAX, lw=2.2, label="VOO after-tax 30% retención US (no-residente)")
    ax.plot(s_c.index, s_c, color=C_CSPX, lw=2.6, label="CSPX UCITS acumulativo")
    ax.set_title("VOO vs CSPX · 10 años\nPara un no-residente, el acumulativo gana por poco", loc="left", fontsize=15, pad=12)
    ax.set_ylabel("Crecimiento de $1 inicial")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{x:.1f}x"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.grid(True, axis="y", alpha=0.55)
    ax.legend(frameon=False, loc="upper left", fontsize=9.5)
    for s, color in ((s_px, C_VOO_PX), (s_tr, C_VOO), (s_tax, C_VOO_TAX), (s_c, C_CSPX)):
        ax.annotate(f"{s.iloc[-1]:.2f}x", xy=(s.index[-1], s.iloc[-1]), xytext=(8, 0), textcoords="offset points", color=color, fontsize=9, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.text(0.01, 0.01, "Fuente: Yahoo Finance. CSPX.L en USD. Retención 30% ilustrativa para no-residentes US. No es asesoría fiscal.", fontsize=7.2, color=C_MUTED)
    fig.tight_layout(rect=[0, 0.035, 1, 1])
    savefig(fig, "voo_vs_cspx")


def plot_port_vs_cspx(series, comps):
    fig, ax = plt.subplots(figsize=(12.5, 7.2), dpi=160)
    s_c = series["CSPX acumulativo"]
    s_p = series["Portafolio buy&hold"]
    s_r = series["Portafolio rebalance anual"]
    for name, s in comps.items():
        ax.plot(s.index, s, color="#6B7C93", lw=0.9, alpha=0.35)
    ax.plot(comps["SMH"].index, comps["SMH"], color=C_SMH, lw=1.1, alpha=0.55, label="SMH (componente)")
    ax.plot(s_c.index, s_c, color=C_CSPX, lw=2.4, label="CSPX acumulativo (S&P 500 UCITS)")
    ax.plot(s_r.index, s_r, color="#E8D48B", lw=1.8, ls="--", label="Portafolio rebalance anual")
    ax.plot(s_p.index, s_p, color=C_PORT, lw=2.8, label="Portafolio (buy & hold, pesos de hoy)")
    ax.set_title("Portafolio growth vs CSPX · mismos 10 años\nEl wrapper acc/dist es de segundo orden frente al motor", loc="left", fontsize=15, pad=12)
    ax.set_ylabel("Crecimiento de $1 inicial")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{x:.0f}x"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.grid(True, axis="y", alpha=0.55)
    ax.legend(frameon=False, loc="upper left", fontsize=9.5)
    for s, color in ((s_c, C_CSPX), (s_p, C_PORT), (s_r, "#E8D48B")):
        ax.annotate(f"{s.iloc[-1]:.2f}x", xy=(s.index[-1], s.iloc[-1]), xytext=(8, 0), textcoords="offset points", color=color, fontsize=10, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    wtxt = "Pesos: " + " · ".join(f"{k.replace('BRK-B', 'BRK.B')} {v * 100:.1f}%" for k, v in WEIGHTS.items())
    fig.text(0.01, 0.018, wtxt + "\nBacktest hipotético. Pesos de hoy inflados por ganadores (SMH). No es recomendación.", fontsize=7.2, color=C_MUTED)
    fig.tight_layout(rect=[0, 0.055, 1, 1])
    savefig(fig, "portfolio_vs_cspx")


def plot_multiples_bar(stats):
    keep = [
        "VOO precio (sin div.)",
        "VOO TR (30% retención no-residente)",
        "VOO TR (0% impuesto)",
        "CSPX acumulativo",
        "Portafolio rebalance anual",
        "Portafolio buy&hold",
    ]
    sub = stats[stats["serie"].isin(keep)].set_index("serie").loc[keep]
    colors = [C_VOO_PX, C_VOO_TAX, C_VOO, C_CSPX, "#E8D48B", C_PORT]
    fig, ax = plt.subplots(figsize=(11.5, 6.4), dpi=160)
    y = np.arange(len(sub))
    vals = sub["multiplo"].to_numpy()
    ax.barh(y, vals, color=colors, height=0.62, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(keep)
    ax.invert_yaxis()
    ax.set_xlabel("Múltiplo de capital a 10 años ($1 → X)")
    ax.set_title("$10.000 invertidos · valor final aproximado", loc="left", fontsize=15, pad=10)
    ax.grid(True, axis="x", alpha=0.5, zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for i, (m, final, cagr_) in enumerate(zip(vals, sub["final_10k_usd"], sub["cagr_%"])):
        ax.text(m + 0.12, i, f"{m:.2f}x   ·   ${final:,.0f}   ·   CAGR {cagr_:.1f}%", va="center", fontsize=9, color=C_TEXT)
    ax.set_xlim(0, max(vals) * 1.38)
    fig.tight_layout()
    savefig(fig, "multiples_bar")


def make_gif(series):
    s_c = series["CSPX acumulativo"]
    s_p = series["Portafolio buy&hold"]
    s_v = series["VOO TR (30% retención no-residente)"]
    df = pd.DataFrame({"cspx": s_c, "port": s_p, "voo_tax": s_v}).resample("W-FRI").last().dropna()
    frames_idx = np.linspace(8, len(df) - 1, 72).astype(int)
    fig, ax = plt.subplots(figsize=(10.8, 6.2), dpi=110)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_PANEL)
    line_v, = ax.plot([], [], color=C_VOO_TAX, lw=2.0, label="VOO after-tax 30%")
    line_c, = ax.plot([], [], color=C_CSPX, lw=2.3, label="CSPX acumulativo")
    line_p, = ax.plot([], [], color=C_PORT, lw=2.7, label="Portafolio (pesos actuales)")
    txt = ax.text(0.02, 0.96, "", transform=ax.transAxes, va="top", fontsize=11, color=C_TEXT, fontweight="bold")
    sub = ax.text(0.02, 0.88, "", transform=ax.transAxes, va="top", fontsize=9, color=C_MUTED)
    ax.set_xlim(df.index[0], df.index[-1])
    ax.set_ylim(0.7, float(df.max().max()) * 1.08)
    ax.set_ylabel("Crecimiento de $1")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"{x:.0f}x"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, axis="y", alpha=0.45)
    ax.legend(loc="upper left", bbox_to_anchor=(0.55, 0.98), frameon=False, fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_title("10 años: acumular dividendos no basta si el motor es growth", loc="left", fontsize=13)

    def update(fi):
        i = frames_idx[fi]
        sl = df.iloc[: i + 1]
        line_v.set_data(sl.index, sl["voo_tax"])
        line_c.set_data(sl.index, sl["cspx"])
        line_p.set_data(sl.index, sl["port"])
        txt.set_text(sl.index[-1].strftime("%b %Y"))
        sub.set_text(f"VOO tax30%  {sl['voo_tax'].iloc[-1]:.2f}x\nCSPX        {sl['cspx'].iloc[-1]:.2f}x\nPortafolio  {sl['port'].iloc[-1]:.2f}x")
        return line_v, line_c, line_p, txt, sub

    anim = FuncAnimation(fig, update, frames=len(frames_idx), interval=80, blit=True)
    anim.save(OUT / "portfolio_vs_cspx.gif", writer=PillowWriter(fps=12))
    plt.close(fig)


def main():
    close, adj = download()
    divs = voo_dividends(START, close.index[-1])
    print(f"ventana {close.index[0].date()} → {close.index[-1].date()}  n={len(close)}")
    print(f"dividendos VOO: {len(divs)} pagos, ${float(divs.sum()):.3f} por acción")
    voo_px = wealth_from_price(close["VOO"])
    voo_tr = wealth_from_price(adj["VOO"])
    cspx = wealth_from_price(adj["CSPX.L"])
    voo_tax = simulate_taxed_voo(close["VOO"], divs, NONRESIDENT_WH)
    port_bh = portfolio_buyhold(adj, WEIGHTS)
    port_reb = portfolio_rebalanced(adj, WEIGHTS, freq="YE")
    idx = voo_px.index.intersection(cspx.index).intersection(port_bh.index)
    series = {
        "VOO precio (sin div.)": voo_px.loc[idx],
        "VOO TR (0% impuesto)": voo_tr.loc[idx],
        "VOO TR (30% retención no-residente)": voo_tax.loc[idx],
        "CSPX acumulativo": cspx.loc[idx],
        "Portafolio buy&hold": port_bh.loc[idx],
        "Portafolio rebalance anual": port_reb.loc[idx],
    }
    comps = {k: wealth_from_price(adj[k]).loc[idx] for k in WEIGHTS}
    rows = [stats_row(name, s) for name, s in series.items()]
    rows += [stats_row(k, v) for k, v in comps.items()]
    stats = pd.DataFrame(rows)
    stats.to_csv(OUT / "stats.csv", index=False, float_format="%.3f")
    print(stats.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    out_df = pd.DataFrame(series)
    for k, v in comps.items():
        out_df[k] = v
    out_df.to_csv(OUT / "series.csv")
    plot_voo_cspx(series)
    plot_port_vs_cspx(series, comps)
    plot_multiples_bar(stats)
    make_gif(series)
    print(f"listo → {OUT}")


if __name__ == "__main__":
    main()
