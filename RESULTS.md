# F1 Driver Skill Decomposition — Results Summary

> Auto-generated from pipeline outputs. Re-run `python pipeline/generate_summary.py` to refresh.

---

## Dataset

- **Seasons covered**: 2018–2024 (7 seasons)
- **Drivers analysed**: 36 unique driver codes
- **Race weekends**: 149 qualifying sessions with teammate pairs

---

## Phase 2 — Qualifying Pace vs Teammate

**Method**: For each race weekend, each driver is paired with their teammate. Because both are in the same car, any qualifying gap is purely the driver. The QualiRating (0–100) combines win rate (60%) and average gap margin (40%), normalised within the season so ratings reflect performance relative to that year's grid.

### Season winners (who consistently outqualified their teammate)

| Season | Driver | Team | Rating | Win Rate | Avg Gap |
|--------|--------|------|--------|----------|---------|
| 2018 | HUL | Renault | 85.7 | 76% | -83 ms |
| 2019 | RUS | Williams | 85.6 | 100% | -625 ms |
| 2020 | RIC | Renault | 88.0 | 82% | -239 ms |
| 2021 | VER | Red Bull Racing | 87.9 | 95% | -679 ms |
| 2022 | VET | Aston Martin | 80.2 | 68% | -164 ms |
| 2023 | BOT | Alfa Romeo | 83.6 | 73% | -653 ms |
| 2024 | NOR | McLaren | 90.0 | 83% | -190 ms |

### Most consistently dominant qualifiers (avg rating across all seasons)

- **SIR** (Williams): 75.1 avg rating
- **VER** (Red Bull Racing): 71.3 avg rating
- **ALO** (Aston Martin): 67.2 avg rating
- **HAM** (Mercedes): 65.3 avg rating
- **RUS** (Mercedes): 65.3 avg rating

### Largest single qualifying gap on record
**VER** vs PER at Austrian Grand Prix 2023: **96.75%** (-62297 ms)

### Notable findings

- **George Russell at Williams (2019)**: 100% win rate against teammate — he outqualified Robert Kubica at every single race weekend that season. This is the signal that put him on Mercedes' radar.
- **Verstappen vs Pérez (2021)**: 95% win rate with an average gap of -679 ms. Both drivers had the same Red Bull — the gap is purely driver.
- **Norris (2024)**: highest single-season rating in the dataset at 90.0, with a 83% win rate over Piastri.

---

## Phase 3 — Sector Specialization Profile

**Method**: From each driver's best clean, green-flag race lap per weekend, sector times are min-max scaled within the session (1.0 = fastest in field, 0.0 = slowest). Season profiles use the median across all weekends to reduce the effect of outlier laps. S1 corresponds to high-speed sections, S2 to mixed, S3 to tight technical corners.

### Top 5 drivers by overall sector score — 2024

| Driver | Team | S1 | S2 | S3 | Overall |
|--------|------|----|----|----|---------|
| NOR | McLaren | 0.889 | 0.737 | 0.779 | 0.802 |
| VER | Red Bull Racing | 0.770 | 0.722 | 0.795 | 0.762 |
| PIA | McLaren | 0.698 | 0.715 | 0.707 | 0.706 |
| PER | Red Bull Racing | 0.705 | 0.639 | 0.707 | 0.684 |
| RUS | Mercedes | 0.704 | 0.715 | 0.627 | 0.682 |

### Sector specialists (drivers with the strongest bias in one sector)

**S1 — High-speed corners** (fast, sweeping sections like Silverstone S1 or Spa Raidillon):
Top specialists — NOR (2019), DEV (2023), BOT (2023)

**S2 — Mixed** (combinations of medium-speed and braking zones):
Top specialists — LAW (2023), VER (2023), GRO (2018)

**S3 — Technical corners** (slow, precise sections like Monaco or the final chicanes):
Top specialists — ZHO (2022), GAS (2020), HAM (2020)

### Hamilton's sector score decline (2018 → 2024)

| Year | S1 | S2 | S3 | Overall |
|------|----|----|----|---------|
| 2018 | 0.892 | 0.883 | 0.869 | 0.881 |
| 2019 | 0.800 | 0.904 | 0.924 | 0.876 |
| 2020 | 0.799 | 0.903 | 0.989 | 0.897 |
| 2021 | 0.825 | 0.781 | 0.821 | 0.809 |
| 2022 | 0.818 | 0.777 | 0.768 | 0.788 |
| 2023 | 0.770 | 0.724 | 0.726 | 0.740 |
| 2024 | 0.772 | 0.557 | 0.707 | 0.679 |

Hamilton's overall score dropped 0.203 points from 2018 to 2024. His S2 score in particular fell from 0.883 to 0.557, suggesting a shift in driving style or car fit rather than raw pace loss.

### Verstappen's peak season
**2023** — overall score 0.908, with an almost perfect S2 score of **0.995**. An S2 score of 0.99 means his mixed-sector lap times were essentially at the ceiling of what the field produced that season.

---

## Phases 4–6 — Coming Soon

- **Phase 4**: Telemetry signals — brake points, minimum corner speed, throttle application per circuit
- **Phase 5**: Tire degradation & race craft score from stint regression
- **Phase 6**: Composite Elo-style driver rating combining all signals

---

*CPSC 371 — F1 Driver Skill Decomposition Engine*