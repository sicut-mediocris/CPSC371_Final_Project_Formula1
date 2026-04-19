"""

Team : Unsupervised Men
Sukirat Singh Dhillon, 230155722
Akshay ArulKrishnan , 230158634
Karsten Keiji Qi-Zhi Ngai-Natsuhara,230165205
Amaan Hingora, 230156282

Phase 7: Supervised ML — Race Finishing Position Predictor
===========================================================
Uses the skill signals from Phases 2-6 as features to predict where each
driver finishes in a race. The goal is to show that the signals we built
capture something real: if you know a driver's skill profile and where they
start, you can predict where they finish better than a naive baseline.

Features:
    QualiRating     — season-level qualifying pace vs teammate (Phase 2)
    SectorScore     — season-level sector performance (Phase 3)
    RaceCraftScore  — season-level tyre management + consistency (Phase 5)
    SeasonStartElo  — Elo accumulated by the start of this season (Phase 6)
    GridPosition    — starting grid position for this specific race
    TeamAvgFinish   — constructor's average finish this season (car proxy)

Target: FinishPosition (1–20)

Train/test split: 2018–2022 → train, 2023–2024 → test (temporal holdout,
no leakage from future races into training features).

Usage:
    python pipeline/race_predictor.py
"""

import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CHARTS_DIR = DATA_DIR / "charts" / "ml"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

FEATURES = [
    "QualiRating",
    "SectorScore",
    "RaceCraftScore",
    "SeasonStartElo",
    "GridPosition",
    "TeamAvgFinish",
]
TARGET = "FinishPosition"


# ---------------------------------------------------------------------------
# Dataset builder
# ---------------------------------------------------------------------------

def build_dataset() -> pd.DataFrame:
    log.info("Loading parquet files...")

    laps = pd.read_parquet(DATA_DIR / "race_laps_data.parquet")
    skills = pd.read_parquet(DATA_DIR / "skill_scores.parquet")
    elo = pd.read_parquet(DATA_DIR / "elo_history.parquet")

    # One row per driver per race (FinishPosition is the same on every lap)
    result_cols = ["Year", "Round", "CircuitName", "Driver", "Team",
                   "FinishPosition", "GridPosition"]
    available = [c for c in result_cols if c in laps.columns]
    races = (
        laps[available]
        .dropna(subset=["FinishPosition", "GridPosition"])
        .drop_duplicates(subset=["Year", "Round", "Driver"])
        .copy()
    )
    races["FinishPosition"] = races["FinishPosition"].astype(int)
    races["GridPosition"] = races["GridPosition"].astype(int)
    log.info(f"  Race results: {len(races)} driver-race rows")

    # Constructor car proxy: average finish position per team per season
    team_avg = (
        races.groupby(["Year", "Team"])["FinishPosition"]
        .mean()
        .reset_index()
        .rename(columns={"FinishPosition": "TeamAvgFinish"})
    )

    # Season-start Elo: a driver's Elo at the END of the previous season.
    # For a driver's first season, this is 1500 (the starting value).
    season_end_elo = (
        elo.sort_values(["Driver", "Year", "Round"])
        .groupby(["Driver", "Year"])
        .last()
        .reset_index()[["Driver", "Year", "Elo"]]
        .rename(columns={"Elo": "SeasonEndElo", "Year": "EloYear"})
    )
    season_end_elo["Year"] = season_end_elo["EloYear"] + 1  # shift: end of N → start of N+1
    season_start_elo = season_end_elo[["Driver", "Year", "SeasonEndElo"]].rename(
        columns={"SeasonEndElo": "SeasonStartElo"}
    )

    # Merge everything together
    df = races.merge(
        skills[["Year", "Driver", "QualiRating", "SectorScore", "RaceCraftScore"]],
        on=["Year", "Driver"],
        how="left",
    )
    df = df.merge(season_start_elo, on=["Year", "Driver"], how="left")
    df = df.merge(team_avg, on=["Year", "Team"], how="left")

    # Drivers with no prior Elo history start at 1500
    df["SeasonStartElo"] = df["SeasonStartElo"].fillna(1500.0)

    # Drop rows missing any feature (mainly drivers without enough data for skill scores)
    before = len(df)
    df = df.dropna(subset=FEATURES)
    log.info(f"  After dropping missing features: {len(df)} rows ({before - len(df)} dropped)")

    return df


# ---------------------------------------------------------------------------
# Training and evaluation
# ---------------------------------------------------------------------------

def train_and_evaluate(df: pd.DataFrame):
    train = df[df["Year"] <= 2022].copy()
    test  = df[df["Year"] >= 2023].copy()

    X_train, y_train = train[FEATURES], train[TARGET]
    X_test,  y_test  = test[FEATURES],  test[TARGET]

    log.info(f"  Train: {len(train)} rows ({train['Year'].min()}–{train['Year'].max()})")
    log.info(f"  Test:  {len(test)} rows ({test['Year'].min()}–{test['Year'].max()})")

    # Baseline: always predict the mean finishing position from the training set
    baseline_pred = np.full(len(y_test), y_train.mean())
    baseline_mae  = mean_absolute_error(y_test, baseline_pred)
    log.info(f"\n  Baseline MAE (predict mean position {y_train.mean():.1f}): {baseline_mae:.2f}")

    # Linear ridge regression (interpretable baseline model)
    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc  = scaler.transform(X_test)
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train_sc, y_train)
    ridge_preds = ridge.predict(X_test_sc)
    ridge_mae   = mean_absolute_error(y_test, ridge_preds)
    log.info(f"  Ridge regression MAE: {ridge_mae:.2f}")

    # XGBoost
    model = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        random_state=42,
        verbosity=0,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )
    xgb_preds = model.predict(X_test)
    xgb_mae   = mean_absolute_error(y_test, xgb_preds)
    xgb_rmse  = np.sqrt(((y_test - xgb_preds) ** 2).mean())

    # Within-N-positions accuracy
    for n in [3, 5]:
        acc = (np.abs(y_test - xgb_preds) <= n).mean() * 100
        log.info(f"  XGBoost within ±{n} positions: {acc:.1f}%")

    log.info(f"  XGBoost MAE:  {xgb_mae:.2f}  (baseline: {baseline_mae:.2f})")
    log.info(f"  XGBoost RMSE: {xgb_rmse:.2f}")

    # Save predictions
    test = test.copy()
    test["PredictedPosition"] = np.clip(np.round(xgb_preds), 1, 20).astype(int)
    test["Error"] = (test["PredictedPosition"] - test[TARGET]).abs()
    test[["Year","Round","CircuitName","Driver","Team",
          TARGET,"GridPosition","PredictedPosition","Error"]].to_parquet(
        DATA_DIR / "race_predictions.parquet", index=False
    )

    return model, ridge, scaler, test, xgb_preds, y_test, baseline_mae, ridge_mae, xgb_mae


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def plot_feature_importance(model):
    importance = pd.Series(model.feature_importances_, index=FEATURES).sort_values()

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("#0a0a0f")
    ax.set_facecolor("#0a0a0f")

    colors = ["#E10600" if f != "GridPosition" else "#00D2BE" for f in importance.index]
    importance.plot(kind="barh", ax=ax, color=colors)

    ax.set_xlabel("Feature Importance (gain)", color="white")
    ax.set_title("XGBoost Feature Importance\nRace Position Predictor", color="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    ax.text(
        0.99, 0.02,
        "Red = skill signals   Teal = grid position (car + quali)",
        transform=ax.transAxes, ha="right", va="bottom",
        fontsize=8, color="#aaa",
    )

    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "feature_importance.png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info("  Saved feature_importance.png")


def plot_pred_vs_actual(preds, actual):
    fig, ax = plt.subplots(figsize=(6, 6))
    fig.patch.set_facecolor("#0a0a0f")
    ax.set_facecolor("#0a0a0f")

    ax.scatter(actual, preds, alpha=0.25, s=8, color="#00D2BE")
    ax.plot([1, 20], [1, 20], color="#E10600", linewidth=1, linestyle="--", label="perfect")
    ax.set_xlabel("Actual Finishing Position", color="white")
    ax.set_ylabel("Predicted Finishing Position", color="white")
    ax.set_title("Predicted vs Actual\n2023–2024 Test Set", color="white")
    ax.tick_params(colors="white")
    ax.legend(facecolor="#1a1a1f", labelcolor="white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")

    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "pred_vs_actual.png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info("  Saved pred_vs_actual.png")


def plot_mae_comparison(baseline_mae, ridge_mae, xgb_mae):
    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_facecolor("#0a0a0f")
    ax.set_facecolor("#0a0a0f")

    labels = ["Baseline\n(predict mean)", "Ridge\nRegression", "XGBoost"]
    values = [baseline_mae, ridge_mae, xgb_mae]
    colors = ["#555", "#888", "#E10600"]

    bars = ax.bar(labels, values, color=colors, width=0.5)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{val:.2f}", ha="center", va="bottom", color="white", fontsize=11)

    ax.set_ylabel("Mean Absolute Error (positions)", color="white")
    ax.set_title("Model Comparison — Test MAE (2023–2024)", color="white")
    ax.tick_params(colors="white")
    ax.set_ylim(0, max(values) * 1.2)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")

    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "model_comparison.png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info("  Saved model_comparison.png")


def plot_driver_errors(test_df):
    driver_err = (
        test_df.groupby("Driver")["Error"]
        .mean()
        .sort_values(ascending=False)
        .head(15)
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor("#0a0a0f")
    ax.set_facecolor("#0a0a0f")

    driver_err.plot(kind="bar", ax=ax, color="#E10600")
    ax.set_ylabel("Mean Absolute Error (positions)", color="white")
    ax.set_title("Hardest Drivers to Predict — 2023–2024", color="white")
    ax.tick_params(colors="white", axis="both")
    ax.tick_params(axis="x", rotation=45)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")

    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "driver_errors.png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info("  Saved driver_errors.png")


def plot_ridge_coefficients(ridge, scaler):
    coefs = pd.Series(ridge.coef_, index=FEATURES).sort_values()

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("#0a0a0f")
    ax.set_facecolor("#0a0a0f")

    colors = ["#E10600" if v > 0 else "#00D2BE" for v in coefs]
    coefs.plot(kind="barh", ax=ax, color=colors)
    ax.axvline(0, color="white", linewidth=0.5)
    ax.set_xlabel("Coefficient (standardized features → positions)", color="white")
    ax.set_title("Ridge Regression Coefficients\n(positive = higher position number = worse finish)",
                 color="white")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")

    fig.tight_layout()
    fig.savefig(CHARTS_DIR / "ridge_coefficients.png", dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    log.info("  Saved ridge_coefficients.png")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("Phase 7 — Race Position Predictor")
    log.info("=" * 60)

    df = build_dataset()
    log.info(f"\nDataset: {len(df)} rows | {df['Year'].nunique()} seasons | "
             f"{df['Driver'].nunique()} drivers\n")

    log.info("Training models...")
    model, ridge, scaler, test_df, xgb_preds, y_test, baseline_mae, ridge_mae, xgb_mae = \
        train_and_evaluate(df)

    log.info("\nGenerating charts...")
    plot_feature_importance(model)
    plot_pred_vs_actual(xgb_preds, y_test.values)
    plot_mae_comparison(baseline_mae, ridge_mae, xgb_mae)
    plot_driver_errors(test_df)
    plot_ridge_coefficients(ridge, scaler)

    log.info(f"\nAll outputs saved to {DATA_DIR}")
    log.info(f"  data/race_predictions.parquet")
    log.info(f"  data/charts/ml/")
    log.info("\nDone.")
