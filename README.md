# F1 Driver Skill Decomposition Engine

![Status](https://img.shields.io/badge/Status-In%20Development-brightgreen) ![Python](https://img.shields.io/badge/Backend-Python%20%7C%20FastF1-yellow) ![Three.js](https://img.shields.io/badge/Frontend-Three.js%20%7C%20Next.js-black)

## What We're Building

The core question is: **who are the most skilled F1 drivers, if you take the car out of the equation?**

The obvious problem with comparing F1 drivers is that the car does most of the work. Verstappen wins a lot, but he also had by far the fastest car for two years straight. To actually measure driver skill you need a baseline that removes the car — and the cleanest one available is the teammate comparison. Same car, same weekend, same conditions. Any gap between two teammates is purely the driver.

We collect seven years of FastF1 data (2018–2024), extract several skill signals that are car-independent, and eventually combine them into a single driver rating. The plan is to surface the results through a scroll-driven 3D frontend, but the data pipeline is the foundation of everything.

---

## Current Status

| Phase | What it does | Status |
|---|---|---|
| 1 | Pull all qualifying + race data from FastF1 API (2018–2024) | Done |
| 2 | Teammate qualifying gap analysis — who consistently beats their partner | Done |
| 3 | Sector specialization — which drivers are strong in S1 vs S2 vs S3 | Done |
| 4 | Telemetry signals — brake points, corner speed, throttle application | Done |
| 5 | Tire degradation & race craft score | Pending |
| 6 | Elo-style composite rating across all signals | Pending |
| 7 | FastAPI backend to serve the data | Pending |
| 8 | Next.js + React Three Fiber frontend | Pending |
| 9 | Scroll-driven 3D circuit experience | Pending |
| 10 | Recharts data viz overlays (radar, speed traces, Elo trajectory) | Pending |

For a summary of what the completed phases actually found, see **[RESULTS.md](RESULTS.md)**.

---

## Repo Layout

```
Formula1/
├── pipeline/
│   ├── collect_data.py          # Phase 1 — downloads and caches all session data
│   ├── qualifying_analysis.py   # Phase 2 — teammate gap analysis and QualiRating
│   ├── sector_analysis.py       # Phase 3 — sector score profiles and radar charts
│   ├── telemetry_analysis.py    # Phase 4 — brake points, corner speed, throttle signals
│   └── generate_summary.py      # Reads all parquet outputs and writes RESULTS.md
│
├── data/
│   ├── qualifying_data.parquet      # Phase 1: one row per driver per race weekend
│   ├── race_laps_data.parquet       # Phase 1: one row per lap per driver (162k rows)
│   ├── teammate_gaps.parquet        # Phase 2: per-weekend teammate deltas
│   ├── qualifying_ratings.parquet   # Phase 2: season-level QualiRating per driver
│   ├── sector_weekend.parquet       # Phase 3: sector scores per driver per weekend
│   ├── sector_profiles.parquet      # Phase 3: median sector scores per driver per season
│   ├── telemetry_signals.parquet    # Phase 4: brake/speed/throttle signals per driver per corner
│   ├── charts/
│   │   ├── quali_rating_2018.png    # top 10 qualifying ratings, per year
│   │   ├── ...
│   │   ├── quali_rating_2024.png
│   │   ├── quali_rating_heatmap.png # all seasons side by side for top 20 drivers
│   │   ├── sectors/
│   │   │   ├── radar_VER.png        # spider chart — Verstappen's S1/S2/S3 fingerprint
│   │   │   ├── radar_HAM.png
│   │   │   ├── ...
│   │   │   └── sector_heatmap.png   # top 20 drivers x 3 sectors for latest season
│   │   └── telemetry/
│   │       ├── braking_italian_grand_prix.png   # brake point comparison at Monza
│   │       ├── braking_hungarian_grand_prix.png
│   │       ├── braking_monaco_grand_prix.png
│   │       └── speed_VER_vs_PER_*.png           # head-to-head speed traces
│   └── pipeline.log                 # timestamped log of every session loaded
│
├── RESULTS.md                   # Plain-English summary of findings so far
├── explore.ipynb                # Early FastF1 exploration notebook
└── CLAUDE.md                    # Full phase-by-phase implementation spec
```

---

## Setup

Python 3.11+. Install dependencies:

```bash
pip install fastf1 pandas pyarrow matplotlib numpy
```

FastF1 caches every session locally after the first download, so the API only gets hit once per session. The cache folder (`data/cache/`) is excluded from git — it's a few GB across all 7 seasons so you don't want it versioned. When you run the pipeline for the first time it'll be slow; after that it's instant.

---

## Running Things

### Phase 1 — Collect the raw data

This downloads qualifying results and race lap data for every Grand Prix from 2018 to 2024.

```bash
python pipeline/collect_data.py
```

It saves after every race weekend, so if it crashes or you kill it you won't lose progress. Run it again and it picks up where it left off (existing rows get deduplicated).

```bash
python pipeline/collect_data.py --seasons 2023 2024   # only pull specific years
python pipeline/collect_data.py --dry-run             # just list events, don't fetch anything
```

**What you get:**
- `data/qualifying_data.parquet` — Q1/Q2/Q3 times, grid position, team, weather per driver per weekend
- `data/race_laps_data.parquet` — every lap for every driver: sector times, tyre compound, tyre life, speed traps, grid/finish positions

---

### Phase 2 — Qualifying gap analysis

Pairs teammates for each weekend, computes the gap between them, and rolls it up into a season rating.

```bash
python pipeline/qualifying_analysis.py
```

**What you get:**
- `data/teammate_gaps.parquet` — the raw gap data. `GapToTeammate_s` is negative if the driver was faster, `GapPct` is the % margin, `BeatsTeammate` is a boolean
- `data/qualifying_ratings.parquet` — one row per driver per season with `QualiRating` (0–100), `WinRate`, and `AvgGapToTeammate_s`
- `data/charts/quali_rating_YYYY.png` — top 10 for each season, colored by team
- `data/charts/quali_rating_heatmap.png` — overview heatmap across all 7 seasons

**How the rating works:**

The score is 60% win rate (what % of weekends did this driver outqualify their teammate) plus 40% gap score (how large was the margin). Both are min-max scaled within the season so you're always comparing relative to that year's grid, not some absolute number. Drivers with fewer than 3 comparisons in a season get dropped — not enough data.

---

### Phase 3 — Sector specialization

Looks at where on track each driver is fast. S1 is typically high-speed, S2 mixed, S3 more technical. Some drivers are genuinely stronger in one type of corner — this makes that visible.

```bash
python pipeline/sector_analysis.py
```

By default generates radar charts for the top 15 drivers. To get specific drivers:

```bash
python pipeline/sector_analysis.py --drivers VER HAM LEC NOR ALO
```

**What you get:**
- `data/sector_weekend.parquet` — normalized sector scores per driver per race weekend (1.0 = fastest in session, 0.0 = slowest)
- `data/sector_profiles.parquet` — median sector scores per driver per season, plus a bias flag for specialists
- `data/charts/sectors/radar_DRIVER.png` — spider chart showing a driver's sector fingerprint across each season they raced
- `data/charts/sectors/sector_heatmap.png` — top 20 drivers for the most recent season, all three sectors at once

**How normalization works:**

For each race weekend we take each driver's best clean, green-flag lap (no safety car, not a pit lap, IsAccurate=True). Within that session, each sector time gets scaled 0–1 so circuit differences don't matter — a 0.9 in S1 at Monza and a 0.9 in S1 at Monaco both mean "near the top of the field in that sector." Season profiles use the median across all weekends.

---

### Regenerate the results summary

After running any phase, you can refresh RESULTS.md with the latest findings:

```bash
python pipeline/generate_summary.py
```

---

## What the Data Shows So Far

Quick highlights — full write-up in [RESULTS.md](RESULTS.md).

- George Russell had a **100% win rate against his Williams teammate in 2019** — outqualified Robert Kubica at every single race. A clear indicator of raw talent before he had a competitive car.
- Verstappen's biggest gap was at the 2023 Austrian GP where he was **0.97% faster than Perez in the same car** — a huge margin at that level.
- Hamilton's sector scores show a consistent **decline from 2018 to 2024**, particularly in S2. His 2020 season was his strongest, with near-perfect scores in S3 (technical corners).
- Verstappen's **2023 S2 score was 0.994** — essentially at the ceiling of what the entire field produced that season in the mixed sector.
- Norris had the **highest single-season qualifying rating** in the dataset (90.0 in 2024).
- Across Monza, Hungary, and Monaco (2023), **Leclerc braked the latest** into corners (+0.88 std from field mean) and also carried the **highest minimum corner speed** (+0.69 std). A consistent pattern across three very different circuit types.
- **Verstappen was second in corner speed** (+0.67 std) despite braking earlier than Leclerc — suggests he's carrying more mechanical grip rather than relying on late braking.

---

## Running Phase 4 — Telemetry Signals

Loads qualifying lap telemetry for three representative circuits and extracts per-corner brake points, corner speeds, and throttle application distances.

```bash
python pipeline/telemetry_analysis.py
```

By default uses 2023. To use a different season or generate a specific head-to-head speed trace:

```bash
python pipeline/telemetry_analysis.py --year 2022
python pipeline/telemetry_analysis.py --compare HAM RUS   # speed trace overlay
```

**What you get:**
- `data/telemetry_signals.parquet` — one row per driver per corner per circuit (180 rows for 2023). Key columns: `brake_point_m`, `min_speed_kmh`, `throttle_point_m`, and their `_norm` versions (z-scores vs field).
- `data/charts/telemetry/braking_CIRCUIT.png` — bar chart of brake points vs field mean, one per circuit
- `data/charts/telemetry/speed_A_vs_B_CIRCUIT.png` — overlaid speed traces with delta shading

**How braking zone detection works:**

The script first runs through the pole lap to identify the three hardest braking zones on the circuit (ranked by entry speed). Then every driver gets measured at those same zones. For each zone we find where that driver's own brakes first went on (in a 150m search window around the reference point), which is the brake point. Min corner speed and throttle application come from the telemetry in the 200m window past the end of braking.

---

## Tech Stack

| Layer | Tools |
|---|---|
| Data | FastF1, Pandas, NumPy, PyArrow |
| ML / ratings | XGBoost, LightGBM, scikit-learn, SciPy |
| Backend (planned) | FastAPI, Uvicorn |
| Frontend (planned) | Next.js, React Three Fiber, GSAP, Recharts, Tailwind CSS |

---

*CPSC 371 — F1 Driver Skill Decomposition Engine*
