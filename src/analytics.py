"""Run the SQL in sql/ against the warehouse and save results + charts to reports/.

Usage: python -m src.analytics
"""
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.etl.config import ROOT, load_config

SQL_DIR = ROOT / "sql"
REPORTS = ROOT / "reports"
COLORS = ["#2563eb", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#64748b"]


def run_queries(con) -> dict:
    results = {}
    for path in sorted(SQL_DIR.glob("*.sql")):
        df = con.execute(path.read_text()).df()
        df.to_csv(REPORTS / f"{path.stem}.csv", index=False)
        results[path.stem] = df
    return results


def style(ax, title, xlabel="", ylabel=""):
    ax.set_title(title, fontsize=13, fontweight="bold", loc="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(REPORTS / name, dpi=130)
    plt.close(fig)


def make_charts(r: dict):
    hourly = r["hourly_demand"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for weekend, color, label in [(False, COLORS[0], "Weekday"), (True, COLORS[1], "Weekend")]:
        part = hourly[hourly["is_weekend"] == weekend]
        ax.plot(part["pickup_hour"], part["avg_trips"], "o-", color=color, label=label, lw=2)
    ax.set_xticks(range(0, 24, 2))
    ax.legend(frameon=False)
    style(ax, "Average trips per hour of day", "pickup hour", "trips per day-hour")
    save(fig, "hourly_demand.png")

    boro = r["revenue_by_borough"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(boro["borough"], boro["revenue_usd"] / 1e6, color=COLORS[0])
    for i, v in enumerate(boro["revenue_usd"]):
        ax.text(i, v / 1e6, f"${v / 1e6:,.1f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K", ha="center", va="bottom", fontsize=9)
    style(ax, "Revenue by pickup borough (Jan–Mar 2024)", "", "revenue (USD millions)")
    save(fig, "revenue_by_borough.png")

    rej = r["rejection_breakdown"].sort_values("rows_rejected")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(rej["reason"], rej["rows_rejected"], color=COLORS[3])
    for i, (v, p) in enumerate(zip(rej["rows_rejected"], rej["pct_of_extracted"])):
        ax.text(v, i, f"  {v:,} ({p}%)" if p >= 0.001 else f"  {v:,} (<0.001%)", va="center", fontsize=9)
    ax.set_xlim(0, rej["rows_rejected"].max() * 1.3)
    style(ax, "Quarantined records by rejection rule", "rows", "")
    ax.grid(axis="x", alpha=0.3)
    ax.grid(axis="y", visible=False)
    save(fig, "rejection_breakdown.png")

    daily = r["daily_trips"]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(daily["date"], daily["trips"] / 1000, color=COLORS[0], lw=1.8)
    wk = daily[daily["is_weekend"]]
    ax.scatter(wk["date"], wk["trips"] / 1000, color=COLORS[1], s=18, zorder=3, label="weekend")
    ax.legend(frameon=False)
    style(ax, "Daily trips", "", "trips (thousands)")
    save(fig, "daily_trips.png")


def main():
    REPORTS.mkdir(exist_ok=True)
    con = duckdb.connect(load_config()["warehouse_path"], read_only=True)
    results = run_queries(con)
    make_charts(results)
    for name, df in results.items():
        print(f"\n== {name}\n{df.head(12).to_string(index=False)}")


if __name__ == "__main__":
    main()
