from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import SVR
from xgboost import XGBRegressor

from house_prices_core import (
    build_preprocessor,
    clean_structural_missing,
    make_features,
    make_splits,
    read_competition_data,
    remove_training_outliers,
    seed_everything,
)

BASE_SEEDS = (42, 123, 2026)
META_SEEDS = (11, 42, 123, 321, 777, 999, 2026, 31415)
BLEND_PENALTY = 0.01
MODEL_NAMES = ("ElasticNet_Domain", "GradientBoosting", "XGBoost", "SVR_RBF")

FEATURE_GROUPS = {
    "ElasticNet_Domain": ("totals", "ages", "ordinal", "nonlinear"),
    "GradientBoosting": ("totals", "ages", "flags", "interactions", "cyclic"),
    "XGBoost": ("totals",),
    "SVR_RBF": (
        "totals",
        "ages",
        "flags",
        "interactions",
        "cyclic",
        "ordinal",
        "nonlinear",
    ),
}

ELASTIC_PARAMS = {
    "alpha": 0.0005085209676210546,
    "l1_ratio": 0.9997910963111475,
    "max_iter": 50_000,
}

GRADIENT_PARAMS = {
    "n_estimators": 2800,
    "learning_rate": 0.023328211181511682,
    "max_depth": 3,
    "min_samples_leaf": 12,
    "min_samples_split": 9,
    "max_features": "sqrt",
    "loss": "huber",
    "alpha": 0.9166708873156382,
}

XGBOOST_PARAMS = {
    "objective": "reg:squarederror",
    "n_estimators": 1400,
    "learning_rate": 0.05236485826854344,
    "max_depth": 2,
    "min_child_weight": 1.3908030837652405,
    "subsample": 0.6709462531373701,
    "colsample_bytree": 0.5429536697038518,
    "reg_alpha": 0.00022725203021403377,
    "reg_lambda": 1.6573381198742205,
    "gamma": 0.0040391137250091365,
    "n_jobs": -1,
    "tree_method": "hist",
}


class LotFrontageByNeighborhood(BaseEstimator, TransformerMixin):
    """Fill missing frontage from fold-fitted neighborhood medians."""

    def fit(self, features, target=None):
        frame = pd.DataFrame(features)
        self.neighborhood_medians_ = frame.groupby("Neighborhood")["LotFrontage"].median()
        self.global_median_ = float(frame["LotFrontage"].median())
        return self

    def transform(self, features):
        frame = pd.DataFrame(features).copy()
        neighborhood_value = frame["Neighborhood"].map(self.neighborhood_medians_)
        frame["LotFrontage"] = (
            frame["LotFrontage"].fillna(neighborhood_value).fillna(self.global_median_)
        )
        return frame


def rmse(actual, predicted) -> float:
    return float(np.sqrt(mean_squared_error(actual, predicted)))


def stratified_splits(target: pd.Series, seed: int):
    bins = pd.qcut(target, 10, labels=False, duplicates="drop")
    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    return list(splitter.split(np.arange(len(target)), bins))


def build_model(name: str, seed: int):
    if name == "ElasticNet_Domain":
        return ElasticNet(**ELASTIC_PARAMS)
    if name == "GradientBoosting":
        return GradientBoostingRegressor(**GRADIENT_PARAMS, random_state=seed)
    if name == "XGBoost":
        return XGBRegressor(**XGBOOST_PARAMS, random_state=seed)
    if name == "SVR_RBF":
        return SVR(C=40, epsilon=0.02, gamma=0.0003)
    raise ValueError(f"Unknown model: {name}")


def build_pipeline(features: pd.DataFrame, name: str, seed: int) -> Pipeline:
    linear_or_kernel = name in {"ElasticNet_Domain", "SVR_RBF"}
    steps = []
    if name == "SVR_RBF":
        steps.append(("lot_frontage", LotFrontageByNeighborhood()))
    steps.extend(
        [
            (
                "preprocessor",
                build_preprocessor(
                    features,
                    scale_numeric=linear_or_kernel,
                    log_skewed=linear_or_kernel,
                    dense=name == "GradientBoosting",
                ),
            ),
            ("model", build_model(name, seed)),
        ]
    )
    return Pipeline(steps)


def fit_base_model(
    name: str,
    train_features: pd.DataFrame,
    target: pd.Series,
    test_features: pd.DataFrame,
):
    oof_by_seed = []
    test_by_seed = []
    rows = []

    for seed in BASE_SEEDS:
        splits = (
            stratified_splits(target, seed)
            if name == "SVR_RBF"
            else make_splits(len(target), seed=seed)
        )
        pipeline = build_pipeline(train_features, name, seed)
        oof = np.zeros(len(target))
        test_folds = []
        fold_scores = []

        for fold, (train_index, valid_index) in enumerate(splits, start=1):
            model = clone(pipeline)
            model.fit(train_features.iloc[train_index], target.iloc[train_index])
            validation_prediction = model.predict(train_features.iloc[valid_index])
            oof[valid_index] = validation_prediction
            test_folds.append(model.predict(test_features))
            fold_scores.append(rmse(target.iloc[valid_index], validation_prediction))
            print(f"{name} seed={seed} fold={fold} rmse={fold_scores[-1]:.6f}")

        oof_by_seed.append(oof)
        test_by_seed.append(np.mean(test_folds, axis=0))
        rows.append(
            {
                "model": name,
                "seed": seed,
                "oof_rmse": rmse(target, oof),
                "fold_mean_rmse": float(np.mean(fold_scores)),
                "fold_std_rmse": float(np.std(fold_scores, ddof=1)),
                "fold_scores": json.dumps(fold_scores),
            }
        )

    return np.mean(oof_by_seed, axis=0), np.mean(test_by_seed, axis=0), rows


def optimize_weights(predictions: np.ndarray, target: np.ndarray) -> np.ndarray:
    model_count = predictions.shape[1]
    result = minimize(
        lambda weights: np.mean((target - predictions @ weights) ** 2)
        + BLEND_PENALTY * np.sum(weights**2),
        np.full(model_count, 1 / model_count),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * model_count,
        constraints={"type": "eq", "fun": lambda weights: weights.sum() - 1},
        options={"maxiter": 2000, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(result.message)
    weights = np.clip(result.x, 0, 1)
    return weights / weights.sum()


def robust_blend_weights(predictions: np.ndarray, target: pd.Series):
    fold_weights = []
    meta_rows = []
    for seed in META_SEEDS:
        prediction = np.zeros(len(target))
        seed_weights = []
        for train_index, valid_index in stratified_splits(target, seed):
            weights = optimize_weights(predictions[train_index], target.iloc[train_index].to_numpy())
            prediction[valid_index] = predictions[valid_index] @ weights
            seed_weights.append(weights)
            fold_weights.append(weights)
        meta_rows.append(
            {
                "seed": seed,
                "crossfit_rmse": rmse(target, prediction),
                "weights": json.dumps(np.mean(seed_weights, axis=0).tolist()),
            }
        )
    mean_weights = np.mean(fold_weights, axis=0)
    return mean_weights / mean_weights.sum(), meta_rows, np.asarray(fold_weights)


def calibrate(prediction: np.ndarray, target: pd.Series):
    centered_prediction = prediction - prediction.mean()
    centered_target = target.to_numpy() - target.mean()
    slope = float(
        np.dot(centered_prediction, centered_target)
        / np.dot(centered_prediction, centered_prediction)
    )
    slope = float(np.clip(slope, 0.98, 1.04))
    intercept = float(target.mean() - slope * prediction.mean())
    return intercept, slope


def validate_submission(submission: pd.DataFrame, sample: pd.DataFrame) -> None:
    if list(submission.columns) != ["Id", "SalePrice"]:
        raise ValueError("Submission columns must be exactly Id and SalePrice")
    if len(submission) != len(sample) or not submission["Id"].equals(sample["Id"]):
        raise ValueError("Submission Ids do not match sample_submission.csv")
    values = submission["SalePrice"].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Submission prices must be finite and positive")


def run(data_dir: Path, output_dir: Path) -> None:
    seed_everything()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_train, raw_test = read_competition_data(data_dir)
    train = clean_structural_missing(raw_train)
    test = clean_structural_missing(raw_test)
    train, removed_outliers = remove_training_outliers(train)
    target = np.log(train["SalePrice"].astype(float))

    feature_cache = {
        name: (
            make_features(train, FEATURE_GROUPS[name]),
            make_features(test, FEATURE_GROUPS[name]),
        )
        for name in MODEL_NAMES
    }

    oof_columns = []
    test_columns = []
    base_rows = []
    for name in MODEL_NAMES:
        train_features, test_features = feature_cache[name]
        oof, test_prediction, rows = fit_base_model(
            name, train_features, target, test_features
        )
        oof_columns.append(oof)
        test_columns.append(test_prediction)
        base_rows.extend(rows)

    oof_matrix = np.column_stack(oof_columns)
    test_matrix = np.column_stack(test_columns)
    weights, meta_rows, fold_weights = robust_blend_weights(oof_matrix, target)
    blend_oof = oof_matrix @ weights
    blend_test = test_matrix @ weights
    intercept, slope = calibrate(blend_oof, target)
    final_oof = intercept + slope * blend_oof
    final_test_log = intercept + slope * blend_test

    sample = pd.read_csv(data_dir / "sample_submission.csv")
    submission = sample[["Id"]].copy()
    submission["SalePrice"] = np.exp(final_test_log)
    validate_submission(submission, sample)

    pd.DataFrame(base_rows).to_csv(output_dir / "base_model_results.csv", index=False)
    pd.DataFrame(meta_rows).to_csv(output_dir / "meta_cv_results.csv", index=False)
    pd.DataFrame(
        {
            "model": MODEL_NAMES,
            "weight": weights,
            "fold_weight_std": fold_weights.std(axis=0, ddof=1),
        }
    ).to_csv(output_dir / "blend_weights.csv", index=False)
    pd.DataFrame(
        {
            "Id": train["Id"],
            "actual_log_price": target,
            **{f"{name}_oof_log": oof_matrix[:, i] for i, name in enumerate(MODEL_NAMES)},
            "blend_oof_log": blend_oof,
            "final_oof_log": final_oof,
            "residual_log": target - final_oof,
        }
    ).to_csv(output_dir / "oof_predictions.csv", index=False)
    pd.DataFrame(
        {
            "Id": test["Id"],
            **{f"{name}_test_log": test_matrix[:, i] for i, name in enumerate(MODEL_NAMES)},
            "blend_test_log": blend_test,
            "final_test_log": final_test_log,
            "SalePrice": submission["SalePrice"],
        }
    ).to_csv(output_dir / "test_predictions.csv", index=False)
    removed_outliers.to_csv(output_dir / "removed_outliers.csv", index=False)
    submission.to_csv(output_dir / "submission.csv", index=False)

    summary = {
        "metric": "RMSE on natural-log SalePrice",
        "training_rows": len(train),
        "test_rows": len(test),
        "removed_outlier_ids": removed_outliers["Id"].astype(int).tolist(),
        "base_seeds": BASE_SEEDS,
        "meta_seeds": META_SEEDS,
        "blend_penalty": BLEND_PENALTY,
        "weights": dict(zip(MODEL_NAMES, weights.tolist())),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "weighted_oof_rmse": rmse(target, blend_oof),
        "calibrated_oof_rmse": rmse(target, final_oof),
        "prediction_min": float(submission["SalePrice"].min()),
        "prediction_median": float(submission["SalePrice"].median()),
        "prediction_max": float(submission["SalePrice"].max()),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description="Train and blend the Ames house-price models")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/reproduced"))
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    run(arguments.data_dir.resolve(), arguments.output_dir.resolve())
