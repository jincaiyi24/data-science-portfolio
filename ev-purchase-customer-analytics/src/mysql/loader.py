from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError


FEATURE_RENAME = {
    "Age": "age",
    "Annual_Income_USD": "annual_income_usd",
    "Daily_Commute_km": "daily_commute_km",
    "Number_of_Cars_Owned": "number_of_cars_owned",
    "Charging_Stations_Near_Home": "charging_stations_near_home",
    "Charging_Stations_Near_Work": "charging_stations_near_work",
    "Environmental_Concern_Level": "environmental_concern_level",
    "Gender": "gender",
    "City_Type": "city_type",
    "Current_Car_Type": "current_car_type",
    "Home_Charging_Possible": "home_charging_possible",
    "Subsidy_Available": "subsidy_available",
    "Range_Anxiety_Level": "range_anxiety_level",
    "Will_Buy_EV": "will_buy_ev",
}


@dataclass
class PreparedTables:
    features: pd.DataFrame
    predictions: pd.DataFrame
    segments: pd.DataFrame
    metrics: pd.DataFrame


def _rank_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    groups = []
    for _, group in frame.groupby("source_set", sort=False):
        group = group.copy()
        descending_rank = group["predicted_probability"].rank(method="first", ascending=False)
        group["prediction_decile"] = np.ceil(descending_rank / len(group) * 10).clip(1, 10).astype("int8")
        group["prediction_percentile"] = (
            group["predicted_probability"].rank(method="average", pct=True) * 100
        )
        groups.append(group)
    return pd.concat(groups, ignore_index=True)


def _prepare_features(root: Path) -> pd.DataFrame:
    train = pd.read_csv(root / "data/raw/train.csv").rename(columns=FEATURE_RENAME)
    test = pd.read_csv(root / "data/raw/test.csv").rename(columns=FEATURE_RENAME)
    train.insert(1, "source_set", "train")
    test.insert(1, "source_set", "test")
    test["will_buy_ev"] = None
    columns = ["id", "source_set", *FEATURE_RENAME.values()]
    return pd.concat([train[columns], test[columns]], ignore_index=True)


def _prepare_predictions(root: Path) -> pd.DataFrame:
    train = pd.read_csv(root / "data/processed/advanced_blend_oof_predictions.csv").rename(
        columns={"actual": "actual_target", "oof_prediction": "predicted_probability"}
    )
    test = pd.read_csv(root / "data/processed/advanced_blend_test_predictions.csv").rename(
        columns={"prediction": "predicted_probability"}
    )
    train["source_set"] = "train"
    test["source_set"] = "test"
    test["actual_target"] = np.nan
    predictions = pd.concat([train, test], ignore_index=True)
    predictions["model_name"] = "Advanced + Base Blend"
    predictions["model_version"] = "final_oof_blend_v1"
    return _rank_predictions(
        predictions[
            ["id", "source_set", "actual_target", "predicted_probability", "model_name", "model_version"]
        ]
    )


def _prepare_segments(root: Path) -> pd.DataFrame:
    train = pd.read_csv(
        root / "outputs/dashboard/customer_overview.csv",
        usecols=["id", "predicted_probability", "customer_segment"],
    )
    test = pd.read_csv(
        root / "outputs/dashboard/purchase_propensity.csv",
        usecols=["id", "predicted_probability", "customer_segment"],
    )
    train["source_set"] = "train"
    test["source_set"] = "test"
    segments = pd.concat([train, test], ignore_index=True).rename(
        columns={"predicted_probability": "segmentation_score"}
    )
    segments["high_potential_flag"] = segments["customer_segment"].eq("High Potential")
    segments["segment_method"] = "Existing multiseed XGBoost rule segmentation"
    return segments[
        ["id", "source_set", "customer_segment", "segmentation_score", "high_potential_flag", "segment_method"]
    ]


def _record(rows: list[dict], **values: object) -> None:
    rows.append(values)


def _prepare_metrics(root: Path) -> pd.DataFrame:
    table_dir = root / "outputs/tables"
    rows: list[dict] = []
    comparison = pd.read_csv(table_dir / "model_comparison.csv")
    for row in comparison.to_dict("records"):
        _record(
            rows,
            experiment_group="model_comparison",
            model_name=row["model"],
            model_version="BASE",
            validation_type="5-fold stratified CV summary",
            seed=42,
            fold=None,
            roc_auc=row["mean_roc_auc"],
            accuracy=row["mean_accuracy"],
            precision_score=row["mean_precision"],
            recall_score=row["mean_recall"],
            f1_score=row["mean_f1"],
            log_loss=row["mean_log_loss"],
            std_roc_auc=row["std_roc_auc"],
            fit_seconds=row["fit_seconds"],
            predict_seconds=row["predict_seconds"],
            parameters=None,
        )
    for path in sorted(table_dir.glob("folds_*.csv")):
        for row in pd.read_csv(path).to_dict("records"):
            _record(
                rows,
                experiment_group="model_folds",
                model_name=row["model"],
                model_version="BASE",
                validation_type="5-fold stratified CV fold",
                seed=42,
                fold=row["fold"],
                roc_auc=row["roc_auc"],
                accuracy=row["accuracy"],
                precision_score=row["precision"],
                recall_score=row["recall"],
                f1_score=row["f1"],
                log_loss=row["log_loss"],
                std_roc_auc=None,
                fit_seconds=row["fit_seconds"],
                predict_seconds=row["predict_seconds"],
                parameters=None,
            )
    for row in pd.read_csv(table_dir / "ensemble_results.csv").to_dict("records"):
        _record(
            rows,
            experiment_group="ensemble",
            model_name=row["method"],
            model_version="final_candidate",
            validation_type="OOF ensemble comparison",
            seed=42,
            fold=None,
            roc_auc=row["oof_auc"],
            accuracy=None,
            precision_score=None,
            recall_score=None,
            f1_score=None,
            log_loss=None,
            std_roc_auc=None,
            fit_seconds=None,
            predict_seconds=None,
            parameters=json.dumps({"weights_or_method": row["weights"]}, ensure_ascii=True),
        )
    for row in pd.read_csv(table_dir / "multiseed_validation.csv").to_dict("records"):
        _record(
            rows,
            experiment_group="stability",
            model_name=row["model"],
            model_version="BASE_multiseed",
            validation_type="5-fold seed summary",
            seed=row["seed"],
            fold=None,
            roc_auc=row["mean_auc"],
            accuracy=None,
            precision_score=None,
            recall_score=None,
            f1_score=None,
            log_loss=None,
            std_roc_auc=row["std_auc"],
            fit_seconds=None,
            predict_seconds=None,
            parameters=json.dumps({"min_auc": row["min_auc"], "max_auc": row["max_auc"]}),
        )
    for row in pd.read_csv(table_dir / "feature_ablation.csv").to_dict("records"):
        _record(
            rows,
            experiment_group="feature_ablation",
            model_name="XGBoost",
            model_version=row["feature_version"],
            validation_type="5-fold feature ablation summary",
            seed=42,
            fold=None,
            roc_auc=row["mean_roc_auc"],
            accuracy=row["mean_accuracy"],
            precision_score=row["mean_precision"],
            recall_score=row["mean_recall"],
            f1_score=row["mean_f1"],
            log_loss=row["mean_log_loss"],
            std_roc_auc=row["std_roc_auc"],
            fit_seconds=row["fit_seconds"],
            predict_seconds=row["predict_seconds"],
            parameters=json.dumps({"feature_count": int(row["feature_count"])}),
        )
    advanced = pd.read_csv(table_dir / "advanced_model_folds.csv")
    for row in advanced.to_dict("records"):
        _record(
            rows,
            experiment_group="advanced_model_folds",
            model_name="Advanced XGBoost",
            model_version="digit_frequency_fold_safe_te",
            validation_type="5-fold stratified CV fold",
            seed=42,
            fold=row["fold"],
            roc_auc=row["roc_auc"],
            accuracy=None,
            precision_score=None,
            recall_score=None,
            f1_score=None,
            log_loss=None,
            std_roc_auc=None,
            fit_seconds=row["fit_seconds"],
            predict_seconds=None,
            parameters=json.dumps({"best_iteration": int(row["best_iteration"])}),
        )
    return pd.DataFrame(rows)


def prepare_tables(root: Path) -> PreparedTables:
    return PreparedTables(
        features=_prepare_features(root),
        predictions=_prepare_predictions(root),
        segments=_prepare_segments(root),
        metrics=_prepare_metrics(root),
    )


TABLE_DTYPES = {
    "ev_customer_features": {
        "id": BigInteger(), "source_set": String(8), "age": Integer(), "annual_income_usd": Float(),
        "daily_commute_km": Float(), "number_of_cars_owned": Integer(),
        "charging_stations_near_home": Integer(), "charging_stations_near_work": Integer(),
        "environmental_concern_level": Float(), "gender": String(16), "city_type": String(16),
        "current_car_type": String(24), "home_charging_possible": String(3),
        "subsidy_available": String(3), "range_anxiety_level": String(12), "will_buy_ev": String(3),
    },
    "ev_model_predictions": {
        "id": BigInteger(), "source_set": String(8), "actual_target": Float(),
        "predicted_probability": Float(), "model_name": String(80), "model_version": String(80),
        "prediction_decile": Integer(), "prediction_percentile": Float(),
    },
    "ev_customer_segments": {
        "id": BigInteger(), "source_set": String(8), "customer_segment": String(48),
        "segmentation_score": Float(), "high_potential_flag": Boolean(), "segment_method": String(120),
    },
    "ev_model_metrics": {
        "experiment_group": String(48), "model_name": String(80), "model_version": String(80),
        "validation_type": String(80), "seed": Integer(), "fold": Integer(), "roc_auc": Float(),
        "accuracy": Float(), "precision_score": Float(), "recall_score": Float(), "f1_score": Float(),
        "log_loss": Float(), "std_roc_auc": Float(), "fit_seconds": Float(), "predict_seconds": Float(),
        "parameters": Text(),
    },
}


def _load_frame(engine: Engine, table: str, frame: pd.DataFrame, chunk_size: int) -> tuple[int, int, float]:
    attempts = 0
    current_chunk = chunk_size
    started = time.perf_counter()
    while True:
        attempts += 1
        try:
            frame.to_sql(
                table,
                engine,
                if_exists="append",
                index=False,
                chunksize=current_chunk,
                dtype=TABLE_DTYPES[table],
                method=None,
            )
            return attempts, current_chunk, time.perf_counter() - started
        except DBAPIError:
            if attempts >= 3 or current_chunk <= 500:
                raise
            current_chunk = max(500, current_chunk // 2)


def load_tables(engine: Engine, tables: PreparedTables, output_dir: Path, chunk_size: int = 5_000) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    table_frames = [
        ("ev_customer_features", tables.features),
        ("ev_model_predictions", tables.predictions),
        ("ev_customer_segments", tables.segments),
        ("ev_model_metrics", tables.metrics),
    ]
    with engine.begin() as connection:
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        for table, _ in reversed(table_frames):
            connection.exec_driver_sql(f"TRUNCATE TABLE `{table}`")
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
    log_rows = []
    for table, frame in table_frames:
        attempts, used_chunk, elapsed = _load_frame(engine, table, frame, chunk_size)
        log_rows.append(
            {
                "table": table,
                "rows_loaded": len(frame),
                "columns_loaded": len(frame.columns),
                "chunk_size": used_chunk,
                "attempts": attempts,
                "elapsed_seconds": round(elapsed, 3),
                "status": "PASS",
            }
        )
    log = pd.DataFrame(log_rows)
    log.to_csv(output_dir / "mysql_load_log.csv", index=False)
    return log
