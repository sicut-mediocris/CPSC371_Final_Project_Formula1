# F1 Driver Skill Decomposition Engine

![Status](https://img.shields.io/badge/Status-In%20Development-brightgreen) ![Python](https://img.shields.io/badge/Backend-Python%20%7C%20FastF1-yellow) ![Three.js](https://img.shields.io/badge/Frontend-Three.js%20%7C%20Next.js-black)

## What This Project Does

This project answers one of F1's most debated questions:

> **Who are the most skilled drivers, independent of the car they're driving?**

A driver on a championship-winning team will almost always beat a driver on a backmarker team. That tells us nothing about talent. To actually compare drivers, you need to control for the car — and the cleanest way to do that is to look at teammates: two drivers, same car, same conditions, same weekend. Any gap between them is purely the driver.

This system collects seven years of FastF1 telemetry data (2018–2024), extracts six skill signals that are car-independent, and combines them into a season-by-season driver rating. The results are served through a scroll-driven 3D web interface.

---

## Project Status

| Phase | Description | Status |
|---|---|---|
| 1 | Multi-season data collection pipeline | ✅ Complete |
| 2 | Teammate qualifying gap analysis & ratings | ✅ Complete |
| 3 | Sector specialization profile (S1/S2/S3) | Planned |
| 4 | Telemetry skill signals (brake points, corner speed) | Planned |
| 5 | Tire degradation & race craft score | Planned |
| 6 | Elo-style composite driver rating | Planned |
| 7 | FastAPI backend | Planned |
| 8 | Next.js + Three Fiber frontend foundation | Planned |
| 9 | Scroll-driven 3D circuit experience | Planned |
| 10 | Data visualization overlays (Recharts, radar charts) | Planned |

---

## Repository Layout

```
Formula1/
├── pipeline/
│   ├── collect_data.py          # Phase 1 — download & cache all session data
│   └── qualifying_analysis.py  # Phase 2 — teammate gap analysis & ratings
│
├── data/
│   ├── cache/                   # FastF1 raw session cache (auto-managed, not in git)
│   ├── qualifying_data.parquet  # Phase 1 output — one row per driver per race weekend
│   ├── race_laps_data.parquet   # Phase 1 output — one row per lap per driver
│   ├── teammate_gaps.parquet    # Phase 2 output — per-weekend teammate deltas
│   ├── qualifying_ratings.parquet  # Phase 2 output — season-level ratings (0–100)
│   ├── charts/                  # Generated PNG charts
│   │   ├── quali_rating_2018.png ... quali_rating_2024.png
│   │   └── quali_rating_heatmap.png
│   └── pipeline.log             # Execution log
│
├── explore.ipynb                # FastF1 walkthrough and dataset exploration
├── first.ipynb                  # Early scratch notebook
└── CLAUDE.md                    # Detailed phase-by-phase implementation spec
```

---

## Setup

**Requirements:** Python 3.11+

```bash
pip install fastf1 pandas pyarrow matplotlib numpy
```

FastF1 caches API responses locally so sessions only download once. The cache lives in `data/cache/` and is excluded from git (it's ~several GB for all 7 seasons).

---

## Running the Pipeline

### Phase 1 — Collect Data

Downloads qualifying and race session data for 2018–2024 from the FastF1 API and saves two Parquet files.

```bash
cd pipeline
python collect_data.py
```

Options:
```bash
python collect_data.py --seasons 2023 2024   # specific seasons only
python collect_data.py --dry-run             # list all events without fetching
```

The script saves progress after every race weekend, so it's safe to interrupt and resume. Already-cached sessions load instantly without hitting the API.

**Output files:**
- `data/qualifying_data.parquet` — one row per driver per race weekend. Columns: `Year`, `Round`, `CircuitName`, `Abbreviation`, `FullName`, `TeamName`, `Position`, `Q1_s`, `Q2_s`, `Q3_s`, `BestQualiTime_s`, weather averages.
- `data/race_laps_data.parquet` — one row per lap per driver. Columns: `Driver`, `Team`, `LapNumber`, `Stint`, `LapTime_s`, `Sector1Time_s`, `Sector2Time_s`, `Sector3Time_s`, `Compound`, `TyreLife`, `GridPosition`, `FinishPosition`, weather averages.

---

### Phase 2 — Qualifying Analysis

Reads `qualifying_data.parquet` and computes teammate gap ratings for every season.

```bash
cd pipeline
python qualifying_analysis.py
```

**Output files:**
- `data/teammate_gaps.parquet` — one row per driver per race weekend. Key columns: `GapToTeammate_s` (seconds, negative = faster), `GapPct` (% delta), `BeatsTeammate` (boolean).
- `data/qualifying_ratings.parquet` — one row per driver per season. Key columns: `QualiRating` (0–100), `WinRate` (% of weekends faster than teammate), `AvgGapToTeammate_s`.

**Charts saved to `data/charts/`:**
- `quali_rating_YYYY.png` — horizontal bar chart of top 10 rated drivers for that season, colored by team.
- `quali_rating_heatmap.png` — grid of top 20 drivers × 7 seasons, showing rating consistency over time. Green = consistently outqualified their teammate.

**How the QualiRating is calculated:**

The rating combines two signals:
- **Win rate (60%)** — what fraction of weekends did the driver outqualify their teammate? Robust to outlier laps.
- **Gap score (40%)** — how large was the average margin? Min-max scaled within the season so it's relative to that year's grid.

Both components are normalised per season so a 2018 rating of 80 means "top performer relative to the 2018 grid", not an absolute benchmark.

Drivers with fewer than 3 teammate comparisons in a season are excluded (too small a sample).

---

## Skill Signals (What Gets Measured)

| Signal | Source | Why It's Car-Independent |
|---|---|---|
| Qualifying gap to teammate | `qualifying_data.parquet` | Same car, same weekend |
| Sector delta (S1/S2/S3) | `race_laps_data.parquet` | Normalised within team |
| Brake point per corner | Telemetry (Phase 4) | Driver decision, not car setup |
| Minimum corner speed | Telemetry (Phase 4) | Car control under lateral load |
| Throttle application point | Telemetry (Phase 4) | Confidence and feel |
| Tire degradation rate | Race stint regression (Phase 5) | Relative to same-car teammate |

---

## Tech Stack

| Layer | Tools |
|---|---|
| Data collection | FastF1, Pandas, PyArrow |
| ML / ratings | XGBoost, LightGBM, scikit-learn, SciPy |
| Backend (planned) | FastAPI, Uvicorn |
| Frontend (planned) | Next.js, React Three Fiber, GSAP, Recharts, Tailwind CSS |

---

*CPSC 371 Project — F1 Driver Skill Decomposition Engine.*
