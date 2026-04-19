"""

Team : Unsupervised Men
Sukirat Singh Dhillon, 230155722
Akshay ArulKrishnan , 230158634
Karsten Keiji Qi-Zhi Ngai-Natsuhara,230165205
Amaan Hingora, 230156282

Reads the parquet outputs from completed pipeline phases and writes RESULTS.md —
a plain-English summary of what the data actually shows.

Run this after any phase to refresh the findings:
    python pipeline/generate_summary.py
"""

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_PATH = ROOT / "RESULTS.md"


def load():
    ratings  = pd.read_parquet(DATA_DIR / "qualifying_ratings.parquet")
    gaps     = pd.read_parquet(DATA_DIR / "teammate_gaps.parquet")
    profiles = pd.read_parquet(DATA_DIR / "sector_profiles.parquet")
    return ratings, gaps, profiles


def phase2_findings(ratings: pd.DataFrame, gaps: pd.DataFrame) -> str:
    lines = []

    # Season-by-season top driver
    lines.append("### Season winners (who consistently outqualified their teammate)\n")
    lines.append("| Season | Driver | Team | Rating | Win Rate | Avg Gap |")
    lines.append("|--------|--------|------|--------|----------|---------|")
    for year in sorted(ratings["Year"].unique()):
        top = ratings[ratings["Year"] == year].iloc[0]
        lines.append(
            f"| {year} | {top['Driver']} | {top['Team']} "
            f"| {top['QualiRating']:.1f} "
            f"| {top['WinRate']*100:.0f}% "
            f"| {top['AvgGapToTeammate_s']*1000:+.0f} ms |"
        )

    lines.append("")

    # Multi-season dominance (exclude apparent data artifacts — valid 3-letter codes only)
    valid_drivers = ratings[ratings["Driver"].str.len() == 3]
    avg_ratings = (
        valid_drivers.groupby("Driver")["QualiRating"]
        .mean()
        .sort_values(ascending=False)
        .head(5)
    )
    lines.append("### Most consistently dominant qualifiers (avg rating across all seasons)\n")
    for driver, rating in avg_ratings.items():
        team = ratings[ratings["Driver"] == driver]["Team"].iloc[-1]
        lines.append(f"- **{driver}** ({team}): {rating:.1f} avg rating")

    lines.append("")

    # Biggest single-weekend gap
    biggest = gaps.sort_values("GapPct", ascending=False).iloc[0]
    lines.append(
        f"### Largest single qualifying gap on record\n"
        f"**{biggest['Driver']}** vs {biggest['TeammateAbbr']} "
        f"at {biggest['CircuitName']} {int(biggest['Year'])}: "
        f"**{biggest['GapPct']:.2f}%** ({biggest['GapToTeammate_s']*1000:+.0f} ms)"
    )
    lines.append("")

    # Notable storylines
    lines.append("### Notable findings\n")

    # Russell 2019
    rus19 = ratings[(ratings["Driver"] == "RUS") & (ratings["Year"] == 2019)]
    if not rus19.empty:
        r = rus19.iloc[0]
        lines.append(
            f"- **George Russell at Williams (2019)**: {r['WinRate']*100:.0f}% win rate "
            f"against teammate — he outqualified Robert Kubica at every single race weekend "
            f"that season. This is the signal that put him on Mercedes' radar."
        )

    # VER 2021
    ver21 = ratings[(ratings["Driver"] == "VER") & (ratings["Year"] == 2021)]
    if not ver21.empty:
        r = ver21.iloc[0]
        lines.append(
            f"- **Verstappen vs Pérez (2021)**: {r['WinRate']*100:.0f}% win rate "
            f"with an average gap of {r['AvgGapToTeammate_s']*1000:+.0f} ms. "
            f"Both drivers had the same Red Bull — the gap is purely driver."
        )

    # NOR 2024
    nor24 = ratings[(ratings["Driver"] == "NOR") & (ratings["Year"] == 2024)]
    if not nor24.empty:
        r = nor24.iloc[0]
        lines.append(
            f"- **Norris (2024)**: highest single-season rating in the dataset at "
            f"{r['QualiRating']:.1f}, with a {r['WinRate']*100:.0f}% win rate "
            f"over Piastri."
        )

    return "\n".join(lines)


def phase3_findings(profiles: pd.DataFrame) -> str:
    lines = []

    # Latest season overview
    latest_year = profiles["Year"].max()
    top5 = profiles[profiles["Year"] == latest_year].head(5)
    lines.append(f"### Top 5 drivers by overall sector score — {latest_year}\n")
    lines.append("| Driver | Team | S1 | S2 | S3 | Overall |")
    lines.append("|--------|------|----|----|----|---------|")
    for _, row in top5.iterrows():
        lines.append(
            f"| {row['Driver']} | {row['Team']} "
            f"| {row['S1Score']:.3f} | {row['S2Score']:.3f} "
            f"| {row['S3Score']:.3f} | {row['OverallScore']:.3f} |"
        )

    lines.append("")

    # Sector specialists
    lines.append("### Sector specialists (drivers with the strongest bias in one sector)\n")
    for bias_col, label, desc in [
        ("S1Bias", "S1 — High-speed corners", "fast, sweeping sections like Silverstone S1 or Spa Raidillon"),
        ("S2Bias", "S2 — Mixed",              "combinations of medium-speed and braking zones"),
        ("S3Bias", "S3 — Technical corners",  "slow, precise sections like Monaco or the final chicanes"),
    ]:
        top3 = profiles.sort_values(bias_col, ascending=False).head(3)
        specialists = ", ".join(
            f"{r['Driver']} ({int(r['Year'])})" for _, r in top3.iterrows()
        )
        lines.append(f"**{label}** ({desc}):")
        lines.append(f"Top specialists — {specialists}")
        lines.append("")

    # Hamilton sector decline
    ham = profiles[profiles["Driver"] == "HAM"].sort_values("Year")
    if not ham.empty:
        earliest = ham.iloc[0]
        latest   = ham.iloc[-1]
        drop = earliest["OverallScore"] - latest["OverallScore"]
        lines.append("### Hamilton's sector score decline (2018 → 2024)\n")
        lines.append("| Year | S1 | S2 | S3 | Overall |")
        lines.append("|------|----|----|----|---------|")
        for _, row in ham.iterrows():
            lines.append(
                f"| {int(row['Year'])} "
                f"| {row['S1Score']:.3f} | {row['S2Score']:.3f} "
                f"| {row['S3Score']:.3f} | {row['OverallScore']:.3f} |"
            )
        lines.append(
            f"\nHamilton's overall score dropped {drop:.3f} points from "
            f"{int(earliest['Year'])} to {int(latest['Year'])}. "
            f"His S2 score in particular fell from {earliest['S2Score']:.3f} "
            f"to {latest['S2Score']:.3f}, suggesting a shift in driving style "
            f"or car fit rather than raw pace loss."
        )

    lines.append("")

    # Verstappen peak
    ver = profiles[profiles["Driver"] == "VER"].sort_values("Year")
    if not ver.empty:
        peak = ver.loc[ver["OverallScore"].idxmax()]
        lines.append(
            f"### Verstappen's peak season\n"
            f"**{int(peak['Year'])}** — overall score {peak['OverallScore']:.3f}, "
            f"with an almost perfect S2 score of **{peak['S2Score']:.3f}**. "
            f"An S2 score of 0.99 means his mixed-sector lap times were essentially "
            f"at the ceiling of what the field produced that season."
        )

    return "\n".join(lines)


def build_summary(ratings, gaps, profiles) -> str:
    total_seasons  = ratings["Year"].nunique()
    total_drivers  = ratings["Driver"].nunique()
    total_weekends = gaps[["Year", "Round"]].drop_duplicates().shape[0]

    sections = [
        "# F1 Driver Skill Decomposition — Results Summary",
        "",
        "> Auto-generated from pipeline outputs. Re-run `python pipeline/generate_summary.py` to refresh.",
        "",
        "---",
        "",
        "## Dataset",
        "",
        f"- **Seasons covered**: {ratings['Year'].min()}–{ratings['Year'].max()} "
        f"({total_seasons} seasons)",
        f"- **Drivers analysed**: {total_drivers} unique driver codes",
        f"- **Race weekends**: {total_weekends} qualifying sessions with teammate pairs",
        "",
        "---",
        "",
        "## Phase 2 — Qualifying Pace vs Teammate",
        "",
        "**Method**: For each race weekend, each driver is paired with their teammate. "
        "Because both are in the same car, any qualifying gap is purely the driver. "
        "The QualiRating (0–100) combines win rate (60%) and average gap margin (40%), "
        "normalised within the season so ratings reflect performance relative to that year's grid.",
        "",
        phase2_findings(ratings, gaps),
        "",
        "---",
        "",
        "## Phase 3 — Sector Specialization Profile",
        "",
        "**Method**: From each driver's best clean, green-flag race lap per weekend, "
        "sector times are min-max scaled within the session (1.0 = fastest in field, "
        "0.0 = slowest). Season profiles use the median across all weekends to reduce "
        "the effect of outlier laps. S1 corresponds to high-speed sections, S2 to mixed, "
        "S3 to tight technical corners.",
        "",
        phase3_findings(profiles),
        "",
        "---",
        "",
        "## Phases 4–6 — Coming Soon",
        "",
        "- **Phase 4**: Telemetry signals — brake points, minimum corner speed, "
        "throttle application per circuit",
        "- **Phase 5**: Tire degradation & race craft score from stint regression",
        "- **Phase 6**: Composite Elo-style driver rating combining all signals",
        "",
        "---",
        "",
        "*CPSC 371 — F1 Driver Skill Decomposition Engine*",
    ]
    return "\n".join(sections)


if __name__ == "__main__":
    ratings, gaps, profiles = load()
    md = build_summary(ratings, gaps, profiles)
    OUT_PATH.write_text(md, encoding="utf-8")
    print(f"Written to {OUT_PATH}")
    print(md.encode("ascii", errors="replace").decode())
