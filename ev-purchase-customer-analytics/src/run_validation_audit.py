from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from config import CV_SPLITS, ID_COLUMN, PROCESSED_DIR, RANDOM_STATE, TABLE_DIR, TARGET, VALIDATION_SEEDS, MODEL_DIR
from data import audit_data, load_data
from evaluation import cv_predict_pipeline
from features import add_features
from models import build_sklearn_model


def main() -> None:
    train, test, _ = load_data()
    audit_data(train, test)
    y = train[TARGET].eq("Yes").astype(int)
    version = str(pd.read_csv(TABLE_DIR / "feature_ablation.csv").sort_values("mean_roc_auc", ascending=False).iloc[0].feature_version)
    x = add_features(train, version)
    ensemble = pd.read_csv(TABLE_DIR / "ensemble_results.csv")
    params = json.loads((MODEL_DIR / "best_params.json").read_text(encoding="utf-8"))
    candidates = [name for name in params if name in set(ensemble.method)]
    name = str(ensemble[ensemble.method.isin(candidates)].sort_values("oof_auc", ascending=False).iloc[0].method)
    rows, oof_predictions, test_predictions = [], [], []
    for seed in VALIDATION_SEEDS:
        if seed == RANDOM_STATE:
            models = joblib.load(MODEL_DIR / f"{name.lower()}_fold_models.joblib")
            splitter = StratifiedKFold(n_splits=CV_SPLITS, shuffle=True, random_state=seed)
            oof, test_pred = np.zeros(len(train)), np.zeros(len(test))
            fold_rows = []
            for model, (_, valid_idx) in zip(models, splitter.split(x, y)):
                pred = model.predict_proba(x.iloc[valid_idx])[:, 1]
                oof[valid_idx] = pred
                test_pred += model.predict_proba(add_features(test, version))[:, 1] / CV_SPLITS
                fold_rows.append(roc_auc_score(y.iloc[valid_idx], pred))
            folds = pd.DataFrame({"roc_auc": fold_rows})
        else:
            model = build_sklearn_model(name, x, seed, params[name])
            _, folds, oof, test_pred, _ = cv_predict_pipeline(model, x, y, add_features(test, version), folds=CV_SPLITS, seed=seed)
        oof_predictions.append(oof)
        test_predictions.append(test_pred)
        rows.append({"model": name, "seed": seed, "mean_auc": folds.roc_auc.mean(), "std_auc": folds.roc_auc.std(ddof=1), "min_auc": folds.roc_auc.min(), "max_auc": folds.roc_auc.max()})
        print(f"{name} seed {seed}: {folds.roc_auc.mean():.6f}", flush=True)
    pd.DataFrame(rows).to_csv(TABLE_DIR / "multiseed_validation.csv", index=False)
    mean_oof = np.mean(oof_predictions, axis=0)
    mean_test = np.mean(test_predictions, axis=0)
    bagging_auc = roc_auc_score(y, mean_oof)
    pd.DataFrame({ID_COLUMN: train[ID_COLUMN], "actual": y, "oof_prediction": mean_oof}).to_csv(PROCESSED_DIR / "multiseed_oof_predictions.csv", index=False)
    pd.DataFrame({ID_COLUMN: test[ID_COLUMN], "prediction": mean_test}).to_csv(PROCESSED_DIR / "multiseed_test_predictions.csv", index=False)
    ensemble = ensemble[ensemble.method.ne("Multi-seed XGBoost Bagging")]
    ensemble.loc[len(ensemble)] = {"method": "Multi-seed XGBoost Bagging", "oof_auc": bagging_auc, "weights": f"equal seeds {list(VALIDATION_SEEDS)}"}
    ensemble.sort_values("oof_auc", ascending=False).to_csv(TABLE_DIR / "ensemble_results.csv", index=False)
    print(f"Multi-seed bagging OOF AUC: {bagging_auc:.6f}", flush=True)


if __name__ == "__main__":
    main()
