"""
Phase 6: Composite SkillScore & Elo Driver Rating
===================================================
Combines the four skill signals from Phases 2-5 into a unified driver rating,
then builds an Elo system that tracks driver ability across seasons.

Signal weights (when all four are available):
    Qualifying pace     35%   — most car-independent, clearest signal
    Sector profile      20%   — where on track a driver is fast
    Telemetry signals   25%   — brake points + corner speed (2023 only)
    Race craft          20%   — tyre management + consistency

For seasons without telemetry data (2018-2022, 2024), the 25% telemetry
weight is redistributed proportionally across the other three.

Elo system:
    Starts every driver at 1500. After each race weekend, updates based on
    the qualifying head-to-head vs teammate (same car = fair comparison).
    Standard chess Elo formula with K=32.

Outputs (written to ../data/):
    skill_scores.parquet   — composite SkillScore per driver per season
    elo_history.parquet    — Elo rating after every race weekend

Charts (written to ../data/charts/elo/):
    elo_trajectory.png     — Elo over time for top 10 drivers (2018-2024)
    skill_score_YYYY.png   — bar chart of composite SkillScore per season

Usage:
    python elo_rating.py
"""

import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

TEAM_COLORS = {
    "Red Bull Racing": "#3671C6", "Ferrari": "#E8002D", "Mercedes": "#27F4D2",
    "McLaren": "#FF8000", "Aston Martin": "#229971", "Alpine": "#FF87BC",
    "Williams": "#64C4FF", "AlphaTauri": "#6692FF", "RB": "#6692FF",
    "Alfa Romeo": "#C92D4B", "Haas F1 Team": "#B6BABD", "Kick Sauber": "#52E252",
    "Renault": "#FFF500", "Racing Point": "#F596C8", "Toro Rosso": "#469BFF",
    "Force India": "#FF80C7", "Alfa Romeo Racing": "#C92D4B",
}


# ---------------------------------------------------------------------------
# Load all phase outputs
# ---------------------------------------------------------------------------

def load_all() -> dict:
    return {
        "quali":     pd.read_parquet(DATA_DIR / "qualifying_ratings.parquet"),
        "sector":    pd.read_parquet(DATA_DIR / "sector_profiles.parquet"),
        "telemetry": pd.read_parquet(DATA_DIR / "telemetry_signals.parquet"),
        "racecraft": pd.read_parquet(DATA_DIR / "race_craft.parquet"),
        "gaps":      pd.read_parquet(DATA_DIR / "teammate_gaps.parquet"),
    }


# ---------------------------------------------------------------------------
# Build telemetry season score (collapse per-corner data to per-driver)
# ---------------------------------------------------------------------------

def build_telemetry_score(tel: pd.DataFrame) -> pd.DataFrame:
    """
    Telemetry signals are per-corner. Aggregate to one score per driver
    by averaging their normalised brake point and corner speed z-scores,
    then scale to 0-100 within the season.

    We combine brake point and corner speed (both higher = better) and
    ignore throttle point since its coverage is patchier across circuits.
    """
    per_driver = (
        tel.groupby(["Year", "Driver", "Team"])
        .agg(
            AvgBrakeNorm=("brake_point_m_norm", "mean"),
            AvgSpeedNorm=("min_speed_kmh_norm", "mean"),
        )
        .reset_index()
    )
    per_driver["RawTelScore"] = (per_driver["AvgBrakeNorm"] +
                                  per_driver["AvgSpeedNorm"]) / 2

    # Scale to 0-100 within each season
    for year in per_driver["Year"].unique():
        mask = per_driver["Year"] == year
        raw = per_driver.loc[mask, "RawTelScore"]
        rng = raw.max() - raw.min()
        if rng > 0:
            per_driver.loc[mask, "TelScore"] = (
                (raw - raw.min()) / rng * 100
            )
        else:
            per_driver.loc[mask, "TelScore"] = 50.0

    return per_driver[["Year", "Driver", "Team", "TelScore"]]


# ---------------------------------------------------------------------------
# Composite SkillScore
# ---------------------------------------------------------------------------

def compute_skill_scores(data: dict) -> pd.DataFrame:
    """
    Merge all four signal scores and compute a weighted composite.

    Sector OverallScore is on a 0-1 scale — convert to 0-100 first.
    Telemetry is only available for 2023, so the weights are redistributed
    for all other seasons:
        With telemetry:    quali 35% / sector 20% / telemetry 25% / racecraft 20%
        Without telemetry: quali 46.7% / sector 26.7% / racecraft 26.7%
        (the 25% is split proportionally across the remaining three)
    """
    quali = data["quali"][["Year", "Driver", "Team", "QualiRating"]].copy()

    sector = data["sector"][["Year", "Driver", "Team", "OverallScore"]].copy()
    sector["SectorScore"] = sector["OverallScore"] * 100  # scale 0-1 -> 0-100

    tel_score = build_telemetry_score(data["telemetry"])

    racecraft = data["racecraft"][["Year", "Driver", "Team", "RaceCraftScore"]].copy()

    # Merge — left join on quali as the broadest dataset
    merged = quali.merge(
        sector[["Year", "Driver", "SectorScore"]], on=["Year", "Driver"], how="left"
    ).merge(
        tel_score[["Year", "Driver", "TelScore"]], on=["Year", "Driver"], how="left"
    ).merge(
        racecraft[["Year", "Driver", "RaceCraftScore"]], on=["Year", "Driver"], how="left"
    )

    records = []
    for _, row in merged.iterrows():
        has_tel = pd.notna(row.get("TelScore"))

        signals = {}
        if pd.notna(row.get("QualiRating")):
            signals["QualiRating"] = row["QualiRating"]
        if pd.notna(row.get("SectorScore")):
            signals["SectorScore"] = row["SectorScore"]
        if has_tel:
            signals["TelScore"] = row["TelScore"]
        if pd.notna(row.get("RaceCraftScore")):
            signals["RaceCraftScore"] = row["RaceCraftScore"]

        if not signals:
            continue

        # Define target weights
        base_weights = {
            "QualiRating":   0.35,
            "SectorScore":   0.20,
            "TelScore":      0.25,
            "RaceCraftScore": 0.20,
        }
        # Keep only weights for signals we have, then renormalise
        active = {k: base_weights[k] for k in signals}
        total_w = sum(active.values())
        norm_w = {k: v / total_w for k, v in active.items()}

        skill = sum(signals[k] * norm_w[k] for k in signals)

        records.append({
            "Year":        row["Year"],
            "Driver":      row["Driver"],
            "Team":        row["Team"],
            "QualiRating": row.get("QualiRating"),
            "SectorScore": row.get("SectorScore"),
            "TelScore":    row.get("TelScore"),
            "RaceCraftScore": row.get("RaceCraftScore"),
            "SignalCount":  len(signals),
            "SkillScore":   round(skill, 2),
        })

    df = pd.DataFrame(records)
    df = df.sort_values(["Year", "SkillScore"], ascending=[True, False])
    log.info(f"SkillScore computed: {len(df):,} driver-season entries")
    return df


# ---------------------------------------------------------------------------
# Elo rating system
# ---------------------------------------------------------------------------

ELO_START = 1500
ELO_K     = 32


def _expected(r_a: float, r_b: float) -> float:
    """Standard Elo expected score for player A vs player B."""
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400))


def run_elo(gaps: pd.DataFrame) -> pd.DataFrame:
    """
    Walk through every race weekend in chronological order and update driver
    Elo ratings based on qualifying head-to-head results vs teammates.

    Using qualifying as the match result keeps it car-independent — same car,
    same conditions, any gap is purely the driver. Win = 1.0, loss = 0.0.

    Returns one row per driver per race weekend showing their Elo after that event.
    """
    ratings: dict[str, float] = {}
    history = []

    # Filter to real 3-letter driver codes — some FastF1 results include
    # reserve/test driver entries with unusual abbreviations.
    gaps = gaps[gaps["Driver"].str.len() == 3].copy()

    # Sort chronologically
    ordered = gaps.sort_values(["Year", "Round"]).copy()

    for (year, round_num), weekend in ordered.groupby(["Year", "Round"]):
        # Process each team's pair for this weekend
        for _, row in weekend.iterrows():
            driver  = row["Driver"]
            teammate = row["TeammateAbbr"]

            r_a = ratings.get(driver,   ELO_START)
            r_b = ratings.get(teammate, ELO_START)

            expected_a = _expected(r_a, r_b)
            actual_a   = 1.0 if row["BeatsTeammate"] else 0.0

            new_r_a = r_a + ELO_K * (actual_a - expected_a)
            ratings[driver] = new_r_a

        # Record all drivers' ratings after this weekend
        for driver, rating in ratings.items():
            history.append({
                "Year":       year,
                "Round":      round_num,
                "CircuitName": weekend["CircuitName"].iloc[0]
                               if "CircuitName" in weekend.columns else "",
                "Driver":     driver,
                "Elo":        round(rating, 2),
            })

    df = pd.DataFrame(history)
    log.info(f"Elo history: {len(df):,} driver-weekend entries, "
             f"{df['Driver'].nunique()} drivers tracked")
    return df


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def plot_elo_trajectory(elo: pd.DataFrame, skill: pd.DataFrame, out_dir: Path):
    """
    Line chart of Elo rating over all race weekends for the top 10 drivers
    by final Elo rating. Each driver gets their team color from their last season.
    """
    # Pick top 10 by final Elo
    final = elo.groupby("Driver")["Elo"].last().sort_values(ascending=False)
    top10 = final.head(10).index.tolist()

    # Build a sequential x-axis from (Year, Round)
    timeline = (
        elo[["Year", "Round"]].drop_duplicates()
        .sort_values(["Year", "Round"])
        .reset_index(drop=True)
    )
    timeline["X"] = timeline.index

    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor("#0d0d1a")
    ax.set_facecolor("#1a1a2e")

    for driver in top10:
        d_elo = elo[elo["Driver"] == driver].merge(timeline, on=["Year", "Round"])
        # Get team from skill scores (last known team)
        team_rows = skill[skill["Driver"] == driver]
        team = team_rows["Team"].iloc[-1] if not team_rows.empty else ""
        color = TEAM_COLORS.get(team, "#FFFFFF")

        ax.plot(d_elo["X"], d_elo["Elo"], color=color, linewidth=1.8, label=driver)
        # Label at end of line
        ax.text(d_elo["X"].iloc[-1] + 1, d_elo["Elo"].iloc[-1],
                driver, color=color, fontsize=8, va="center")

    # Mark season boundaries
    for year in sorted(elo["Year"].unique()):
        first_x = timeline[timeline["Year"] == year]["X"].min()
        ax.axvline(first_x, color="#333355", linewidth=0.8, linestyle="--")
        ax.text(first_x + 0.5, ax.get_ylim()[0] + 5, str(year),
                color="gray", fontsize=8)

    ax.axhline(ELO_START, color="gray", linewidth=0.6, linestyle=":", alpha=0.5)
    ax.set_ylabel("Elo Rating", color="white")
    ax.set_xlabel("Race Weekend (chronological)", color="white")
    ax.set_title("F1 Driver Elo Rating — 2018 to 2024  (based on qualifying vs teammate)",
                 color="white", fontsize=13, pad=12)
    ax.tick_params(colors="white")
    ax.legend(facecolor="#1a1a2e", labelcolor="white", fontsize=8,
              loc="upper left", ncol=2)
    plt.tight_layout()

    out_path = out_dir / "elo_trajectory.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    log.info(f"  Saved {out_path.name}")


def plot_skill_scores(skill: pd.DataFrame, out_dir: Path):
    """Bar chart of composite SkillScore — top 10 per season."""
    for year in sorted(skill["Year"].unique()):
        top10 = skill[skill["Year"] == year].head(10)
        colors = [TEAM_COLORS.get(t, "#FFFFFF") for t in top10["Team"]]
        labels = top10.apply(
            lambda r: f"{r['Driver']}  ({r['Team'].split()[0]})", axis=1
        )

        fig, ax = plt.subplots(figsize=(12, 6))
        fig.patch.set_facecolor("#0d0d1a")
        ax.set_facecolor("#1a1a2e")

        bars = ax.barh(labels[::-1], top10["SkillScore"][::-1], color=colors[::-1])
        for bar, val in zip(bars, top10["SkillScore"][::-1]):
            ax.text(bar.get_width() + 0.5,
                    bar.get_y() + bar.get_height() / 2,
                    f"{val:.1f}", va="center", color="white", fontsize=9)

        n_signals = top10["SignalCount"].iloc[0]
        ax.set_xlabel("Composite Skill Score (0-100)", color="white")
        ax.set_title(
            f"Composite Driver Skill Score — {year}  "
            f"({'all 4 signals' if n_signals == 4 else f'{n_signals} signals — telemetry not available this year'})",
            color="white", fontsize=12, pad=12,
        )
        ax.set_xlim(0, 110)
        ax.tick_params(colors="white")
        plt.tight_layout()

        out_path = out_dir / f"skill_score_{year}.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close()
        log.info(f"  Saved {out_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    data = load_all()

    log.info("Computing composite SkillScores...")
    skill = compute_skill_scores(data)

    log.info("Running Elo rating system...")
    elo = run_elo(data["gaps"])

    skill.to_parquet(DATA_DIR / "skill_scores.parquet", index=False)
    elo.to_parquet(DATA_DIR / "elo_history.parquet", index=False)
    log.info("Saved skill_scores.parquet and elo_history.parquet")

    # Print composite rankings
    print("\n=== COMPOSITE SKILL SCORE — TOP 5 PER SEASON ===")
    for year in sorted(skill["Year"].unique()):
        top5 = skill[skill["Year"] == year].head(5)
        sigs = top5["SignalCount"].iloc[0]
        print(f"\n{year}  ({sigs} signals):")
        for _, row in top5.iterrows():
            print(f"  {row['Driver']:<6} ({row['Team']:<22})  "
                  f"Skill: {row['SkillScore']:5.1f}  "
                  f"Quali: {row['QualiRating'] if pd.notna(row['QualiRating']) else 'N/A':>5}  "
                  f"RaceCraft: {row['RaceCraftScore'] if pd.notna(row['RaceCraftScore']) else 'N/A':>5}")

    print("\n=== FINAL ELO RATINGS (top 15) ===")
    final_elo = elo.groupby("Driver")["Elo"].last().sort_values(ascending=False)
    for driver, rating in final_elo.head(15).items():
        team_rows = skill[skill["Driver"] == driver]
        team = team_rows["Team"].iloc[-1] if not team_rows.empty else ""
        print(f"  {driver:<6} ({team:<22})  Elo: {rating:.0f}")

    # Charts
    out_dir = DATA_DIR / "charts" / "elo"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("\nGenerating Elo trajectory chart...")
    plot_elo_trajectory(elo, skill, out_dir)

    log.info("Generating skill score charts...")
    plot_skill_scores(skill, out_dir)

    log.info("\nPhase 6 complete.")
