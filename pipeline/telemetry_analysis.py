"""
Team : Unsupervised Men
Sukirat Singh Dhillon, 230155722
Akshay ArulKrishnan , 230158634
Karsten Keiji Qi-Zhi Ngai-Natsuhara,230165205
Amaan Hingora, 230156282

Phase 4: Telemetry Skill Signals
==================================
Extracts three driver skill signals from per-meter qualifying lap telemetry
for a representative set of circuits. Telemetry is the most granular data
available — it shows exactly what a driver does at every point on track.

Circuits used (one of each type):
    Monza  (Italian GP)   — high-speed, long straights, heavy braking
    Hungary (Hungarian GP) — low-speed, tight and technical
    Monaco  (Monaco GP)   — street circuit, walls, precision-critical

The three signals computed per braking zone per driver:
    1. Brake point       — distance where the driver first touches the brakes
                           (later = braver/more committed into corners)
    2. Min corner speed  — lowest speed through the apex window
                           (higher = better car control under lateral load)
    3. Throttle point    — distance after the apex where throttle first exceeds 80%
                           (earlier = more confident exit, better traction management)

Each signal is normalised relative to the full field so circuit differences cancel out.
A positive normalised brake point means the driver brakes later than average.

Outputs (written to ../data/):
    telemetry_signals.parquet — one row per driver per corner per circuit

Charts (written to ../data/charts/telemetry/):
    braking_CIRCUIT.png  — brake point comparison across all drivers at that circuit
    speed_DRIVER_vs_DRIVER_CIRCUIT.png  — speed trace overlay for two drivers

Usage:
    python telemetry_analysis.py
    python telemetry_analysis.py --year 2022          # use a different season
    python telemetry_analysis.py --compare VER PER    # generate a head-to-head speed trace
"""

import argparse
import logging
import sys
from pathlib import Path

import fastf1
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
CACHE_DIR = DATA_DIR / "cache"

fastf1.Cache.enable_cache(str(CACHE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Circuit selection
# Each value is the exact FastF1 event name for that circuit type.
# ---------------------------------------------------------------------------
CIRCUITS = {
    "high_speed":   "Italian Grand Prix",   # Monza
    "low_speed":    "Hungarian Grand Prix",  # Budapest
    "street":       "Monaco Grand Prix",     # Monaco
}

# How many of the hardest braking zones to analyse per circuit.
# The top 3 by entry speed captures the most demanding spots without noise.
N_ZONES = 3

# Throttle threshold for "driver is back on power" — 80% avoids counting
# brief lifts and catches the real committed throttle application.
THROTTLE_THRESHOLD = 80


# ---------------------------------------------------------------------------
# Session loading
# ---------------------------------------------------------------------------

def load_qualifying(year: int, event_name: str):
    """Load a qualifying session with telemetry enabled."""
    log.info(f"  Loading {event_name} {year} Qualifying...")
    session = fastf1.get_session(year, event_name, "Q")
    # telemetry=True is required for get_telemetry() to work per lap.
    # It's slower on first load but cached after that.
    session.load(telemetry=True, weather=False, messages=False)
    log.info(f"  Loaded — {len(session.drivers)} drivers available")
    return session


# ---------------------------------------------------------------------------
# Braking zone detection
# ---------------------------------------------------------------------------

def find_braking_zones(tel: pd.DataFrame, n: int = N_ZONES) -> list[dict]:
    """
    Identify the N hardest braking zones on the circuit from telemetry.

    Strategy: scan for transitions from Brake=False to Brake=True (the
    moment the driver touches the pedal). Rank zones by the speed at that
    entry point — a high-speed brake application is a hard braking zone.

    Returns a list of dicts, each describing one zone:
        entry_distance  — where braking starts (metres)
        entry_speed     — speed at brake application (km/h)
        exit_distance   — where continuous braking ends
    """
    # Mark the start of each braking event (False -> True transition)
    braking = tel["Brake"].astype(bool)
    zone_starts = tel[braking & (~braking.shift(1, fill_value=False))]

    zones = []
    for idx in zone_starts.index:
        pos = tel.index.get_loc(idx)
        entry_dist  = tel.loc[idx, "Distance"]
        entry_speed = tel.loc[idx, "Speed"]

        # Find where this braking zone ends (Brake goes back to False)
        remaining = tel.iloc[pos:]
        not_braking = remaining[~remaining["Brake"].astype(bool)]
        if not_braking.empty:
            exit_dist = tel["Distance"].iloc[-1]
        else:
            exit_dist = not_braking.iloc[0]["Distance"]

        zones.append({
            "entry_distance": entry_dist,
            "entry_speed":    entry_speed,
            "exit_distance":  exit_dist,
        })

    # Sort by entry speed descending and keep the top N
    zones.sort(key=lambda z: z["entry_speed"], reverse=True)
    return zones[:n]


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def compute_signals_for_zone(tel: pd.DataFrame, zone: dict) -> dict:
    """
    For a single braking zone, extract the three telemetry skill signals.

    The apex window extends 200m past the end of braking to capture the
    full corner minimum speed and the throttle application on exit.
    """
    ref_entry = zone["entry_distance"]
    apex_window_end = zone["exit_distance"] + 200   # 200m past end of braking

    corner = tel[(tel["Distance"] >= ref_entry) & (tel["Distance"] <= apex_window_end)]
    if corner.empty:
        return {}

    # 1. Brake point — find the driver's actual first brake application within
    # a 150m search window centered on the reference brake point. Drivers
    # brake slightly earlier or later than the reference lap, and that delta
    # is exactly the signal we want to capture.
    search_window = tel[
        (tel["Distance"] >= ref_entry - 150) &
        (tel["Distance"] <= ref_entry + 100)
    ]
    first_brake = search_window[search_window["Brake"].astype(bool)]
    brake_point = first_brake.iloc[0]["Distance"] if not first_brake.empty else ref_entry

    # 2. Min corner speed — lowest speed between brake application and 200m past exit
    min_speed_idx = corner["Speed"].idxmin()
    min_speed     = corner.loc[min_speed_idx, "Speed"]
    apex_distance = corner.loc[min_speed_idx, "Distance"]

    # 3. Throttle application point — first distance after apex where throttle > threshold
    post_apex = corner[corner["Distance"] > apex_distance]
    throttle_open = post_apex[post_apex["Throttle"] > THROTTLE_THRESHOLD]
    if throttle_open.empty:
        throttle_point = None
    else:
        throttle_point = throttle_open.iloc[0]["Distance"]

    return {
        "brake_point_m":    brake_point,
        "entry_speed_kmh":  zone["entry_speed"],
        "min_speed_kmh":    min_speed,
        "apex_distance_m":  apex_distance,
        "throttle_point_m": throttle_point,
    }


# ---------------------------------------------------------------------------
# Process one session
# ---------------------------------------------------------------------------

def process_session(session, year: int, circuit_type: str) -> pd.DataFrame:
    """
    Extract telemetry signals for every driver in the session.
    Uses each driver's fastest qualifying lap.
    """
    event_name = session.event["EventName"]
    records = []

    # First pass: get field-average braking zones using the overall fastest lap.
    # This gives us consistent zone definitions to compare all drivers against.
    fastest_overall = session.laps.pick_fastest()
    if fastest_overall is None or fastest_overall.empty:
        log.warning(f"  No fastest lap found for {event_name}, skipping.")
        return pd.DataFrame()

    ref_tel = fastest_overall.get_telemetry().add_distance()
    zones = find_braking_zones(ref_tel)
    log.info(f"  Found {len(zones)} braking zones at {event_name}")
    for i, z in enumerate(zones):
        log.info(f"    Zone {i+1}: entry at {z['entry_distance']:.0f}m, "
                 f"speed {z['entry_speed']:.0f} km/h")

    # Second pass: measure each driver at those same zones
    for driver in session.drivers:
        try:
            driver_laps = session.laps.pick_drivers(driver)
            fastest = driver_laps.pick_fastest()
            if fastest is None or fastest.empty:
                continue

            tel = fastest.get_telemetry().add_distance()
            if tel.empty:
                continue

            driver_info = session.get_driver(driver)
            abbr = driver_info.get("Abbreviation", driver)
            team = driver_info.get("TeamName", "")

            for zone_idx, zone in enumerate(zones):
                sigs = compute_signals_for_zone(tel, zone)
                if not sigs:
                    continue

                records.append({
                    "Year":         year,
                    "CircuitType":  circuit_type,
                    "CircuitName":  event_name,
                    "Driver":       abbr,
                    "Team":         team,
                    "ZoneIndex":    zone_idx + 1,
                    "ZoneEntryM":   zone["entry_distance"],
                    **sigs,
                })

        except Exception as exc:
            log.warning(f"  Driver {driver} failed: {exc}")
            continue

    df = pd.DataFrame(records)
    log.info(f"  Extracted signals for {df['Driver'].nunique()} drivers, "
             f"{len(df)} driver-zone rows")
    return df


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalise_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise each signal relative to the field, per circuit per zone.

    The normalised value is how many standard deviations above/below the
    field mean the driver sits. Positive = better (later brake, higher min
    speed, earlier throttle). This makes circuits comparable to each other.
    """
    df = df.copy()

    for signal, higher_is_better in [
        ("brake_point_m",    True),   # later brake point = more committed
        ("min_speed_kmh",    True),   # higher apex speed = better car control
        ("throttle_point_m", False),  # earlier throttle = better exit (lower distance)
    ]:
        col_norm = f"{signal}_norm"
        group_cols = ["CircuitName", "ZoneIndex"]

        means = df.groupby(group_cols)[signal].transform("mean")
        stds  = df.groupby(group_cols)[signal].transform("std")

        z_score = (df[signal] - means) / stds.replace(0, 1)
        df[col_norm] = z_score if higher_is_better else -z_score

    return df


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
}


def plot_brake_points(df: pd.DataFrame, circuit_name: str, out_dir: Path):
    """
    Horizontal bar chart showing each driver's average brake point
    across all zones at this circuit. Later = braver = further right.
    """
    circuit_df = df[df["CircuitName"] == circuit_name].copy()
    if circuit_df.empty:
        return

    avg = (
        circuit_df.groupby(["Driver", "Team"])["brake_point_m_norm"]
        .mean()
        .reset_index()
        .sort_values("brake_point_m_norm", ascending=True)
    )

    colors = [TEAM_COLORS.get(t, "#FFFFFF") for t in avg["Team"]]

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor("#0d0d1a")
    ax.set_facecolor("#1a1a2e")

    bars = ax.barh(avg["Driver"], avg["brake_point_m_norm"], color=colors)
    ax.axvline(0, color="gray", linewidth=0.8, linestyle="--")

    for bar, val in zip(bars, avg["brake_point_m_norm"]):
        ax.text(
            val + (0.02 if val >= 0 else -0.02),
            bar.get_y() + bar.get_height() / 2,
            f"{val:+.2f}σ",
            va="center", ha="left" if val >= 0 else "right",
            color="white", fontsize=8,
        )

    ax.set_xlabel("Brake Point (std devs from field mean — later = braver)", color="white")
    ax.set_title(f"Brake Points vs Field Average — {circuit_name}",
                 color="white", fontsize=12, pad=12)
    ax.tick_params(colors="white")
    ax.spines["bottom"].set_color("#333355")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#333355")
    plt.tight_layout()

    slug = circuit_name.replace(" ", "_").lower()
    out_path = out_dir / f"braking_{slug}.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    log.info(f"  Saved {out_path.name}")


def plot_speed_trace(session, driver_a: str, driver_b: str,
                     circuit_name: str, out_dir: Path):
    """
    Overlay speed traces for two drivers on their fastest qualifying lap.
    The delta strip below shows who is faster at each point on track.
    """
    try:
        lap_a = session.laps.pick_drivers(driver_a).pick_fastest()
        lap_b = session.laps.pick_drivers(driver_b).pick_fastest()
        tel_a = lap_a.get_telemetry().add_distance()
        tel_b = lap_b.get_telemetry().add_distance()
    except Exception as exc:
        log.warning(f"  Speed trace failed for {driver_a}/{driver_b}: {exc}")
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7),
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#0d0d1a")
    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")

    color_a = TEAM_COLORS.get(lap_a["Team"], "#E10600")
    color_b = TEAM_COLORS.get(lap_b["Team"], "#00D2BE")
    # Same team means same color — pick a contrasting fallback for driver B
    # so the two lines are always visually distinct.
    if color_a == color_b:
        color_b = "#FFFFFF"

    ax1.plot(tel_a["Distance"], tel_a["Speed"], color=color_a, linewidth=1.2, label=driver_a)
    ax1.plot(tel_b["Distance"], tel_b["Speed"], color=color_b, linewidth=1.2, label=driver_b)
    ax1.set_ylabel("Speed (km/h)", color="white")
    ax1.tick_params(colors="white")
    ax1.legend(facecolor="#1a1a2e", labelcolor="white")
    ax1.set_title(f"Speed Trace — {circuit_name}  |  {driver_a} vs {driver_b}",
                  color="white", fontsize=12, pad=10)

    # Delta: interpolate b onto a's distance axis and subtract
    interp_b = np.interp(tel_a["Distance"], tel_b["Distance"], tel_b["Speed"])
    delta = tel_a["Speed"].values - interp_b
    ax2.fill_between(tel_a["Distance"], delta, 0,
                     where=(delta > 0), color=color_a, alpha=0.5)
    ax2.fill_between(tel_a["Distance"], delta, 0,
                     where=(delta <= 0), color=color_b, alpha=0.5)
    ax2.axhline(0, color="gray", linewidth=0.6)
    ax2.set_ylabel(f"{driver_a} faster ↑", color="white", fontsize=8)
    ax2.set_xlabel("Distance (m)", color="white")
    ax2.tick_params(colors="white")

    plt.tight_layout()
    out_path = out_dir / f"speed_{driver_a}_vs_{driver_b}_{circuit_name.replace(' ', '_')}.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    log.info(f"  Saved {out_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 telemetry skill signals")
    parser.add_argument("--year", type=int, default=2023,
                        help="Season to analyse (default: 2023)")
    parser.add_argument("--compare", nargs=2, metavar=("DRIVER_A", "DRIVER_B"),
                        default=None,
                        help="Generate speed trace comparison for two drivers")
    args = parser.parse_args()

    all_frames = []
    sessions_loaded = {}

    for circuit_type, event_name in CIRCUITS.items():
        log.info(f"\n{'='*55}")
        log.info(f"Circuit: {event_name}  ({circuit_type})")
        log.info(f"{'='*55}")

        try:
            session = load_qualifying(args.year, event_name)
            sessions_loaded[event_name] = session
            df = process_session(session, args.year, circuit_type)
            if not df.empty:
                all_frames.append(df)
        except Exception as exc:
            log.error(f"  Failed to process {event_name}: {exc}")
            continue

    if not all_frames:
        log.error("No telemetry data collected. Exiting.")
        sys.exit(1)

    combined = pd.concat(all_frames, ignore_index=True)
    combined = normalise_signals(combined)

    combined.to_parquet(DATA_DIR / "telemetry_signals.parquet", index=False)
    log.info(f"\nSaved telemetry_signals.parquet — {len(combined):,} rows")

    # Print summary
    print("\n=== BRAKE POINTS VS FIELD MEAN (std devs, positive = brakes later) ===")
    avg_brake = (
        combined.groupby("Driver")["brake_point_m_norm"]
        .mean()
        .sort_values(ascending=False)
    )
    for driver, val in avg_brake.head(10).items():
        print(f"  {driver:<6}  {val:+.3f} std")

    print("\n=== MINIMUM CORNER SPEED VS FIELD MEAN ===")
    avg_speed = (
        combined.groupby("Driver")["min_speed_kmh_norm"]
        .mean()
        .sort_values(ascending=False)
    )
    for driver, val in avg_speed.head(10).items():
        print(f"  {driver:<6}  {val:+.3f} std")

    # Charts
    out_dir = DATA_DIR / "charts" / "telemetry"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("\nGenerating brake point charts...")
    for event_name in CIRCUITS.values():
        plot_brake_points(combined, event_name, out_dir)

    # Speed trace: default to Verstappen vs Perez (same team = car-controlled comparison)
    # or whatever the user passed
    compare_pair = args.compare if args.compare else ["VER", "PER"]
    for event_name, session in sessions_loaded.items():
        log.info(f"Generating speed trace: {compare_pair[0]} vs {compare_pair[1]} at {event_name}...")
        plot_speed_trace(session, compare_pair[0], compare_pair[1], event_name, out_dir)

    log.info("\nPhase 4 complete.")
