# F1 Driver Skill Decomposition Engine

![Status](https://img.shields.io/badge/Status-In%20Development-brightgreen) ![Python](https://img.shields.io/badge/Backend-Python%20%7C%20FastF1-yellow) ![Three.js](https://img.shields.io/badge/Frontend-Three.js%20%7C%20Next.js-black)

## Overview

This project uses Machine Learning to answer one of F1's most debated questions:

> **Who are the most skilled drivers, independent of the car they're driving?**

Using per-meter telemetry, sector breakdowns, teammate comparisons, and tire degradation data from the FastF1 library, we decompose driver performance into measurable skill signals — then roll them into a season-by-season Elo-style driver rating.

The result is a system that can tell you not just who wins, but *why*, and whether a driver is overperforming or underperforming given their machinery.

---

## What Makes This Different From a Win Predictor

A standard race win predictor just learns "whoever qualified P1 in the fastest car wins." That's not insight — it's memorization. This project goes deeper:

| Skill Signal | What It Measures | Why It's Car-Independent |
|---|---|---|
| Qualifying gap to teammate | Raw one-lap pace | Same car, same conditions |
| Sector delta (S1/S2/S3) | Where on track a driver is fast | Normalised within the same car |
| Telemetry brake point | How late a driver brakes into corners | Driving style, not machinery |
| Minimum corner speed | How much speed is carried through apexes | Car control under lateral load |
| Throttle application point | How early a driver gets back on power | Confidence and car feel |
| Tire degradation rate | How gently a driver manages rubber | Race craft, not car pace |

---

## ML Architecture

- **Input**: Multi-season FastF1 data (qualifying + race sessions, 2018-2024)
- **Core Model**: Gradient Boosted Trees (XGBoost/LightGBM) per skill dimension
- **Rating System**: Elo-style cumulative driver rating updated each race weekend
- **Output**: Per-driver skill profile — overall pace, high-speed vs technical bias, race craft score, and a "true talent" rating that strips out car advantage

---

## Frontend

A premium, scroll-driven 3D interface built with Next.js and React Three Fiber:

- A 3D F1 car navigates a stylized circuit as the user scrolls
- Each section of track reveals a different skill dimension (brake points, sector times, tire curves)
- Driver comparison cards with glassmorphic design and live telemetry overlays
- Dark neon aesthetic inspired by real F1 engineer dashboards

---

## Project Structure

```
Formula1/
├── data/           # FastF1 cache and processed datasets
├── pipeline/       # Data extraction and feature engineering scripts
├── models/         # Trained ML models and evaluation notebooks
├── api/            # FastAPI backend serving skill ratings and telemetry
├── frontend/       # Next.js + React Three Fiber interface
├── explore.ipynb   # Dataset exploration and FastF1 walkthrough
└── claude.md       # Step-by-step implementation roadmap
```

---

*CPSC 371 Project — built on FastF1, XGBoost, and React Three Fiber.*
