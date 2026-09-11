from __future__ import annotations

import gc
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import TargetEncoder
from xgboost import XGBClassifier

from config import ID_COLUMN, MODEL_DIR, PROCESSED_DIR, RANDOM_STATE, TABLE_DIR, TARGET
from data import load_data
from features import BASE_FEATURES


NUMERIC = [
    "Age",
    "Annual_Income_USD",
    "Daily_Commute_km",
    "Number_of_Cars_Owned",
    "Charging_Stations_Near_Home",
    "Charging_Stations_Near_Work",
    "Environmental_Concern_Level",
]


def competition_features(train: pd.DataFrame, test: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    combined = pd.concat([train[BASE_FEATURES], test[BASE_FEATURES]], ignore_index=True)
    output = pd.DataFrame(index=combined.index)
    for col in BASE_FEATURES:
        if combined[col].dtype == "object":
            categories = sorted(combined[col].astype(str).unique())
            output[col] = combined[col].astype(str).map({value: idx for idx, value in enumerate(categories)}).astype("int8")
        else:
            output[col] = combined[col].astype("float32")

    subsidy = combined["Subsidy_Available"].eq("Yes").astype("int8")
    home = combined["Home_Charging_Possible"].eq("Yes").astype("int8")
    anxiety = combined["Range_Anxiety_Level"].map({"Low": 0, "Medium": 1, "High": 2}).astype("int8")
    output["Eco_x_Subsidy"] = (combined["Environmental_Concern_Level"] * subsidy).astype("float32")
    output["Eco_x_Income"] = (combined["Environmental_Concern_Level"] * combined["Annual_Income_USD"] / 100_000).astype("float32")
    output["Income_x_Subsidy"] = (combined["Annual_Income_USD"] * subsidy / 100_000).astype("float32")
    output["Anxiety_x_Subsidy"] = (anxiety * subsidy).astype("int8")
    output["Home_x_Subsidy"] = (home * subsidy).astype("int8")

    digit_columns = []
    for col in NUMERIC:
        values = combined[col].fillna(0).to_numpy()
        for exponent in (-1, 0, 1, 2, 3, 4, 5):
            name = f"{col}_digit_{exponent}"
            output[name] = (np.floor(values / (10.0**exponent)).astype("int64") % 10).astype("int8")
            digit_columns.append(name)

    for col in BASE_FEATURES + digit_columns:
        output[f"freq_{col}"] = output[col].map(output[col].value_counts(normalize=True)).astype("float32")

    output = output.loc[:, output.nunique(dropna=False).gt(1)]
    return output.iloc[: len(train)].reset_index(drop=True), output.iloc[len(train) :].reset_index(drop=True)


def cross_fitted_target_features(
    raw_train: pd.DataFrame,
    raw_valid: pd.DataFrame,
    raw_test: pd.DataFrame,
    y_train: pd.Series,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    train_parts, valid_parts, test_parts = [], [], []
    for smooth in ("auto", 20.0, 100.0):
        encoder = TargetEncoder(target_type="binary", smooth=smooth, cv=5, shuffle=True, random_state=seed)
        train_parts.append(encoder.fit_transform(raw_train, y_train).astype("float32"))
        valid_parts.append(encoder.transform(raw_valid).astype("float32"))
        test_parts.append(encoder.transform(raw_test).astype("float32"))
    return np.hstack(train_parts), np.hstack(valid_parts), np.hstack(test_parts)


def run() -> None:
    train, test, _ = load_data()
    y = train[TARGET].eq("Yes").astype(int)
    x, xt = competition_features(train, test)
    raw_train = train[BASE_FEATURES].copy()
    raw_test = test[BASE_FEATURES].copy()
    for frame in (raw_train, raw_test):
        for col in frame.select_dtypes(include="object"):
            frame[col] = frame[col].fillna("Missing")
        for col in frame.select_dtypes(exclude="object"):
            frame[col] = frame[col].fillna(raw_train[col].median())

    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    oof, test_pred = np.zeros(len(train)), np.zeros(len(test))
    fold_rows, importance = [], np.zeros(x.shape[1] + 3 * len(BASE_FEATURES))
    params = {
        "n_estimators": 3500,
        "learning_rate": 0.01,
        "max_depth": 7,
        "min_child_weight": 10,
        "subsample": 0.90,
        "colsample_bytree": 0.88,
        "reg_alpha": 0.05,
        "reg_lambda": 2.0,
        "max_bin": 512,
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "tree_method": "hist",
        "device": "cuda",
        "early_stopping_rounds": 250,
        "random_state": RANDOM_STATE,
    }
    for fold, (train_idx, valid_idx) in enumerate(splitter.split(x, y), 1):
        started = time.perf_counter()
        train_te, valid_te, test_te = cross_fitted_target_features(
            raw_train.iloc[train_idx], raw_train.iloc[valid_idx], raw_test, y.iloc[train_idx], RANDOM_STATE + fold
        )
        x_train = np.hstack([x.iloc[train_idx].to_numpy(dtype="float32"), train_te])
        x_valid = np.hstack([x.iloc[valid_idx].to_numpy(dtype="float32"), valid_te])
        x_test = np.hstack([xt.to_numpy(dtype="float32"), test_te])
        model = XGBClassifier(**params)
        model.fit(x_train, y.iloc[train_idx], eval_set=[(x_valid, y.iloc[valid_idx])], verbose=False)
        pred = model.predict_proba(x_valid)[:, 1]
        oof[valid_idx] = pred
        test_pred += model.predict_proba(x_test)[:, 1] / 5
        auc = roc_auc_score(y.iloc[valid_idx], pred)
        fold_rows.append({"fold": fold, "roc_auc": auc, "best_iteration": model.best_iteration, "fit_seconds": time.perf_counter() - started})
        importance += model.feature_importances_ / 5
        model.save_model(MODEL_DIR / f"advanced_xgboost_fold_{fold}.json")
        print(f"Advanced fold {fold}: AUC={auc:.6f}, best_iteration={model.best_iteration}", flush=True)
        del train_te, valid_te, test_te, x_train, x_valid, x_test, model
        gc.collect()

    feature_names = x.columns.tolist() + [f"te_{smooth}_{col}" for smooth in ("auto", "20", "100") for col in BASE_FEATURES]
    pd.DataFrame({"feature": feature_names, "importance": importance}).sort_values("importance", ascending=False).to_csv(TABLE_DIR / "advanced_feature_importance.csv", index=False)
    folds = pd.DataFrame(fold_rows)
    folds.to_csv(TABLE_DIR / "advanced_model_folds.csv", index=False)
    auc = roc_auc_score(y, oof)
    pd.DataFrame({ID_COLUMN: train[ID_COLUMN], "actual": y, "oof_prediction": oof}).to_csv(PROCESSED_DIR / "advanced_oof_predictions.csv", index=False)
    pd.DataFrame({ID_COLUMN: test[ID_COLUMN], "prediction": test_pred}).to_csv(PROCESSED_DIR / "advanced_test_predictions.csv", index=False)
    (MODEL_DIR / "advanced_xgboost_params.json").write_text(json.dumps(params, indent=2), encoding="utf-8")

    ensemble = pd.read_csv(TABLE_DIR / "ensemble_results.csv")
    ensemble = ensemble[~ensemble.method.str.startswith("Advanced")]
    ensemble.loc[len(ensemble)] = {"method": "Advanced XGBoost", "oof_auc": auc, "weights": "digit + frequency + fold-safe target encoding"}
    base_oof = pd.read_csv(PROCESSED_DIR / "multiseed_oof_predictions.csv")["oof_prediction"].to_numpy()
    base_test = pd.read_csv(PROCESSED_DIR / "multiseed_test_predictions.csv")["prediction"].to_numpy()
    weights = np.linspace(0, 1, 41)
    blend_scores = [roc_auc_score(y, weight * oof + (1 - weight) * base_oof) for weight in weights]
    weight = float(weights[int(np.argmax(blend_scores))])
    blend_oof = weight * oof + (1 - weight) * base_oof
    blend_test = weight * test_pred + (1 - weight) * base_test
    pd.DataFrame({ID_COLUMN: train[ID_COLUMN], "actual": y, "oof_prediction": blend_oof}).to_csv(PROCESSED_DIR / "advanced_blend_oof_predictions.csv", index=False)
    pd.DataFrame({ID_COLUMN: test[ID_COLUMN], "prediction": blend_test}).to_csv(PROCESSED_DIR / "advanced_blend_test_predictions.csv", index=False)
    ensemble.loc[len(ensemble)] = {
        "method": "Advanced + Base Blend",
        "oof_auc": roc_auc_score(y, blend_oof),
        "weights": f"advanced={weight:.3f}; base={1-weight:.3f}",
    }
    ensemble.sort_values("oof_auc", ascending=False).to_csv(TABLE_DIR / "ensemble_results.csv", index=False)
    print(f"Advanced OOF AUC={auc:.6f}; best blend AUC={roc_auc_score(y, blend_oof):.6f}; advanced weight={weight:.3f}", flush=True)


if __name__ == "__main__":
    run()
