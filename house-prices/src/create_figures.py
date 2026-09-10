from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COLORS = {
    "blue": "#2F6B8A",
    "green": "#2F7D67",
    "orange": "#D07A32",
    "red": "#B44C4C",
    "gold": "#C6A33A",
    "gray": "#66717D",
    "light": "#E8EDF1",
    "ink": "#1E2933",
}


def finish(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.labelcolor": COLORS["ink"],
            "axes.edgecolor": "#AAB3BB",
            "xtick.color": COLORS["ink"],
            "ytick.color": COLORS["ink"],
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def target_distribution(train: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    axes[0].hist(train["SalePrice"], bins=36, color=COLORS["blue"], alpha=0.88)
    axes[0].set_title("Raw SalePrice is right-skewed")
    axes[0].set_xlabel("SalePrice (USD)")
    axes[0].set_ylabel("Homes")
    axes[1].hist(np.log(train["SalePrice"]), bins=36, color=COLORS["green"], alpha=0.88)
    axes[1].set_title("Log transform stabilizes the target")
    axes[1].set_xlabel("log(SalePrice)")
    axes[1].set_ylabel("Homes")
    finish(fig, output / "01_target_distribution.png")


def missingness(train: pd.DataFrame, output: Path) -> None:
    counts = train.isna().sum().sort_values(ascending=False).head(12)
    fig, ax = plt.subplots(figsize=(8.8, 5.0))
    colors = [COLORS["orange"] if value > len(train) / 2 else COLORS["blue"] for value in counts]
    ax.barh(counts.index[::-1], counts.values[::-1], color=colors[::-1])
    ax.set_title("Missing values are often structural, not random")
    ax.set_xlabel("Missing rows in training data")
    for index, value in enumerate(counts.values[::-1]):
        ax.text(value + 15, index, f"{value}", va="center", fontsize=9)
    ax.set_xlim(0, counts.max() * 1.12)
    finish(fig, output / "02_missingness.png")


def baseline_models(results: Path, output: Path) -> None:
    frame = pd.read_csv(results / "baseline_models.csv").sort_values("oof_rmse")
    fig, ax = plt.subplots(figsize=(9.2, 5.3))
    colors = [COLORS["green"] if name in {"Lasso", "ElasticNet"} else COLORS["blue"] for name in frame["model"]]
    ax.barh(frame["model"][::-1], frame["oof_rmse"][::-1], color=colors[::-1])
    ax.set_title("Baseline model screening")
    ax.set_xlabel("5-fold OOF RMSE (lower is better)")
    ax.set_xlim(0.105, frame["oof_rmse"].max() + 0.006)
    for index, value in enumerate(frame["oof_rmse"][::-1]):
        ax.text(value + 0.0005, index, f"{value:.4f}", va="center", fontsize=8.8)
    finish(fig, output / "03_baseline_model_screening.png")


def selection_path(results: Path, output: Path) -> None:
    baseline = pd.read_csv(results / "baseline_models.csv")
    v3 = json.loads((results / "v3_summary.json").read_text(encoding="utf-8"))
    stages = pd.DataFrame(
        {
            "stage": [
                "Best single model",
                "V2 repeated blend",
                "V3 robust blend",
            ],
            "rmse": [
                float(baseline["oof_rmse"].min()),
                0.105867,
                float(v3["robust_crossfit_calibrated_rmse"]),
            ],
        }
    )
    fig, ax = plt.subplots(figsize=(9.5, 4.9))
    colors = [COLORS["blue"], COLORS["orange"], COLORS["green"]]
    bars = ax.bar(stages["stage"], stages["rmse"], color=colors, width=0.65)
    ax.set_title("Validation improved through staged model selection")
    ax.set_ylabel("OOF RMSE (lower is better)")
    ax.set_ylim(0.103, 0.1115)
    ax.text(
        0.99,
        0.95,
        "Dummy baseline: 0.39878",
        transform=ax.transAxes,
        ha="right",
        va="top",
        color=COLORS["gray"],
        fontsize=9,
    )
    for bar, value in zip(bars, stages["rmse"]):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.00018, f"{value:.5f}", ha="center")
    finish(fig, output / "04_model_selection_path.png")


def blend_weights(results: Path, output: Path) -> None:
    summary = json.loads((results / "v3_summary.json").read_text(encoding="utf-8"))
    weights = pd.Series(summary["selected_weights"]).sort_values()
    labels = {
        "ElasticNet_Domain": "Elastic Net",
        "GradientBoosting": "Gradient Boosting",
        "XGBoost": "XGBoost",
        "SVR_RBF": "RBF-SVR",
    }
    fig, ax = plt.subplots(figsize=(8.8, 4.6))
    palette = [COLORS["blue"], COLORS["orange"], COLORS["gold"], COLORS["green"]]
    ax.barh([labels[name] for name in weights.index], weights.values, color=palette)
    ax.set_title("V3 blend keeps four models at comparable influence")
    ax.set_xlabel("Final blend weight")
    ax.set_xlim(0, 0.32)
    for index, value in enumerate(weights.values):
        ax.text(value + 0.005, index, f"{value:.1%}", va="center")
    finish(fig, output / "05_blend_weights.png")


def residual_diagnostics(results: Path, output: Path) -> None:
    frame = pd.read_csv(results / "v3_oof_predictions.csv")
    frame["residual"] = frame["actual_log_price"] - frame["calibrated_oof_log"]
    frame["price_decile"] = pd.qcut(frame["actual_log_price"], 10, labels=False) + 1
    grouped = frame.groupby("price_decile")["residual"].agg(
        rmse=lambda values: float(np.sqrt(np.mean(values**2))),
        bias="mean",
    )
    grouped.to_csv(results / "v3_residual_by_price_decile.csv")

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    axes[0].bar(grouped.index, grouped["rmse"], color=COLORS["blue"])
    axes[0].set_title("Error remains largest in the price tails")
    axes[0].set_xlabel("Actual price decile")
    axes[0].set_ylabel("OOF RMSE")
    bias_colors = [COLORS["red"] if value < 0 else COLORS["green"] for value in grouped["bias"]]
    axes[1].bar(grouped.index, grouped["bias"], color=bias_colors)
    axes[1].axhline(0, color=COLORS["ink"], linewidth=1)
    axes[1].set_title("Residual bias after calibration")
    axes[1].set_xlabel("Actual price decile")
    axes[1].set_ylabel("Mean actual - predicted log price")
    finish(fig, output / "06_residual_by_price_decile.png")

    fig, ax = plt.subplots(figsize=(7.4, 6.0))
    ax.scatter(
        frame["actual_log_price"],
        frame["calibrated_oof_log"],
        s=16,
        alpha=0.52,
        color=COLORS["blue"],
        edgecolors="none",
    )
    lower = min(frame["actual_log_price"].min(), frame["calibrated_oof_log"].min())
    upper = max(frame["actual_log_price"].max(), frame["calibrated_oof_log"].max())
    ax.plot([lower, upper], [lower, upper], color=COLORS["red"], linewidth=1.4)
    ax.set_title("Out-of-fold prediction versus actual price")
    ax.set_xlabel("Actual log(SalePrice)")
    ax.set_ylabel("OOF predicted log(SalePrice)")
    finish(fig, output / "07_oof_actual_vs_predicted.png")


def prediction_distribution(train: pd.DataFrame, results: Path, output: Path) -> None:
    prediction = pd.read_csv(results / "submission_v3.csv")
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.hist(train["SalePrice"], bins=38, alpha=0.62, color=COLORS["blue"], label="Train actual")
    ax.hist(prediction["SalePrice"], bins=38, alpha=0.62, color=COLORS["orange"], label="Test prediction")
    ax.set_title("Predicted test prices stay within a plausible distribution")
    ax.set_xlabel("SalePrice (USD)")
    ax.set_ylabel("Homes")
    ax.legend(frameon=False)
    finish(fig, output / "08_prediction_distribution.png")


def kaggle_result(results: Path, output: Path) -> None:
    history = pd.read_csv(results / "kaggle_submission_history.csv")
    rank = pd.read_csv(results / "kaggle_rank_snapshot.csv").iloc[0]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    bars = axes[0].bar(history["Version"], history["PublicScore"], color=[COLORS["gray"], COLORS["green"]], width=0.55)
    axes[0].set_title("Kaggle public score improved")
    axes[0].set_ylabel("Public RMSE (lower is better)")
    axes[0].set_ylim(0.118, 0.124)
    for bar, value in zip(bars, history["PublicScore"]):
        axes[0].text(bar.get_x() + bar.get_width() / 2, value + 0.00012, f"{value:.5f}", ha="center")

    axes[1].axis("off")
    axes[1].text(0.05, 0.80, "KAGGLE SNAPSHOT", fontsize=10, color=COLORS["gray"], weight="bold")
    axes[1].text(0.05, 0.53, f"Rank {int(rank['Rank']):,}", fontsize=29, color=COLORS["ink"], weight="bold")
    axes[1].text(0.05, 0.36, f"of {int(rank['TotalTeams']):,} teams", fontsize=15, color=COLORS["gray"])
    axes[1].text(0.05, 0.18, f"Top {float(rank['TopPercent']):.2f}%  |  2026-08-24", fontsize=13, color=COLORS["green"], weight="bold")
    finish(fig, output / "09_kaggle_result.png")


def validation_gap(results: Path, output: Path) -> None:
    summary = json.loads((results / "v3_summary.json").read_text(encoding="utf-8"))
    local = float(summary["robust_crossfit_calibrated_rmse"])
    public = float(pd.read_csv(results / "kaggle_rank_snapshot.csv").iloc[0]["Score"])
    labels = ["Robust local CV", "Kaggle public"]
    values = [local, public]
    fig, ax = plt.subplots(figsize=(7.7, 4.6))
    bars = ax.bar(labels, values, color=[COLORS["blue"], COLORS["orange"]], width=0.58)
    ax.set_title("The public score exposes remaining validation optimism")
    ax.set_ylabel("RMSE (lower is better)")
    ax.set_ylim(0.095, 0.126)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.0006, f"{value:.5f}", ha="center")
    ax.annotate(
        f"gap = {public - local:.5f}",
        xy=(1, public),
        xytext=(0.52, public + 0.003),
        arrowprops={"arrowstyle": "->", "color": COLORS["red"]},
        color=COLORS["red"],
        weight="bold",
    )
    finish(fig, output / "10_validation_gap.png")


def main(data_dir: Path, results: Path, output: Path) -> None:
    style()
    output.mkdir(parents=True, exist_ok=True)
    train = pd.read_csv(data_dir / "train.csv", keep_default_na=False, na_values=["NA", ""])
    target_distribution(train, output)
    missingness(train, output)
    baseline_models(results, output)
    selection_path(results, output)
    blend_weights(results, output)
    residual_diagnostics(results, output)
    prediction_distribution(train, results, output)
    kaggle_result(results, output)
    validation_gap(results, output)
    manifest = sorted(
        path.name for path in output.glob("*.png") if not path.name.startswith("_")
    )
    (output / "chart_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Generated {len(manifest)} figures in {output}")


def parse_args():
    parser = argparse.ArgumentParser(description="Create portfolio charts")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args.data_dir.resolve(), args.results_dir.resolve(), args.output_dir.resolve())
