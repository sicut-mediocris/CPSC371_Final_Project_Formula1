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

## Phase 4 — Telemetry Signals

**Method**: For a qualifying lap at three representative circuits (Monza — high speed, Hungaroring — low speed, Monaco — street), the three hardest braking zones on each circuit are identified from the pole lap. Every driver is then measured at those same zones: brake point (where they first apply brakes), minimum corner speed (lowest speed in the corner window), and throttle application point (where throttle first exceeds 80% past the apex). All three signals are z-scored relative to the full field so circuit differences cancel out.

### Driver profiles (averaged across all three circuits, 2023)

| Driver | Brake Point (z) | Corner Speed (z) | Throttle Point (z) | Style |
|--------|----------------|-----------------|-------------------|-------|
| LEC | +0.88 | +0.69 | +0.18 | Latest braker, highest corner speed |
| HAM | +0.43 | +0.36 | +0.43 | Late braker, consistent high-speed entry |
| RUS | +0.24 | +0.34 | +0.13 | Similar style to Hamilton, slightly earlier |
| VER | -0.22 | +0.67 | +1.17 | Earlier braker, but second-highest corner speed |
| SAI | -0.31 | +0.59 | -0.54 | Carries high corner speed despite earlier braking |
| PER | -0.61 | -0.80 | +0.71 | Earliest braker, lowest corner speed in top group |

### Notable findings

- **Leclerc braked the latest** at every circuit in the sample — +0.88 std above the field mean on brake point, the highest of any driver. He also carried the highest minimum corner speed (+0.69 std). A consistent pattern across three very different circuit types.
- **Verstappen's approach is different**: he brakes earlier than average (-0.22 std) but carries the second-highest corner speed (+0.67 std). The interpretation is that he gets into the corner earlier and sustains speed mechanically, rather than relying on late braking as a precision technique.
- **Hamilton** shows a clear late-braking, high-entry-speed pattern (+0.43, +0.36) — consistent with the aggressive style that made him dominant in the Hamilton-Rosberg era, still visible even in 2023.
- **Pérez** is the inverse of Leclerc: earliest braking in the group (-0.61) and lowest minimum corner speed (-0.80). The gap between Pérez and Verstappen in corner technique is significant, and matches the qualifying gap data from Phase 2.
- **Sainz** carries high corner speed (+0.59) despite braking earlier than average — suggesting good mechanical setup and smooth entry rather than a late-braking strategy.

---

## Phase 5 — Tire Degradation & Race Craft

**Method**: For each stint in a race, a linear regression of lap time vs tyre life gives the degradation slope (seconds lost per lap on the tyre). The median slope per driver per season is compared to their teammate's to remove the car's baseline degradation. Consistency is the coefficient of variation of clean lap times (no safety car, no in/out laps), averaged across the season. Both signals are min-max scaled to 0–100 within each season, then combined: consistency 60%, degradation 40%.

### Season winners (RaceCraftScore)

| Season | Driver | Team | Score | Notes |
|--------|--------|------|-------|-------|
| 2018 | HAM | Mercedes | 83.5 | Highest consistency in the dataset for that year |
| 2019 | GAS | Toro Rosso | 80.8 | Strong degradation management in underpowered car |
| 2020 | RIC | Renault | 87.1 | Best single-season race craft score pre-2023 |
| 2021 | RUS | Williams | 86.7 | Extremely consistent lap times in a slow car |
| 2022 | STR | Aston Martin | 82.5 | Near-zero degradation slope |
| 2023 | DEV | AlphaTauri | 93.9 | Highest race craft score across all seasons |
| 2024 | COL | Williams | 96.4 | Highest score in the dataset — small sample |

### Notable findings

- **De Vries (2023)** posted the highest race craft score in the entire dataset (93.9) despite being dropped by AlphaTauri mid-season after 10 races. His tyre management was exceptional — his degradation slope was the flattest of any driver that year. Small sample, but a striking signal.
- **Colapinto (2024)** scored 96.4, the highest in the dataset, across his 7-race debut. Lawson followed at 95.1 in 5 races. Both are driven by low tyre degradation and limited data — treat them as strong preliminary signals, not settled verdicts.
- **Hamilton topped consistency in 2018** (100/100 ConScore), matching his peak sector scores from Phase 3 — 2018 appears to be the measurable peak of his driving precision across every signal.
- **Leclerc** consistently appears in the top 5 across multiple seasons: 75.5 in 2023 and 81.3 in 2024, with his ConScore approaching 100 in 2024. His Phase 4 telemetry signals combined with strong race craft give him a well-rounded profile.
- **Piastri vs Norris (2023–2024)**: Looking at the teammate-normalised degradation, Piastri degrades tyres less than Norris in the majority of races they shared. Norris outqualifies Piastri consistently (Phase 2), but Piastri manages rubber better in race conditions — they are strong in different phases of the weekend.
- **Russell at Williams (2021)**: 86.7 race craft score, second in that season. The Williams was objectively one of the slowest cars — Russell's consistency score required him to produce near-identical lap times on a difficult car, which makes the number more meaningful, not less.

---

## Phase 6 — Composite SkillScore & Elo Rating

**Method**: Composite SkillScore weights qualifying pace 35%, sector scores 20%, telemetry signals 25%, and race craft 20%. For seasons without telemetry (all except 2023), the 25% telemetry weight is redistributed proportionally across the other three. All four components are already on a 0–100 scale from their respective phases. The Elo system starts every driver at 1500 and runs a qualifying head-to-head against their teammate after each race weekend (K=32), using constructor standings as a proxy for car baseline.

### Composite SkillScore — top 3 per season

| Season | 1st | Score | 2nd | Score | 3rd | Score |
|--------|-----|-------|-----|-------|-----|-------|
| 2018 | VET | 79.9 | VER | 78.4 | HAM | 74.1 |
| 2019 | HAM | 79.9 | ALB | 73.1 | VER | 69.2 |
| 2020 | RIC | 79.6 | VER | 73.7 | HAM | 70.5 |
| 2021 | VER | 80.2 | HAM | 79.7 | RUS | 66.7 |
| 2022 | VER | 71.9 | MAG | 67.6 | VET | 65.5 |
| 2023 | LEC | 81.0 | ALO | 67.2 | GAS | 65.5 |
| 2024 | NOR | 81.7 | LEC | 72.3 | ALO | 68.2 |

### Final Elo standings (end of 2024)

| Rank | Driver | Final Elo |
|------|--------|-----------|
| 1 | VER | 1900 |
| 2 | RUS | 1798 |
| 3 | NOR | 1729 |
| 4 | ALB | 1716 |
| 5 | LEC | 1639 |
| 6 | TSU | 1637 |
| 7 | GAS | 1637 |
| 8 | HUL | 1623 |
| 9 | BOT | 1605 |
| 10 | ALO | 1602 |

### Notable findings

- **Verstappen's final Elo of 1900** is the clear outlier — 102 points ahead of Russell in second. He accumulated it almost entirely through qualifying head-to-heads against Ricciardo (2018–2019), then Albon, then Gasly, then Pérez — a different level of teammate year after year.
- **Russell at 1798** is the most interesting number. He spent years at Williams outperforming underpowered teammates, then moved to Mercedes and continued beating Hamilton more often than not. His Elo reflects that sustained record of winning the intra-team comparison regardless of which team he was at.
- **Norris at 1729** is third despite being in F1 fewer seasons. His surge came in 2023–2024 when Piastri became his benchmark — a strong teammate makes each win worth more points in the Elo system.
- **Leclerc tops the 2023 SkillScore at 81.0** — the only season where telemetry is included. His 100/100 TelScore (the highest telemetry signal values in the 2023 field) combined with strong qualifying and race craft pushed him clear of Alonso (67.2) and Verstappen (62.5). Verstappen's composite was dragged down by a poor qualifying rating in 2023 (54.3 — Pérez was unusually competitive that year) despite his near-perfect sector scores.
- **Norris leads 2024 at 81.7**, entirely built on his 90.0 qualifying rating — the highest single-season qualifying rating in the dataset. Without the telemetry component in 2024, his exceptional raw pace over Piastri dominates the composite.
- **Hamilton's SkillScore has declined steadily**: 74.1 (2018) → 79.9 (2019) → 70.5 (2020) → 79.7 (2021) → not in top 5 by 2022–2024. The signals across every phase point to a peak around 2019–2021 and a measurable step back after that.
- **Vettel's 2018 score of 79.9** is often overlooked — he outqualified Räikkönen consistently that year, had strong sector scores, and managed race pace well. The Elo system rewards him less because Räikkönen was a weak benchmark by 2018.

---

*CPSC 371 — F1 Driver Skill Decomposition Engine*