# Project: F1 Driver Skill Decomposition Engine

## Objective

Build an ML system that isolates and quantifies F1 driver skill independent of car performance, using FastF1 telemetry, sector times, and teammate comparisons. Serve the results through a premium 3D scrollable frontend.

The core question: **Who is actually the most skilled driver, if you remove the car from the equation?**

## Key Features

1. **Multi-Signal Skill Pipeline (Python, FastF1, XGBoost/LightGBM)**
   - Teammate qualifying gap (same car → pure pace signal)
   - Sector-by-sector performance delta (S1/S2/S3 specialization)
   - Telemetry analysis: brake points, corner speed, throttle application per meter
   - Tire degradation curves across stints (race craft signal)
   - Elo-style driver rating accumulated across seasons

2. **Immersive 3D Frontend (Next.js, React Three Fiber, GSAP)**
   - Scroll-driven 3D F1 car moving around a stylized circuit
   - Each section of the track reveals a different skill dimension
   - Glassmorphic driver comparison cards with live telemetry overlays
   - Dark neon aesthetic inspired by real F1 engineer dashboards

---

## Data Available (FastF1)

Each session loaded from FastF1 gives four layers:

| Layer | Key Fields |
|---|---|
| `session.results` | Q1/Q2/Q3 times, final position, grid position, team |
| `session.laps` | LapTime, Sector1/2/3Time, Compound, TyreLife, FreshTyre, Stint, SpeedI1/I2/FL/ST, IsAccurate |
| `session.weather_data` | AirTemp, TrackTemp, Humidity, WindSpeed (time-series) |
| `lap.get_telemetry()` | Speed, Throttle, Brake, nGear, RPM, DRS at per-meter resolution |

Sessions to load: `'Q'` (Qualifying) and `'R'` (Race) for each Grand Prix weekend.

---

## Step-by-Step Implementation

### Phase 1: Multi-Season Data Pipeline

> "Build a Python data pipeline using FastF1 that collects both Qualifying ('Q') and Race ('R') session data for every Grand Prix from 2018 to 2024. For each session, extract: session.results (driver, team, positions, Q1/Q2/Q3 times), session.laps (all lap rows with sector times, tire compound, tyre life, speed traps, IsAccurate flag), and session.weather_data (track/air temp, humidity). Enable FastF1's cache. Export two clean Parquet files: one for qualifying data and one for race lap data. Include logging and graceful error handling for sessions that fail to load."

### Phase 2: Teammate Comparison & Qualifying Pace Rating

> "Using the qualifying Parquet from Phase 1, build a teammate gap analysis. For each race weekend, pair each driver with their teammate (same TeamName). Calculate: the gap in Q3 time (or best Q-session time if a driver didn't reach Q3), expressed as a percentage delta relative to the faster driver. Aggregate across the season to produce a qualifying pace rating per driver per season. Drivers who consistently beat their teammate score higher. Output a DataFrame with columns: Season, Driver, Team, AvgQualiGapVsTeammate, QualiRating. Visualize the top 10 drivers per season as a horizontal bar chart."

### Phase 3: Sector Specialization Profile

> "Using session.laps data, compute each driver's sector strengths. For every race weekend, take each driver's best accurate lap and extract Sector1Time, Sector2Time, Sector3Time. Normalise each sector time relative to the session's fastest sector time in that sector (giving a 0-to-1 score where 0 = fastest in field). Aggregate per driver per season. This produces three scores per driver: S1 (high-speed corners), S2 (mixed), S3 (technical/slow corners). Plot a radar/spider chart per driver showing their sector fingerprint. Flag drivers who are outliers in specific sectors."

### Phase 4: Telemetry Skill Signals

> "For a representative sample of circuits (one low-speed, one high-speed, one street circuit), extract telemetry for each driver's fastest qualifying lap using lap.get_telemetry().add_distance(). Compute these signals: (1) Brake point — the track distance at which the driver first applies brakes before the three hardest braking zones on each circuit. (2) Minimum corner speed — the lowest Speed value in each corner's distance window. (3) Throttle application point — the distance after apex where Throttle first exceeds 80%. Normalise each signal relative to teammates or the full field. Output a telemetry_signals DataFrame with one row per driver per corner per session."

### Phase 5: Tire Degradation & Race Craft Score

> "Using race session laps from Phase 1, compute tire degradation rates. For each stint (group by Driver + Stint), fit a linear regression of LapTime (in seconds) vs TyreLife (laps on the tire). The slope is the degradation rate — steeper = tires wearing faster. Normalise this relative to the driver's teammate in the same race to control for car. Aggregate per driver per season into a RaceCraftScore. Also compute a consistency score: the standard deviation of lap times in clean air stints (no safety car, no pit in/out laps). Combine degradation and consistency into a single race craft metric."

### Phase 6: Elo Driver Rating System

> "Combine the four skill signals from Phases 2-5 into a unified driver rating. Assign weights: qualifying pace 35%, sector specialization 20%, telemetry signals 25%, race craft 20%. Normalize each component to a 0-100 scale. Compute a weighted composite SkillScore per driver per season. Then build an Elo-style system that updates a driver's rating after each race weekend based on their performance vs the field expectation given their car's pace (use constructor standings as a proxy for car strength). Plot the Elo trajectory for the top 10 drivers across 2018-2024."

### Phase 7: FastAPI Backend

> "Build a FastAPI backend that serves the skill rating data to the frontend. Endpoints needed: GET /drivers — list of all drivers with their latest Elo rating and season SkillScore. GET /driver/{driver_code} — full skill breakdown (quali rating, sector profile, telemetry signals, race craft, Elo history). GET /compare/{driver_a}/{driver_b} — head-to-head comparison of two drivers across all skill dimensions. GET /telemetry/{driver_code}/{year}/{circuit} — raw telemetry data for a specific lap. Include CORS middleware. Load pre-computed DataFrames from Parquet files at startup."

### Phase 8: 3D Frontend — Foundation & Design System

> "Set up a Next.js project with Tailwind CSS and React Three Fiber. Create a global design system: background #0a0a0f, primary accent #E10600 (F1 red), secondary accent #00D2BE (teal), glassmorphic cards with backdrop-filter blur. Build the landing page hero section with a large headline ('Who is F1's Most Skilled Driver?'), a subheading, and a driver search/select input. The hero should sit above a WebGL canvas that renders a simple dark 3D scene as a teaser."

### Phase 9: Scroll-Driven 3D Experience

> "Implement the scroll-driven 3D experience. A 3D F1 car model follows a curved path around a stylized circuit as the user scrolls. Use GSAP ScrollTrigger to map scroll position to the car's position on the path. Divide the circuit into sections — each section corresponds to a skill dimension (Qualifying Pace, Sector Profile, Telemetry, Race Craft, Overall Rating). As the car enters each section, the corresponding data panel fades in from the side using Framer Motion. The 3D scene should be rendered in React Three Fiber with post-processing bloom for neon glow effects."

### Phase 10: Data Visualization & Driver Comparison UI

> "Build the data visualization panels that overlay the 3D scene. For each skill section: (1) Qualifying section — animated bar chart of teammate gap using Recharts, styled dark. (2) Sector section — radar/spider chart of S1/S2/S3 strengths. (3) Telemetry section — speed trace comparison chart for two drivers on the same circuit, with color-coded delta shading. (4) Race Craft section — tire degradation slope chart. (5) Overall Rating section — Elo trajectory line chart. Add a driver selector at the top that lets users pick any two drivers to compare, fetching data live from the FastAPI backend."

---

## Tech Stack

| Layer | Tools |
|---|---|
| Data | FastF1, Pandas, NumPy |
| ML | XGBoost, LightGBM, scikit-learn, SciPy (linear regression) |
| Backend | FastAPI, Uvicorn, Parquet (pyarrow) |
| Frontend | Next.js, React Three Fiber, Three.js, GSAP, Framer Motion, Recharts, Tailwind CSS |

---

*CPSC 371 Project — F1 Driver Skill Decomposition Engine.*
