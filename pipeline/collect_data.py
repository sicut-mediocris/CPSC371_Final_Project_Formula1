"""

Team : Unsupervised Men
Sukirat Singh Dhillon, 230155722
Akshay ArulKrishnan , 230158634
Karsten Keiji Qi-Zhi Ngai-Natsuhara,230165205
Amaan Hingora, 230156282

Phase 1: Multi-Season Data Collection Pipeline
===============================================
Collects Qualifying and Race session data for every Grand Prix from 2018-2024
using the FastF1 library.

Outputs (written to ../data/):
    qualifying_data.parquet  — one row per driver per race weekend
    race_laps_data.parquet   — one row per lap per driver (race sessions only)

Usage:
    python collect_data.py
    python collect_data.py --seasons 2023 2024   # specific seasons only
    python collect_data.py --dry-run              # list events without fetching
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import fastf1
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

fastf1.Cache.enable_cache(str(CACHE_DIR))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(DATA_DIR / "pipeline.log", mode="a"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEASONS = list(range(2018, 2025))   # 2018 through 2024 inclusive

QUALI_RESULT_COLS = [
    "DriverNumber", "Abbreviation", "FullName", "TeamName",
    "Position", "Q1", "Q2", "Q3",
]

LAP_COLS = [
    "Driver", "Team", "LapNumber", "Stint", "LapTime",
    "Sector1Time", "Sector2Time", "Sector3Time",
    "Compound", "TyreLife", "FreshTyre",
    "SpeedI1", "SpeedI2", "SpeedFL", "SpeedST",
    "IsAccurate", "TrackStatus", "PitInTime", "PitOutTime",
]

WEATHER_COLS = ["AirTemp", "TrackTemp", "Humidity", "WindSpeed", "Rainfall"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timedelta_to_seconds(series: pd.Series) -> pd.Series:
    """Convert a timedelta Series to float seconds, NaN for missing."""
    return series.dt.total_seconds()


def _load_session_with_retry(year, round_num, session_type, frames, failed, collector_fn):
    """
    Load a session and collect data. If the rate limit is hit, wait 5 minutes
    and retry once before giving up. This way cached sessions never trigger the
    wait, and only genuinely new API calls cause a pause.
    """
    from fastf1.exceptions import RateLimitExceededError

    label = f"{year} R{round_num} {session_type}"
    for attempt in range(2):
        try:
            log.info(f"  Loading {session_type} session...")
            session = fastf1.get_session(year, round_num, session_type)
            session.load(telemetry=False, weather=True, messages=False)
            df = collector_fn(session, year, round_num)
            if df is not None:
                frames.append(df)
                log.info(f"  {session_type}: collected {len(df)} rows.")
            else:
                failed.append(label)
            return
        except RateLimitExceededError:
            if attempt == 0:
                log.warning(f"  Rate limit hit on {label} — waiting 5 minutes then retrying...")
                time.sleep(300)
            else:
                log.warning(f"  Rate limit hit again on {label} — skipping.")
                failed.append(label)
        except Exception as exc:
            log.warning(f"  {session_type} failed: {exc}")
            failed.append(label)
            return


def _save_parquet(frames: list, out_path: Path, dedup_cols: list):
    """Merge new frames with any existing parquet and save, deduplicating rows."""
    df = pd.concat(frames, ignore_index=True)
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        df = pd.concat([existing, df], ignore_index=True)
        df.drop_duplicates(subset=dedup_cols, inplace=True)
    df.to_parquet(out_path, index=False)


def _weather_averages(session) -> dict:
    """Return mean weather values for a session, or empty dict on failure."""
    try:
        w = session.weather_data
        if w is None or w.empty:
            return {}
        out = {}
        for col in WEATHER_COLS:
            if col in w.columns:
                out[f"weather_{col}"] = w[col].mean()
        return out
    except Exception:
        return {}


def _session_meta(session, year: int, round_num: int) -> dict:
    """Extract basic event metadata."""
    event = session.event
    return {
        "Year": year,
        "Round": round_num,
        "CircuitName": event.get("EventName", "Unknown"),
        "CircuitKey": event.get("Location", "Unknown"),
        "Country": event.get("Country", "Unknown"),
    }


# ---------------------------------------------------------------------------
# Qualifying collector
# ---------------------------------------------------------------------------

def collect_qualifying(session, year: int, round_num: int) -> pd.DataFrame | None:
    """
    Extract one row per driver from a qualifying session.
    Returns None if the session cannot be processed.
    """
    try:
        results = session.results
        if results is None or results.empty:
            log.warning("  No results data for qualifying session.")
            return None

        # Keep only the columns that exist in this session's results
        available = [c for c in QUALI_RESULT_COLS if c in results.columns]
        df = results[available].copy()

        # Convert Q1/Q2/Q3 timedeltas → seconds
        for q in ["Q1", "Q2", "Q3"]:
            if q in df.columns:
                df[f"{q}_s"] = _timedelta_to_seconds(df[q])
                df.drop(columns=[q], inplace=True)

        # Best qualifying time: Q3 takes priority because it represents a driver's
        # peak effort lap. Drivers knocked out in Q1/Q2 fall back to their best
        # available time so they're still represented in the dataset.
        time_cols = [c for c in ["Q3_s", "Q2_s", "Q1_s"] if c in df.columns]
        if time_cols:
            df["BestQualiTime_s"] = df[time_cols].min(axis=1)

        # Add event metadata
        meta = _session_meta(session, year, round_num)
        for k, v in meta.items():
            df[k] = v

        # Add weather averages
        weather = _weather_averages(session)
        for k, v in weather.items():
            df[k] = v

        df.reset_index(drop=True, inplace=True)
        return df

    except Exception as exc:
        log.error(f"  Failed to process qualifying results: {exc}")
        return None


# ---------------------------------------------------------------------------
# Race laps collector
# ---------------------------------------------------------------------------

def collect_race_laps(session, year: int, round_num: int) -> pd.DataFrame | None:
    """
    Extract one row per lap per driver from a race session.
    Returns None if the session cannot be processed.
    """
    try:
        laps = session.laps
        if laps is None or laps.empty:
            log.warning("  No laps data for race session.")
            return None

        available = [c for c in LAP_COLS if c in laps.columns]
        df = laps[available].copy()

        # Convert timedelta columns → seconds
        time_cols = [
            "LapTime", "Sector1Time", "Sector2Time", "Sector3Time",
            "PitInTime", "PitOutTime",
        ]
        for col in time_cols:
            if col in df.columns:
                df[f"{col}_s"] = _timedelta_to_seconds(df[col])
                df.drop(columns=[col], inplace=True)

        # Pull grid/finish positions from results
        try:
            results = session.results
            if results is not None and not results.empty:
                pos_map = results.set_index("Abbreviation")[
                    [c for c in ["GridPosition", "Position", "Status", "Points"]
                     if c in results.columns]
                ].rename(columns={"Position": "FinishPosition"})
                df = df.merge(pos_map, left_on="Driver", right_index=True, how="left")
        except Exception as exc:
            log.warning(f"  Could not merge race results: {exc}")

        # Add event metadata
        meta = _session_meta(session, year, round_num)
        for k, v in meta.items():
            df[k] = v

        # Add weather averages
        weather = _weather_averages(session)
        for k, v in weather.items():
            df[k] = v

        df.reset_index(drop=True, inplace=True)
        return df

    except Exception as exc:
        log.error(f"  Failed to process race laps: {exc}")
        return None


# ---------------------------------------------------------------------------
# Main collection loop
# ---------------------------------------------------------------------------

def run(seasons: list[int], dry_run: bool = False):
    quali_frames: list[pd.DataFrame] = []
    race_frames: list[pd.DataFrame] = []

    total_events = 0
    failed_sessions = []

    for year in seasons:
        log.info(f"{'='*60}")
        log.info(f"Season: {year}")
        log.info(f"{'='*60}")

        try:
            schedule = fastf1.get_event_schedule(year, include_testing=False)
        except Exception as exc:
            log.error(f"  Could not load {year} schedule: {exc}")
            continue

        # Filter to conventional race weekends only
        schedule = schedule[schedule["EventFormat"] != "testing"]

        for _, event in schedule.iterrows():
            round_num = int(event["RoundNumber"])
            event_name = event["EventName"]
            total_events += 1

            log.info(f"\nRound {round_num:02d}: {event_name}")

            if dry_run:
                log.info("  [dry-run] skipping load.")
                continue

            # --- Qualifying ---
            _load_session_with_retry(
                year, round_num, "Q",
                quali_frames, failed_sessions,
                collect_qualifying,
            )

            # --- Race ---
            _load_session_with_retry(
                year, round_num, "R",
                race_frames, failed_sessions,
                collect_race_laps,
            )

            # Save progress after every event so a crash doesn't lose the run.
            if quali_frames:
                _save_parquet(quali_frames, DATA_DIR / "qualifying_data.parquet",
                              dedup_cols=["Year", "Round", "Abbreviation"])
            if race_frames:
                _save_parquet(race_frames, DATA_DIR / "race_laps_data.parquet",
                              dedup_cols=["Year", "Round", "Driver", "LapNumber"])

            # Short pause between events — rate limit is only triggered for
            # sessions not already in cache. Retry logic handles the rare case
            # where we still exceed the cap.
            if not dry_run:
                time.sleep(30)

    if dry_run:
        log.info(f"\nDry run complete. Would process {total_events} events.")
        return

    log.info("\nFinal parquet files are up to date (saved incrementally after each event).")

    if failed_sessions:
        log.warning(f"\nFailed sessions ({len(failed_sessions)}):")
        for s in failed_sessions:
            log.warning(f"  {s}")

    log.info("\nPipeline complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="F1 data collection pipeline")
    parser.add_argument(
        "--seasons", nargs="+", type=int, default=SEASONS,
        help="Which seasons to collect (default: 2018-2024)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List all events without actually fetching data",
    )
    args = parser.parse_args()

    log.info(f"Seasons to collect: {args.seasons}")
    log.info(f"Cache directory: {CACHE_DIR}")
    log.info(f"Output directory: {DATA_DIR}")

    run(seasons=args.seasons, dry_run=args.dry_run)
