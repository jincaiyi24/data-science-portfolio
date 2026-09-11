from __future__ import annotations

import time

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.metrics import accuracy_score, f1_score, log_loss, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from models import build_catboost


def binary_metrics(y_true, prediction: np.ndarray) -> dict[str, float]:
    label = (prediction >= 0.5).astype(int)
    return {
        "roc_auc": roc_auc_score(y_true, prediction),
        "accuracy": accuracy_score(y_true, label),
        "precision": precision_score(y_true, label, zero_division=0),
        "recall": recall_score(y_true, label, zero_division=0),
        "f1": f1_score(y_true, label, zero_division=0),
        "log_loss": log_loss(y_true, prediction),
    }


def evaluate_pipeline(model, x: pd.DataFrame, y: pd.Series, folds: int = 5, seed: int = 42, return_oof: bool = False):
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    oof = np.zeros(len(x))
    rows = []
    for fold, (train_idx, valid_idx) in enumerate(splitter.split(x, y), 1):
        fitted = clone(model)
        start = time.perf_counter()
        fitted.fit(x.iloc[train_idx], y.iloc[train_idx])
        fit_seconds = time.perf_counter() - start
        start = time.perf_counter()
        pred = fitted.predict_proba(x.iloc[valid_idx])[:, 1]
        predict_seconds = time.perf_counter() - start
        oof[valid_idx] = pred
        rows.append({"fold": fold, **binary_metrics(y.iloc[valid_idx], pred), "fit_seconds": fit_seconds, "predict_seconds": predict_seconds})
    detail = pd.DataFrame(rows)
    summary = {f"mean_{c}": detail[c].mean() for c in ["roc_auc", "accuracy", "precision", "recall", "f1", "log_loss"]}
    summary.update({"std_roc_auc": detail["roc_auc"].std(ddof=1), "fit_seconds": detail["fit_seconds"].sum(), "predict_seconds": detail["predict_seconds"].sum()})
    return (summary, detail, oof) if return_oof else (summary, detail)


def cv_predict_pipeline(model, x: pd.DataFrame, y: pd.Series, test: pd.DataFrame, folds: int = 5, seed: int = 42):
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    oof = np.zeros(len(x))
    test_pred = np.zeros(len(test))
    rows, models = [], []
    for fold, (train_idx, valid_idx) in enumerate(splitter.split(x, y), 1):
        fitted = clone(model)
        start = time.perf_counter()
        fitted.fit(x.iloc[train_idx], y.iloc[train_idx])
        fit_seconds = time.perf_counter() - start
        start = time.perf_counter()
        pred = fitted.predict_proba(x.iloc[valid_idx])[:, 1]
        test_pred += fitted.predict_proba(test)[:, 1] / folds
        predict_seconds = time.perf_counter() - start
        oof[valid_idx] = pred
        rows.append({"fold": fold, **binary_metrics(y.iloc[valid_idx], pred), "fit_seconds": fit_seconds, "predict_seconds": predict_seconds})
        models.append(fitted)
    detail = pd.DataFrame(rows)
    summary = {f"mean_{c}": detail[c].mean() for c in ["roc_auc", "accuracy", "precision", "recall", "f1", "log_loss"]}
    summary.update({"std_roc_auc": detail["roc_auc"].std(ddof=1), "fit_seconds": detail["fit_seconds"].sum(), "predict_seconds": detail["predict_seconds"].sum()})
    return summary, detail, oof, test_pred, models


def evaluate_catboost(
    x: pd.DataFrame,
    y: pd.Series,
    folds: int = 5,
    seed: int = 42,
    params: dict | None = None,
    return_oof: bool = False,
    test: pd.DataFrame | None = None,
):
    categorical = x.select_dtypes(include=["object", "category"]).columns.tolist()
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    oof = np.zeros(len(x))
    test_pred = np.zeros(len(test)) if test is not None else None
    rows = []
    models = []
    for fold, (train_idx, valid_idx) in enumerate(splitter.split(x, y), 1):
        model = build_catboost(seed + fold, params)
        start = time.perf_counter()
        model.fit(
            x.iloc[train_idx],
            y.iloc[train_idx],
            cat_features=categorical,
            eval_set=(x.iloc[valid_idx], y.iloc[valid_idx]),
            early_stopping_rounds=80,
            verbose=False,
        )
        fit_seconds = time.perf_counter() - start
        start = time.perf_counter()
        pred = model.predict_proba(x.iloc[valid_idx])[:, 1]
        predict_seconds = time.perf_counter() - start
        oof[valid_idx] = pred
        if test is not None:
            test_pred += model.predict_proba(test)[:, 1] / folds
        rows.append({"fold": fold, **binary_metrics(y.iloc[valid_idx], pred), "fit_seconds": fit_seconds, "predict_seconds": predict_seconds})
        models.append(model)
    detail = pd.DataFrame(rows)
    summary = {f"mean_{c}": detail[c].mean() for c in ["roc_auc", "accuracy", "precision", "recall", "f1", "log_loss"]}
    summary.update({"std_roc_auc": detail["roc_auc"].std(ddof=1), "fit_seconds": detail["fit_seconds"].sum(), "predict_seconds": detail["predict_seconds"].sum()})
    if return_oof:
        return summary, detail, oof, test_pred, models
    return summary, detail
