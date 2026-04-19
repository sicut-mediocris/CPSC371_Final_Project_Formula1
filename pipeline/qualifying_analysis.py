"""

Team : Unsupervised Men
Sukirat Singh Dhillon, 230155722
Akshay ArulKrishnan , 230158634
Karsten Keiji Qi-Zhi Ngai-Natsuhara,230165205
Amaan Hingora, 230156282

Phase 2: Teammate Qualifying Gap Analysis
==========================================
For every race weekend, pairs each driver with their teammate (same team)
and computes the qualifying pace delta. Aggregates per driver per season
into a QualiRating — drivers who consistently beat their teammate score higher.

Using a teammate as the baseline is the cleanest way to isolate driver skill:
both drivers have the same car, same tyres, and race in the same conditions,
so any gap is purely down to the driver.

Outputs (written to ../data/):
    qualifying_ratings.parquet  — one row per driver per season
    teammate_gaps.parquet       — one row per driver per race weekend

Charts (written to ../data/charts/):
    quali_rating_YYYY.png       — top 10 rated drivers per season (2018-2024)
    quali_rating_heatmap.png    — all seasons side-by-side for top 20 drivers

Usage:
    python qualifying_analysis.py
"""

import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_qualifying() -> pd.DataFrame:
    path = DATA_DIR / "qualifying_data.parquet"
    df = pd.read_parquet(path)
    log.info(f"Loaded qualifying data: {len(df):,} rows, {df['Year'].nunique()} seasons")
    return df


# ---------------------------------------------------------------------------
# Teammate pairing
# ---------------------------------------------------------------------------

def get_best_quali_time(row) -> float | None:
    """Return the best available qualifying time, preferring Q3 > Q2 > Q1.

    We prefer the latest session because drivers typically push hardest in Q3
    (higher stakes, less tyre conservation). If a driver was knocked out early,
    we fall back to their Q2 or Q1 time so they still get a comparison.
    """
    for col in ["Q3_s", "Q2_s", "Q1_s"]:
        if col in row.index and pd.notna(row[col]) and row[col] > 0:
            return row[col]
    return None


def build_teammate_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each race weekend, pair teammates and compute the qualifying gap.
    Returns one row per driver per weekend with:
        - BestTime_s       : their best qualifying time in seconds
        - TeammateTime_s   : teammate's best time
        - GapToTeammate_s  : delta in seconds (negative = faster than teammate)
        - GapPct           : delta as % of the faster time (always >= 0)
        - BeatsTeammate    : True if this driver was faster
    """
    records = []

    for (year, round_num, team), group in df.groupby(["Year", "Round", "TeamName"]):
        if len(group) < 2:
            continue  # need at least 2 drivers to make a pair

        drivers = group.copy()
        drivers["BestTime_s"] = drivers.apply(get_best_quali_time, axis=1)
        drivers = drivers.dropna(subset=["BestTime_s"])

        if len(drivers) < 2:
            continue

        # Rare but real: mid-season substitutions sometimes put 3 drivers in one
        # team entry. Taking all pairs avoids dropping data for the sub driver.
        driver_list = drivers.to_dict("records")
        for i, d1 in enumerate(driver_list):
            for d2 in driver_list[i + 1:]:
                faster_time = min(d1["BestTime_s"], d2["BestTime_s"])

                for driver, teammate in [(d1, d2), (d2, d1)]:
                    gap_s = driver["BestTime_s"] - teammate["BestTime_s"]
                    gap_pct = abs(gap_s) / faster_time * 100

                    records.append({
                        "Year": year,
                        "Round": round_num,
                        "CircuitName": driver.get("CircuitName", ""),
                        "Driver": driver["Abbreviation"],
                        "FullName": driver.get("FullName", driver["Abbreviation"]),
                        "Team": team,
                        "Position": driver.get("Position"),
                        "BestTime_s": driver["BestTime_s"],
                        "TeammateAbbr": teammate["Abbreviation"],
                        "TeammateTime_s": teammate["BestTime_s"],
                        "GapToTeammate_s": gap_s,
                        "GapPct": gap_pct,
                        "BeatsTeammate": gap_s < 0,
                    })

    gaps_df = pd.DataFrame(records)
    log.info(f"Teammate gap pairs: {len(gaps_df):,} rows across {gaps_df['Year'].nunique()} seasons")
    return gaps_df


# ---------------------------------------------------------------------------
# Qualifying rating per driver per season
# ---------------------------------------------------------------------------

def compute_quali_ratings(gaps_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate teammate gaps per driver per season into a QualiRating.

    Methodology:
        - AvgGapPct        : mean % gap vs teammate (lower = better)
        - WinRate          : % of weekends where driver beat teammate
        - QualiRating      : 0-100 score, higher = better
          Combines WinRate (60%) and normalised AvgGapPct (40%)
    """
    agg = (
        gaps_df.groupby(["Year", "Driver", "FullName", "Team"])
        .agg(
            Races=("Round", "nunique"),
            AvgGapPct=("GapPct", "mean"),
            AvgGapToTeammate_s=("GapToTeammate_s", "mean"),
            WinRate=("BeatsTeammate", "mean"),
            Wins=("BeatsTeammate", "sum"),
        )
        .reset_index()
    )

    # Drop drivers with fewer than 3 comparisons — too small a sample to be meaningful
    agg = agg[agg["Races"] >= 3].copy()

    # Normalise within each season so a 2018 rating means "relative to 2018 grid",
    # not some absolute benchmark that changes as the sport evolves.
    for year in agg["Year"].unique():
        mask = agg["Year"] == year

        # Win rate: how often did this driver beat their teammate (0-100 scale)
        win_score = agg.loc[mask, "WinRate"] * 100

        # Gap component: invert so smaller average gap = higher score.
        # We min-max scale within the season so the worst driver scores 0 and
        # the best scores 100 — this makes seasons comparable.
        gap = agg.loc[mask, "AvgGapPct"]
        gap_min, gap_max = gap.min(), gap.max()
        if gap_max > gap_min:
            gap_score = (1 - (gap - gap_min) / (gap_max - gap_min)) * 100
        else:
            gap_score = pd.Series(50.0, index=gap.index)

        # Win rate weighted higher (60%) because it's more robust to outlier laps.
        # Gap size captures the margin of dominance — useful secondary signal.
        agg.loc[mask, "QualiRating"] = (win_score * 0.6 + gap_score * 0.4).round(1)

    agg = agg.sort_values(["Year", "QualiRating"], ascending=[True, False])
    log.info(f"Qualifying ratings computed: {len(agg):,} driver-season entries")
    return agg


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

TEAM_COLORS = {
    "Red Bull Racing": "#3671C6",
    "Ferrari": "#E8002D",
    "Mercedes": "#27F4D2",
    "McLaren": "#FF8000",
    "Aston Martin": "#229971",
    "Alpine": "#FF87BC",
    "Williams": "#64C4FF",
    "AlphaTauri": "#6692FF",
    "RB": "#6692FF",
    "Alfa Romeo": "#C92D4B",
    "Haas F1 Team": "#B6BABD",
    "Kick Sauber": "#52E252",
    "Renault": "#FFF500",
    "Racing Point": "#F596C8",
    "Toro Rosso": "#469BFF",
    "Force India": "#FF80C7",
}


def plot_top10_per_season(ratings_df: pd.DataFrame, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    seasons = sorted(ratings_df["Year"].unique())

    for year in seasons:
        season_df = (
            ratings_df[ratings_df["Year"] == year]
            .sort_values("QualiRating", ascending=False)
            .head(10)
        )

        colors = [TEAM_COLORS.get(t, "#FFFFFF") for t in season_df["Team"]]
        labels = season_df.apply(
            lambda r: f"{r['Driver']}  ({r['Team'].split()[0]})", axis=1
        )

        fig, ax = plt.subplots(figsize=(12, 6))
        fig.patch.set_facecolor("#0d0d1a")
        ax.set_facecolor("#1a1a2e")

        bars = ax.barh(labels[::-1], season_df["QualiRating"][::-1], color=colors[::-1])

        for bar, val in zip(bars, season_df["QualiRating"][::-1]):
            ax.text(
                bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}", va="center", color="white", fontsize=9,
            )

        ax.set_xlabel("Qualifying Rating (0-100)", color="white")
        ax.set_title(
            f"Top 10 Qualifying Pace Ratings vs Teammate — {year}",
            color="white", fontsize=13, pad=12,
        )
        ax.tick_params(colors="white")
        ax.set_xlim(0, 110)
        plt.tight_layout()

        out_path = out_dir / f"quali_rating_{year}.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close()
        log.info(f"  Saved {out_path.name}")


def plot_all_seasons_overview(ratings_df: pd.DataFrame, out_dir: Path):
    """Heatmap — driver vs season QualiRating for consistently top drivers."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # Keep drivers who appear in at least 3 seasons
    driver_counts = ratings_df.groupby("Driver")["Year"].nunique()
    top_drivers = driver_counts[driver_counts >= 3].index

    pivot = (
        ratings_df[ratings_df["Driver"].isin(top_drivers)]
        .pivot_table(index="Driver", columns="Year", values="QualiRating")
    )

    # Sort by mean rating descending
    pivot = pivot.loc[pivot.mean(axis=1).sort_values(ascending=False).index]
    pivot = pivot.head(20)  # top 20 drivers

    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor("#0d0d1a")
    ax.set_facecolor("#1a1a2e")

    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)
    plt.colorbar(im, ax=ax, label="QualiRating")

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, color="white")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, color="white")

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.iloc[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                        color="black" if 30 < val < 80 else "white", fontsize=8)

    ax.set_title("Qualifying Rating Heatmap — 2018 to 2024\n(green = consistently beats teammate)",
                 color="white", fontsize=12, pad=12)
    plt.tight_layout()

    out_path = out_dir / "quali_rating_heatmap.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    log.info(f"  Saved {out_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    quali_df = load_qualifying()

    log.info("Building teammate gap pairs...")
    gaps_df = build_teammate_gaps(quali_df)

    log.info("Computing qualifying ratings...")
    ratings_df = compute_quali_ratings(gaps_df)

    # Save outputs
    gaps_df.to_parquet(DATA_DIR / "teammate_gaps.parquet", index=False)
    ratings_df.to_parquet(DATA_DIR / "qualifying_ratings.parquet", index=False)
    log.info("Saved teammate_gaps.parquet and qualifying_ratings.parquet")

    # Print top 5 per season
    print("\n=== TOP 5 QUALIFYING RATINGS PER SEASON ===")
    for year in sorted(ratings_df["Year"].unique()):
        top5 = ratings_df[ratings_df["Year"] == year].head(5)
        print(f"\n{year}:")
        for _, row in top5.iterrows():
            print(f"  {row['Driver']:<6} ({row['Team']:<20}) "
                  f"Rating: {row['QualiRating']:5.1f}  "
                  f"WinRate: {row['WinRate']*100:.0f}%  "
                  f"AvgGap: {row['AvgGapToTeammate_s']*1000:.0f}ms")

    # Charts
    log.info("Generating charts...")
    charts_dir = DATA_DIR / "charts"
    plot_top10_per_season(ratings_df, charts_dir)
    plot_all_seasons_overview(ratings_df, charts_dir)

    log.info("\nPhase 2 complete.")
