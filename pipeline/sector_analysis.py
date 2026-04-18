"""
Phase 3: Sector Specialization Profile
=======================================
Computes each driver's relative strength across the three track sectors,
using their best clean lap from each race weekend.

The idea: if a driver consistently outperforms their rivals in S1 (high-speed
sweepers) but loses time in S3 (tight technical corners), that tells you
something real about their driving style — and it shows up across circuits.

Normalization approach:
    Within each session, the fastest S1 time in the field scores 1.0.
    The slowest scores 0.0. Everyone else sits in between.
    So a SectorScore of 0.85 means "85% of the way from slowest to fastest."

Outputs (written to ../data/):
    sector_weekend.parquet   — one row per driver per race weekend (raw sector scores)
    sector_profiles.parquet  — one row per driver per season (median sector scores)

Charts (written to ../data/charts/sectors/):
    radar_DRIVER.png         — spider chart of a driver's S1/S2/S3 fingerprint
    sector_heatmap.png       — all top drivers across all three sectors at a glance

Usage:
    python sector_analysis.py
    python sector_analysis.py --drivers VER HAM LEC  # radar charts for specific drivers only
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


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_race_laps() -> pd.DataFrame:
    path = DATA_DIR / "race_laps_data.parquet"
    df = pd.read_parquet(path)
    log.info(f"Loaded race laps: {len(df):,} rows, {df['Year'].nunique()} seasons")
    return df


# ---------------------------------------------------------------------------
# Select best lap per driver per weekend
# ---------------------------------------------------------------------------

def get_best_laps(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each driver at each race weekend, pick their single best clean lap.

    'Clean' here means three things:
      1. IsAccurate=True — FastF1's own flag for laps where all timing is reliable
      2. TrackStatus='1' — green flag only (safety car or VSC laps aren't representative)
      3. No pit entry/exit — the pit in/out laps have inflated times by design

    We take the minimum LapTime_s among qualifying laps as the driver's
    representative effort for that weekend.
    """
    clean = df[
        (df["IsAccurate"] == True) &
        (df["TrackStatus"] == "1") &
        (df["PitInTime_s"].isna()) &
        (df["PitOutTime_s"].isna()) &
        (df["Sector1Time_s"].notna()) &
        (df["Sector2Time_s"].notna()) &
        (df["Sector3Time_s"].notna())
    ].copy()

    # Pick the single fastest lap per driver per weekend
    best = (
        clean.sort_values("LapTime_s")
        .groupby(["Year", "Round", "Driver"], as_index=False)
        .first()
    )

    log.info(f"Best clean laps: {len(best):,} driver-weekend entries "
             f"(from {len(clean):,} clean laps)")
    return best


# ---------------------------------------------------------------------------
# Normalize sector times within each session
# ---------------------------------------------------------------------------

def normalize_sectors(best_laps: pd.DataFrame) -> pd.DataFrame:
    """
    Scale each sector time to 0-1 within the session, where 1.0 = fastest
    in the field and 0.0 = slowest.

    Using min-max per session accounts for the fact that absolute sector times
    vary wildly between circuits — a fast S1 at Monza is completely different
    from a fast S1 at Monaco.
    """
    df = best_laps.copy()

    for sector in ["Sector1Time_s", "Sector2Time_s", "Sector3Time_s"]:
        score_col = sector.replace("Time_s", "Score")

        # Compute min/max per session (year + round)
        session_stats = (
            df.groupby(["Year", "Round"])[sector]
            .agg(["min", "max"])
            .rename(columns={"min": f"{sector}_min", "max": f"{sector}_max"})
            .reset_index()
        )
        df = df.merge(session_stats, on=["Year", "Round"], how="left")

        rng = df[f"{sector}_max"] - df[f"{sector}_min"]
        # Where everyone posted the exact same time, give everyone 0.5 (neutral)
        df[score_col] = np.where(
            rng > 0,
            1.0 - (df[sector] - df[f"{sector}_min"]) / rng,
            0.5,
        )
        df.drop(columns=[f"{sector}_min", f"{sector}_max"], inplace=True)

    log.info("Sector scores normalised (1.0 = fastest in session, 0.0 = slowest)")
    return df


# ---------------------------------------------------------------------------
# Aggregate per driver per season
# ---------------------------------------------------------------------------

def compute_sector_profiles(scored: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate each driver's session-level sector scores into a season profile.

    We use median rather than mean to reduce the influence of outlier weekends
    (crashes in qualifying, unusual track conditions, etc.).
    Only include drivers with data from at least 5 weekends in the season.
    """
    agg = (
        scored.groupby(["Year", "Driver", "Team"])
        .agg(
            Rounds=("Round", "nunique"),
            S1Score=("Sector1Score", "median"),
            S2Score=("Sector2Score", "median"),
            S3Score=("Sector3Score", "median"),
        )
        .reset_index()
    )

    agg = agg[agg["Rounds"] >= 5].copy()

    # Overall pace = average of the three sector scores
    agg["OverallScore"] = agg[["S1Score", "S2Score", "S3Score"]].mean(axis=1)

    agg = agg.sort_values(["Year", "OverallScore"], ascending=[True, False])
    log.info(f"Sector profiles: {len(agg):,} driver-season entries")
    return agg


# ---------------------------------------------------------------------------
# Flag sector outliers
# ---------------------------------------------------------------------------

def flag_outliers(profiles: pd.DataFrame) -> pd.DataFrame:
    """
    Identify drivers who stand out in a specific sector relative to their
    own overall pace.

    The logic: a driver's 'sector bias' is their sector score minus their
    overall score. A large positive bias in S1 means they punch above their
    weight in high-speed corners specifically. We flag anyone who is more
    than 1 standard deviation from the field average bias.
    """
    df = profiles.copy()

    for sector, label in [("S1Score", "S1"), ("S2Score", "S2"), ("S3Score", "S3")]:
        # How much does this sector deviate from the driver's own average?
        df[f"{label}Bias"] = df[sector] - df["OverallScore"]

    # Flag: True if this driver is a clear outlier in that sector
    for bias_col in ["S1Bias", "S2Bias", "S3Bias"]:
        mean = df[bias_col].mean()
        std = df[bias_col].std()
        df[f"{bias_col}_Outlier"] = (df[bias_col] - mean).abs() > std

    outliers = df[df[["S1Bias_Outlier", "S2Bias_Outlier", "S3Bias_Outlier"]].any(axis=1)]
    log.info(f"Sector outlier entries: {len(outliers):,} (drivers strong/weak in a specific sector)")

    return df


# ---------------------------------------------------------------------------
# Visualisation helpers
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

SECTOR_LABELS = ["S1\n(High-speed)", "S2\n(Mixed)", "S3\n(Technical)"]


def plot_driver_radar(driver: str, profiles: pd.DataFrame, out_dir: Path):
    """
    Spider chart showing a driver's S1/S2/S3 scores for each season they
    appeared in. Each season is one polygon; the field average is a reference ring.
    """
    driver_data = profiles[profiles["Driver"] == driver].sort_values("Year")
    if driver_data.empty:
        log.warning(f"  No data for driver {driver}, skipping radar.")
        return

    categories = SECTOR_LABELS
    n = len(categories)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig = plt.figure(figsize=(7, 7))
    fig.patch.set_facecolor("#0d0d1a")
    ax = fig.add_subplot(111, polar=True)
    ax.set_facecolor("#1a1a2e")
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    # Reference ring: field average for each sector
    field_avg = profiles.groupby("Year")[["S1Score", "S2Score", "S3Score"]].mean()
    avg_s1 = field_avg["S1Score"].mean()
    avg_s2 = field_avg["S2Score"].mean()
    avg_s3 = field_avg["S3Score"].mean()
    ref_values = [avg_s1, avg_s2, avg_s3, avg_s1]  # close the loop
    ax.plot(angles, ref_values, color="gray", linewidth=1, linestyle="--", alpha=0.6)
    ax.fill(angles, ref_values, color="gray", alpha=0.05)

    # One line per season
    cmap = matplotlib.colormaps.get_cmap("plasma").resampled(len(driver_data))
    for idx, (_, row) in enumerate(driver_data.iterrows()):
        values = [row["S1Score"], row["S2Score"], row["S3Score"]]
        values += values[:1]
        color = cmap(idx)
        ax.plot(angles, values, color=color, linewidth=2)
        ax.fill(angles, values, color=color, alpha=0.1)
        ax.text(
            angles[0], values[0] + 0.03,
            str(int(row["Year"])),
            ha="center", va="bottom", color=color, fontsize=7,
        )

    # Chart cosmetics
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(SECTOR_LABELS, color="white", fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.5", "0.75", "1.0"], color="gray", fontsize=7)
    ax.tick_params(colors="white")
    ax.spines["polar"].set_color("#333355")
    ax.grid(color="#333355", linewidth=0.5)

    team = driver_data.iloc[-1]["Team"]
    team_color = TEAM_COLORS.get(team, "#FFFFFF")
    ax.set_title(
        f"{driver}  —  Sector Profile",
        color=team_color, fontsize=13, pad=20,
    )
    plt.tight_layout()

    out_path = out_dir / f"radar_{driver}.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    log.info(f"  Saved {out_path.name}")


def plot_sector_heatmap(profiles: pd.DataFrame, out_dir: Path):
    """
    Overview heatmap: top 20 drivers ranked by overall score,
    showing their S1/S2/S3 breakdown side-by-side.
    We use 2023 as the representative season since it has all major drivers.
    """
    year = profiles["Year"].max()
    season = profiles[profiles["Year"] == year].sort_values("OverallScore", ascending=False).head(20)

    drivers = season["Driver"].tolist()
    s1 = season["S1Score"].values
    s2 = season["S2Score"].values
    s3 = season["S3Score"].values

    data = np.vstack([s1, s2, s3])

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("#0d0d1a")
    ax.set_facecolor("#1a1a2e")

    im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=0.3, vmax=0.9)
    plt.colorbar(im, ax=ax, label="Sector Score (1.0 = fastest in session)")

    ax.set_xticks(range(len(drivers)))
    ax.set_xticklabels(drivers, color="white", rotation=45, ha="right", fontsize=9)
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["S1 (High-speed)", "S2 (Mixed)", "S3 (Technical)"], color="white")

    for i in range(3):
        for j in range(len(drivers)):
            val = data[i, j]
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color="black" if 0.35 < val < 0.75 else "white", fontsize=7)

    ax.set_title(f"Sector Scores by Driver — {year}  (green = faster than field average)",
                 color="white", fontsize=12, pad=12)
    plt.tight_layout()

    out_path = out_dir / "sector_heatmap.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    log.info(f"  Saved {out_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 sector specialization analysis")
    parser.add_argument(
        "--drivers", nargs="+", type=str, default=None,
        help="Driver abbreviations to generate radar charts for (default: top 15 overall)",
    )
    args = parser.parse_args()

    race_df = load_race_laps()

    log.info("Selecting best clean lap per driver per weekend...")
    best_laps = get_best_laps(race_df)

    log.info("Normalizing sector times within each session...")
    scored = normalize_sectors(best_laps)

    log.info("Aggregating into season profiles...")
    profiles = compute_sector_profiles(scored)

    log.info("Flagging sector outliers...")
    profiles = flag_outliers(profiles)

    # Save outputs
    keep_cols = [c for c in scored.columns if c in [
        "Year", "Round", "CircuitName", "Driver", "Team",
        "Sector1Score", "Sector2Score", "Sector3Score", "LapTime_s",
    ]]
    scored[keep_cols].to_parquet(DATA_DIR / "sector_weekend.parquet", index=False)
    profiles.to_parquet(DATA_DIR / "sector_profiles.parquet", index=False)
    log.info("Saved sector_weekend.parquet and sector_profiles.parquet")

    # Print top sector specialists
    print("\n=== TOP SECTOR SPECIALISTS (most recent season) ===")
    latest = profiles[profiles["Year"] == profiles["Year"].max()].sort_values("OverallScore", ascending=False)
    for _, row in latest.head(10).iterrows():
        print(
            f"  {row['Driver']:<6} ({row['Team']:<22})  "
            f"S1: {row['S1Score']:.3f}  S2: {row['S2Score']:.3f}  S3: {row['S3Score']:.3f}  "
            f"Overall: {row['OverallScore']:.3f}"
        )

    print("\n=== NOTABLE SECTOR SPECIALISTS ===")
    for bias, label in [("S1Bias", "S1"), ("S2Bias", "S2"), ("S3Bias", "S3")]:
        top = profiles.sort_values(bias, ascending=False).head(3)
        print(f"\nStrongest in {label}:")
        for _, row in top.iterrows():
            print(f"  {row['Driver']} ({row['Year']})  bias: +{row[bias]:.3f}")

    # Charts
    out_dir = DATA_DIR / "charts" / "sectors"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Generating sector heatmap...")
    plot_sector_heatmap(profiles, out_dir)

    # Radar charts: either the drivers passed via CLI or the top 15 by overall score
    if args.drivers:
        radar_drivers = [d.upper() for d in args.drivers]
    else:
        radar_drivers = (
            profiles.groupby("Driver")["OverallScore"]
            .mean()
            .sort_values(ascending=False)
            .head(15)
            .index.tolist()
        )

    log.info(f"Generating radar charts for {len(radar_drivers)} drivers...")
    for driver in radar_drivers:
        plot_driver_radar(driver, profiles, out_dir)

    log.info("\nPhase 3 complete.")
