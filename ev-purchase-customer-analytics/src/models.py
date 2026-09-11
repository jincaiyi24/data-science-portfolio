from __future__ import annotations

from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier


def make_preprocessor(x, scale_numeric: bool = False) -> ColumnTransformer:
    categorical = x.select_dtypes(include=["object", "category"]).columns.tolist()
    numerical = x.columns.difference(categorical, sort=False).tolist()
    numeric_steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale_numeric:
        numeric_steps.append(("scaler", StandardScaler()))
    return ColumnTransformer(
        [
            ("num", Pipeline(numeric_steps), numerical),
            (
                "cat",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=True)),
                    ]
                ),
                categorical,
            ),
        ]
    )


def build_sklearn_model(name: str, x, seed: int = 42, params: dict | None = None) -> Pipeline:
    params = params or {}
    if name == "Dummy":
        estimator = DummyClassifier(strategy="prior")
        scale = False
    elif name == "Logistic Regression":
        estimator = LogisticRegression(C=1.0, max_iter=500, class_weight="balanced", random_state=seed, n_jobs=-1)
        scale = True
    elif name == "Random Forest":
        estimator = RandomForestClassifier(
            n_estimators=50,
            max_depth=12,
            min_samples_leaf=8,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=seed,
        )
        scale = False
    elif name == "XGBoost":
        defaults = dict(
            n_estimators=700,
            learning_rate=0.05,
            max_depth=7,
            min_child_weight=6,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.05,
            reg_lambda=2.0,
            objective="binary:logistic",
            eval_metric="auc",
            tree_method="hist",
            n_jobs=-1,
            random_state=seed,
        )
        defaults.update(params)
        estimator = XGBClassifier(**defaults)
        scale = False
    elif name == "LightGBM":
        defaults = dict(
            n_estimators=750,
            learning_rate=0.04,
            num_leaves=31,
            max_depth=-1,
            min_child_samples=35,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_alpha=0.05,
            reg_lambda=1.0,
            objective="binary",
            verbosity=-1,
            n_jobs=-1,
            random_state=seed,
        )
        defaults.update(params)
        estimator = LGBMClassifier(**defaults)
        scale = False
    else:
        raise ValueError(f"Unknown sklearn model: {name}")
    return Pipeline([("preprocessor", make_preprocessor(x, scale)), ("model", estimator)])


def build_catboost(seed: int = 42, params: dict | None = None) -> CatBoostClassifier:
    defaults = dict(
        iterations=300,
        depth=7,
        learning_rate=0.07,
        l2_leaf_reg=5.0,
        loss_function="Logloss",
        eval_metric="AUC",
        random_seed=seed,
        verbose=False,
        thread_count=-1,
        allow_writing_files=False,
    )
    defaults.update(params or {})
    return CatBoostClassifier(**defaults)
