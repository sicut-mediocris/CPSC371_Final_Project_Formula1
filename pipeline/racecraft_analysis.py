"""

Team : Unsupervised Men
Sukirat Singh Dhillon, 230155722
Akshay ArulKrishnan , 230158634
Karsten Keiji Qi-Zhi Ngai-Natsuhara,230165205
Amaan Hingora, 230156282

Phase 5: Tire Degradation & Race Craft Score
=============================================
Measures how gently each driver manages their tyres and how consistent their
pace is over a race stint — two signals that reflect racecraft rather than
raw qualifying speed.

The core idea: two teammates in the same car on the same compound will still
show different degradation rates if one is harder on the rubber. That
difference is the driver. We control for the car by normalising each driver's
degradation against their teammate in the same race.

Degradation method:
    For each stint with enough clean green-flag laps, fit a linear regression
    of LapTime_s vs TyreLife. The slope is degradation: how many extra seconds
    per lap the driver loses as the tyre wears. A shallower slope = gentler on tyres.

Consistency method:
    Standard deviation of lap times across all clean green-flag laps in the race
    (excluding pit in/out laps and safety car periods). Lower std = more consistent.

RaceCraftScore (0-100):
    Combines normalised degradation (40%) and normalised consistency (60%).
    Normalised within each season so scores reflect performance vs that year's grid.

Outputs (written to ../data/):
    stint_regressions.parquet  — one row per stint with slope, r², lap count
    race_craft.parquet         — one row per driver per season with RaceCraftScore

Charts (written to ../data/charts/racecraft/):
    degradation_scatter.png    — avg degradation vs consistency for all drivers
    racecraft_YYYY.png         — top 10 RaceCraftScore per season bar chart
    stint_example_DRIVER.png   — example stint progression for a specific driver

Usage:
    python racecraft_analysis.py
    python racecraft_analysis.py --example-driver VER   # show VER's stint chart
"""

import argparse
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Paths & logging
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

# Minimum green-flag laps in a stint before we trust the regression.
# Below this the slope is too noisy to mean anything.
MIN_STINT_LAPS = 5

# Wet/intermediate tyres behave completely differently — exclude them since
# degradation there reflects rain conditions more than driver input.
DRY_COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "SUPERSOFT", "ULTRASOFT",
                 "HYPERSOFT", "PIRELLI"}

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


# ---------------------------------------------------------------------------
# Load & clean
# ---------------------------------------------------------------------------

def load_race_laps() -> pd.DataFrame:
    path = DATA_DIR / "race_laps_data.parquet"
    df = pd.read_parquet(path)
    log.info(f"Loaded race laps: {len(df):,} rows across {df['Year'].nunique()} seasons")
    return df


def get_clean_laps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only laps where the lap time is a fair reflection of driver pace.

    We exclude:
    - TrackStatus != '1'  : any yellow flag, safety car, or VSC period distorts times
    - Pit in/out laps     : the pit stop lap and the slow out-lap are not representative
    - Wet compounds       : rain changes tyre physics entirely; can't compare with dry stints
    - IsAccurate == False : FastF1 flags laps with timing issues
    - LapTime_s < 60      : catches any data corruption (no F1 lap is under a minute)
    """
    clean = df[
        (df["TrackStatus"] == "1") &
        (df["PitInTime_s"].isna()) &
        (df["PitOutTime_s"].isna()) &
        (df["IsAccurate"] == True) &
        (df["LapTime_s"].notna()) &
        (df["LapTime_s"] > 60) &
        (df["Compound"].isin(DRY_COMPOUNDS))
    ].copy()

    log.info(f"Clean green-flag laps: {len(clean):,} "
             f"(from {len(df):,} total, {len(df)-len(clean):,} excluded)")
    return clean


# ---------------------------------------------------------------------------
# Stint regression
# ---------------------------------------------------------------------------

def fit_stint_regressions(clean: pd.DataFrame) -> pd.DataFrame:
    """
    For every driver stint with enough laps, fit LapTime_s ~ TyreLife.

    The slope is the degradation rate in seconds-per-lap. A positive slope
    means the driver is getting slower as the tyre wears — the steeper it is,
    the harder they're going through the rubber.

    We also record r² so downstream steps can weight or filter by how well
    the linear model actually fits (some stints have non-linear degradation).
    """
    records = []

    groups = clean.groupby(["Year", "Round", "Driver", "Team", "Stint", "Compound"])
    for (year, round_num, driver, team, stint, compound), group in groups:
        group = group.sort_values("TyreLife")
        if len(group) < MIN_STINT_LAPS:
            continue

        x = group["TyreLife"].values
        y = group["LapTime_s"].values

        result = stats.linregress(x, y)

        records.append({
            "Year":        year,
            "Round":       round_num,
            "CircuitName": group["CircuitName"].iloc[0],
            "Driver":      driver,
            "Team":        team,
            "Stint":       stint,
            "Compound":    compound,
            "Laps":        len(group),
            "Slope":       result.slope,       # degradation rate (s/lap)
            "Intercept":   result.intercept,   # predicted lap time at tyre life = 0
            "R2":          result.rvalue ** 2, # how well linear model fits the stint
            "MedianLapTime_s": np.median(y),
        })

    df = pd.DataFrame(records)
    log.info(f"Stint regressions: {len(df):,} stints across "
             f"{df['Year'].nunique()} seasons, {df['Driver'].nunique()} drivers")
    return df


# ---------------------------------------------------------------------------
# Consistency score
# ---------------------------------------------------------------------------

def compute_consistency(clean: pd.DataFrame) -> pd.DataFrame:
    """
    Lap time consistency = std deviation of clean lap times per driver per race.

    Lower std means the driver is putting in more uniform laps — a sign of
    smooth, controlled driving that doesn't burn through tyres unevenly.
    We use coefficient of variation (std / mean) so that faster circuits
    (shorter absolute lap times) don't automatically look more consistent.
    """
    agg = (
        clean.groupby(["Year", "Round", "Driver", "Team"])
        .agg(
            CleanLaps=("LapTime_s", "count"),
            StdLapTime=("LapTime_s", "std"),
            MeanLapTime=("LapTime_s", "mean"),
        )
        .reset_index()
    )
    # Coefficient of variation: std as % of mean lap time
    agg["CV"] = agg["StdLapTime"] / agg["MeanLapTime"] * 100
    return agg[agg["CleanLaps"] >= 5]   # need at least 5 clean laps per race


# ---------------------------------------------------------------------------
# Teammate normalisation
# ---------------------------------------------------------------------------

def normalise_vs_teammate(stints: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise each driver's average degradation slope relative to their
    teammate in the same race. This strips out any circuit or car effects
    (both teammates run the same car on the same track).

    RelativeDeg = (driver_slope - teammate_slope) / max(|teammate_slope|, 0.001)

    Negative = driver degrades less than teammate = better tyre management.
    """
    # Average slope per driver per race (across all their stints that round)
    per_race = (
        stints.groupby(["Year", "Round", "Driver", "Team"])
        .agg(AvgSlope=("Slope", "mean"), Stints=("Stint", "nunique"))
        .reset_index()
    )

    records = []
    for (year, round_num, team), group in per_race.groupby(["Year", "Round", "Team"]):
        if len(group) < 2:
            continue
        driver_list = group.to_dict("records")
        for i, d1 in enumerate(driver_list):
            for d2 in driver_list[i + 1:]:
                for driver, teammate in [(d1, d2), (d2, d1)]:
                    rel = ((driver["AvgSlope"] - teammate["AvgSlope"])
                           / max(abs(teammate["AvgSlope"]), 0.001))
                    records.append({
                        "Year":        year,
                        "Round":       round_num,
                        "Team":        team,
                        "Driver":      driver["Driver"],
                        "TeammateDriver": teammate["Driver"],
                        "AvgSlope":    driver["AvgSlope"],
                        "TeammateSlope": teammate["AvgSlope"],
                        "RelativeDeg": rel,   # negative = better
                    })

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Season-level RaceCraftScore
# ---------------------------------------------------------------------------

def compute_racecraft_score(stints: pd.DataFrame,
                            consistency: pd.DataFrame) -> pd.DataFrame:
    """
    Combine degradation and consistency into a single season score.

    Steps:
    1. Average each driver's degradation slope and consistency CV per season
    2. Normalise both within the season to 0-100 (better = higher)
    3. Weighted sum: consistency 60%, degradation 40%
       Consistency is weighted higher because it's available for every race;
       degradation requires a usable stint of 5+ clean laps and is noisier.
    """
    # Per-season degradation: median slope per driver (median to ignore outlier stints)
    deg_season = (
        stints.groupby(["Year", "Driver", "Team"])
        .agg(MedianSlope=("Slope", "median"), StintCount=("Stint", "count"))
        .reset_index()
    )
    deg_season = deg_season[deg_season["StintCount"] >= 3]  # need a few stints

    # Per-season consistency: mean CV across races
    con_season = (
        consistency.groupby(["Year", "Driver"])
        .agg(AvgCV=("CV", "mean"), Races=("Round", "nunique"))
        .reset_index()
    )
    con_season = con_season[con_season["Races"] >= 5]

    merged = deg_season.merge(con_season, on=["Year", "Driver"], how="inner")

    scored_seasons = []
    for year in merged["Year"].unique():
        m = merged[merged["Year"] == year].copy()

        # Degradation score: invert (lower slope = less degradation = better)
        slope = m["MedianSlope"]
        s_min, s_max = slope.min(), slope.max()
        if s_max > s_min:
            m["DegScore"] = (1 - (slope - s_min) / (s_max - s_min)) * 100
        else:
            m["DegScore"] = 50.0

        # Consistency score: invert (lower CV = more consistent = better)
        cv = m["AvgCV"]
        cv_min, cv_max = cv.min(), cv.max()
        if cv_max > cv_min:
            m["ConScore"] = (1 - (cv - cv_min) / (cv_max - cv_min)) * 100
        else:
            m["ConScore"] = 50.0

        m["RaceCraftScore"] = (m["ConScore"] * 0.6 + m["DegScore"] * 0.4).round(1)
        scored_seasons.append(m)

    result = pd.concat(scored_seasons, ignore_index=True)
    result = result.sort_values(["Year", "RaceCraftScore"], ascending=[True, False])
    log.info(f"RaceCraftScore computed: {len(result):,} driver-season entries")
    return result


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def plot_racecraft_per_season(scores: pd.DataFrame, out_dir: Path):
    """Top 10 RaceCraftScore bar chart per season."""
    for year in sorted(scores["Year"].unique()):
        top10 = scores[scores["Year"] == year].head(10)
        colors = [TEAM_COLORS.get(t, "#FFFFFF") for t in top10["Team"]]
        labels = top10.apply(
            lambda r: f"{r['Driver']}  ({r['Team'].split()[0]})", axis=1
        )

        fig, ax = plt.subplots(figsize=(12, 6))
        fig.patch.set_facecolor("#0d0d1a")
        ax.set_facecolor("#1a1a2e")

        bars = ax.barh(labels[::-1], top10["RaceCraftScore"][::-1],
                       color=colors[::-1])
        for bar, val in zip(bars, top10["RaceCraftScore"][::-1]):
            ax.text(bar.get_width() + 0.5,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}", va="center", color="white", fontsize=9)

        ax.set_xlabel("Race Craft Score (0-100)", color="white")
        ax.set_title(f"Top 10 Race Craft Scores — {year}",
                     color="white", fontsize=13, pad=12)
        ax.set_xlim(0, 110)
        ax.tick_params(colors="white")
        plt.tight_layout()

        out_path = out_dir / f"racecraft_{year}.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close()
        log.info(f"  Saved {out_path.name}")


def plot_degradation_scatter(scores: pd.DataFrame, out_dir: Path):
    """
    Scatter of degradation score vs consistency score for the most recent season.
    Top-right quadrant = best on both dimensions.
    """
    latest = scores[scores["Year"] == scores["Year"].max()]

    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_facecolor("#0d0d1a")
    ax.set_facecolor("#1a1a2e")

    for _, row in latest.iterrows():
        color = TEAM_COLORS.get(row["Team"], "#FFFFFF")
        ax.scatter(row["ConScore"], row["DegScore"], color=color, s=80, zorder=3)
        ax.annotate(row["Driver"],
                    (row["ConScore"], row["DegScore"]),
                    textcoords="offset points", xytext=(6, 4),
                    color="white", fontsize=8)

    ax.axhline(50, color="gray", linewidth=0.6, linestyle="--")
    ax.axvline(50, color="gray", linewidth=0.6, linestyle="--")
    ax.set_xlabel("Consistency Score  (higher = more uniform lap times)", color="white")
    ax.set_ylabel("Degradation Score  (higher = gentler on tyres)", color="white")
    ax.set_title(f"Race Craft — Degradation vs Consistency  ({latest['Year'].iloc[0]})",
                 color="white", fontsize=12, pad=12)
    ax.tick_params(colors="white")
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 105)

    # Label quadrants
    for x, y, label in [(25, 90, "Consistent\nbut eats tyres"),
                         (75, 90, "Consistent\nAND easy on tyres"),
                         (25, 10, "Inconsistent\nAND hard on tyres"),
                         (75, 10, "Hard on tyres\nbut consistent")]:
        ax.text(x, y, label, color="gray", fontsize=7, ha="center", alpha=0.7)

    plt.tight_layout()
    out_path = out_dir / "degradation_scatter.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    log.info(f"  Saved {out_path.name}")


def plot_stint_example(stints_raw: pd.DataFrame, clean_laps: pd.DataFrame,
                       driver: str, out_dir: Path):
    """
    Show the actual lap time progression for one driver across all their stints
    in their best-data season. Each stint is one line; the regression fit overlaid.
    """
    driver_stints = stints_raw[stints_raw["Driver"] == driver]
    if driver_stints.empty:
        log.warning(f"  No stint data for {driver}, skipping example chart.")
        return

    # Pick the season with most stints for this driver
    best_year = driver_stints.groupby("Year")["Stint"].count().idxmax()
    driver_stints = driver_stints[driver_stints["Year"] == best_year]
    clean_driver = clean_laps[
        (clean_laps["Driver"] == driver) & (clean_laps["Year"] == best_year)
    ]

    fig, ax = plt.subplots(figsize=(13, 5))
    fig.patch.set_facecolor("#0d0d1a")
    ax.set_facecolor("#1a1a2e")

    team = driver_stints["Team"].iloc[0]
    base_color = TEAM_COLORS.get(team, "#E10600")
    cmap = matplotlib.colormaps.get_cmap("plasma").resampled(len(driver_stints))

    for idx, (_, stint_row) in enumerate(driver_stints.iterrows()):
        round_num = stint_row["Round"]
        stint_num = stint_row["Stint"]

        laps = clean_driver[
            (clean_driver["Round"] == round_num) &
            (clean_driver["Stint"] == stint_num)
        ].sort_values("TyreLife")

        if len(laps) < 2:
            continue

        color = cmap(idx)
        ax.scatter(laps["TyreLife"], laps["LapTime_s"],
                   color=color, s=18, alpha=0.7, zorder=3)

        # Overlay the regression line
        x_fit = np.linspace(laps["TyreLife"].min(), laps["TyreLife"].max(), 50)
        y_fit = stint_row["Slope"] * x_fit + stint_row["Intercept"]
        ax.plot(x_fit, y_fit, color=color, linewidth=1.5, alpha=0.9,
                label=f"R{int(round_num)} S{int(stint_num)} "
                      f"({stint_row['Compound'][:3]}) "
                      f"slope={stint_row['Slope']:+.3f}s/lap")

    ax.set_xlabel("Tyre Life (laps on tyre)", color="white")
    ax.set_ylabel("Lap Time (s)", color="white")
    ax.set_title(f"{driver} — Stint Degradation Profiles  ({best_year})",
                 color="white", fontsize=12, pad=10)
    ax.tick_params(colors="white")
    ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=7,
              loc="upper left", ncol=2)
    plt.tight_layout()

    out_path = out_dir / f"stint_example_{driver}.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    log.info(f"  Saved {out_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 race craft analysis")
    parser.add_argument("--example-driver", type=str, default="VER",
                        help="Driver to show stint progression chart for (default: VER)")
    args = parser.parse_args()

    race_df = load_race_laps()

    log.info("Filtering to clean green-flag laps...")
    clean = get_clean_laps(race_df)

    log.info("Fitting stint regressions...")
    stints = fit_stint_regressions(clean)

    log.info("Computing consistency scores...")
    consistency = compute_consistency(clean)

    log.info("Normalising degradation vs teammate...")
    teammate_norm = normalise_vs_teammate(stints)

    log.info("Computing season RaceCraftScores...")
    scores = compute_racecraft_score(stints, consistency)

    # Save outputs
    stints.to_parquet(DATA_DIR / "stint_regressions.parquet", index=False)
    scores.to_parquet(DATA_DIR / "race_craft.parquet", index=False)
    teammate_norm.to_parquet(DATA_DIR / "degradation_vs_teammate.parquet", index=False)
    log.info("Saved stint_regressions.parquet, race_craft.parquet, "
             "degradation_vs_teammate.parquet")

    # Print top 5 per season
    print("\n=== TOP 5 RACE CRAFT SCORES PER SEASON ===")
    for year in sorted(scores["Year"].unique()):
        top5 = scores[scores["Year"] == year].head(5)
        print(f"\n{year}:")
        for _, row in top5.iterrows():
            print(f"  {row['Driver']:<6} ({row['Team']:<22})  "
                  f"RaceCraft: {row['RaceCraftScore']:5.1f}  "
                  f"DegScore: {row['DegScore']:.1f}  "
                  f"ConScore: {row['ConScore']:.1f}")

    print("\n=== TEAMMATE DEGRADATION COMPARISON (top 5 best vs teammate) ===")
    avg_rel = (
        teammate_norm.groupby("Driver")["RelativeDeg"]
        .mean()
        .sort_values()
        .head(5)
    )
    for driver, val in avg_rel.items():
        print(f"  {driver:<6}  {val:+.3f}  (negative = degrades less than teammate)")

    # Charts
    out_dir = DATA_DIR / "charts" / "racecraft"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("\nGenerating season bar charts...")
    plot_racecraft_per_season(scores, out_dir)

    log.info("Generating degradation scatter...")
    plot_degradation_scatter(scores, out_dir)

    log.info(f"Generating stint example for {args.example_driver}...")
    plot_stint_example(stints, clean, args.example_driver.upper(), out_dir)

    log.info("\nPhase 5 complete.")
