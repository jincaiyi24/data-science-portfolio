from __future__ import annotations

import json
import random
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import skew
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, RobustScaler

SEED = 42
TARGET = "SalePrice"
ID_COLUMN = "Id"
OUTLIER_RULE = "GrLivArea > 4000 and SalePrice < 300000"


def seed_everything(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)


def read_competition_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    read_options = {
        "keep_default_na": False,
        "na_values": ["NA", ""],
    }
    train = pd.read_csv(data_dir / "train.csv", **read_options)
    test = pd.read_csv(data_dir / "test.csv", **read_options)
    validate_raw_data(train, test)
    return train, test


def validate_raw_data(train: pd.DataFrame, test: pd.DataFrame) -> None:
    assert train.shape == (1460, 81), f"Unexpected train shape: {train.shape}"
    assert test.shape == (1459, 80), f"Unexpected test shape: {test.shape}"
    assert train[ID_COLUMN].is_unique and test[ID_COLUMN].is_unique
    assert train[TARGET].notna().all()
    assert TARGET not in test
    assert list(train.drop(columns=TARGET)) == list(test)
    assert set(train[ID_COLUMN]).isdisjoint(set(test[ID_COLUMN]))


def clean_structural_missing(dataframe: pd.DataFrame) -> pd.DataFrame:
    data = dataframe.copy()

    for column in ["Alley", "Fence", "MiscFeature"]:
        data[column] = data[column].fillna("None")

    basement_categories = [
        "BsmtQual",
        "BsmtCond",
        "BsmtExposure",
        "BsmtFinType1",
        "BsmtFinType2",
    ]
    basement_numbers = [
        "BsmtFinSF1",
        "BsmtFinSF2",
        "BsmtUnfSF",
        "TotalBsmtSF",
        "BsmtFullBath",
        "BsmtHalfBath",
    ]
    has_basement = data[basement_categories].notna().any(axis=1) | data[
        basement_numbers
    ].fillna(0).gt(0).any(axis=1)
    _fill_facility_columns(
        data,
        has_basement,
        basement_categories,
        basement_numbers,
    )

    garage_categories = [
        "GarageType",
        "GarageFinish",
        "GarageQual",
        "GarageCond",
    ]
    garage_numbers = ["GarageYrBlt", "GarageCars", "GarageArea"]
    has_garage = data[garage_categories].notna().any(axis=1) | data[
        ["GarageCars", "GarageArea"]
    ].fillna(0).gt(0).any(axis=1)
    _fill_facility_columns(
        data,
        has_garage,
        garage_categories,
        garage_numbers,
    )

    has_fireplace = data["Fireplaces"].fillna(0).gt(0)
    data.loc[~has_fireplace, "FireplaceQu"] = "None"
    data.loc[has_fireplace, "FireplaceQu"] = data.loc[
        has_fireplace, "FireplaceQu"
    ].fillna("Missing")

    has_pool = data["PoolArea"].fillna(0).gt(0)
    data.loc[~has_pool, "PoolQC"] = "None"
    data.loc[has_pool, "PoolQC"] = data.loc[has_pool, "PoolQC"].fillna("Missing")

    no_masonry = data["MasVnrArea"].fillna(0).eq(0)
    data.loc[no_masonry, "MasVnrType"] = data.loc[no_masonry, "MasVnrType"].fillna(
        "None"
    )
    data.loc[no_masonry, "MasVnrArea"] = data.loc[no_masonry, "MasVnrArea"].fillna(0)
    data.loc[~no_masonry, "MasVnrType"] = data.loc[~no_masonry, "MasVnrType"].fillna(
        "Missing"
    )

    invalid_garage_year = data["GarageYrBlt"].gt(data["YrSold"]) & data[
        "GarageYrBlt"
    ].gt(0)
    data.loc[invalid_garage_year, "GarageYrBlt"] = np.nan

    invalid_remodel_year = data["YearRemodAdd"].gt(data["YrSold"])
    data.loc[invalid_remodel_year, "YearRemodAdd"] = data.loc[
        invalid_remodel_year, "YrSold"
    ]

    return data


def _fill_facility_columns(
    data: pd.DataFrame,
    has_facility: pd.Series,
    category_columns: list[str],
    numeric_columns: list[str],
) -> None:
    for column in category_columns:
        data.loc[~has_facility, column] = "None"
        data.loc[has_facility, column] = data.loc[has_facility, column].fillna(
            "Missing"
        )

    for column in numeric_columns:
        data.loc[~has_facility, column] = 0


def remove_training_outliers(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    outlier_mask = train["GrLivArea"].gt(4000) & train[TARGET].lt(300000)
    outliers = train.loc[
        outlier_mask,
        [ID_COLUMN, "GrLivArea", "OverallQual", TARGET],
    ].copy()
    clean_train = train.loc[~outlier_mask].reset_index(drop=True)
    assert outliers[ID_COLUMN].tolist() == [524, 1299]
    assert len(clean_train) == 1458
    return clean_train, outliers


FEATURE_GROUPS = (
    "totals",
    "ages",
    "flags",
    "interactions",
    "cyclic",
    "ordinal",
    "nonlinear",
)

QUALITY_MAP = {
    "None": 0,
    "Missing": np.nan,
    "Po": 1,
    "Fa": 2,
    "TA": 3,
    "Gd": 4,
    "Ex": 5,
}
ORDINAL_MAPS = {
    "ExterQual": QUALITY_MAP,
    "ExterCond": QUALITY_MAP,
    "BsmtQual": QUALITY_MAP,
    "BsmtCond": QUALITY_MAP,
    "HeatingQC": QUALITY_MAP,
    "KitchenQual": QUALITY_MAP,
    "FireplaceQu": QUALITY_MAP,
    "GarageQual": QUALITY_MAP,
    "GarageCond": QUALITY_MAP,
    "PoolQC": QUALITY_MAP,
    "BsmtExposure": {
        "None": 0,
        "Missing": np.nan,
        "No": 1,
        "Mn": 2,
        "Av": 3,
        "Gd": 4,
    },
    "BsmtFinType1": {
        "None": 0,
        "Missing": np.nan,
        "Unf": 1,
        "LwQ": 2,
        "Rec": 3,
        "BLQ": 4,
        "ALQ": 5,
        "GLQ": 6,
    },
    "BsmtFinType2": {
        "None": 0,
        "Missing": np.nan,
        "Unf": 1,
        "LwQ": 2,
        "Rec": 3,
        "BLQ": 4,
        "ALQ": 5,
        "GLQ": 6,
    },
    "GarageFinish": {
        "None": 0,
        "Missing": np.nan,
        "Unf": 1,
        "RFn": 2,
        "Fin": 3,
    },
    "Functional": {
        "Sal": 0,
        "Sev": 1,
        "Maj2": 2,
        "Maj1": 3,
        "Mod": 4,
        "Min2": 5,
        "Min1": 6,
        "Typ": 7,
    },
    "LotShape": {"IR3": 0, "IR2": 1, "IR1": 2, "Reg": 3},
    "LandSlope": {"Sev": 0, "Mod": 1, "Gtl": 2},
    "PavedDrive": {"N": 0, "P": 1, "Y": 2},
}


def make_features(
    dataframe: pd.DataFrame,
    groups: Iterable[str] = (),
) -> pd.DataFrame:
    data = dataframe.copy()
    groups = set(groups)

    if "totals" in groups:
        data["TotalSF"] = data["TotalBsmtSF"] + data["1stFlrSF"] + data["2ndFlrSF"]
        data["TotalBathrooms"] = (
            data["FullBath"]
            + 0.5 * data["HalfBath"]
            + data["BsmtFullBath"]
            + 0.5 * data["BsmtHalfBath"]
        )
        data["TotalPorchSF"] = (
            data["OpenPorchSF"]
            + data["EnclosedPorch"]
            + data["3SsnPorch"]
            + data["ScreenPorch"]
            + data["WoodDeckSF"]
        )
        data["TotalOutdoorSF"] = data["TotalPorchSF"] + data["PoolArea"]

    if "ages" in groups:
        data["AgeAtSale"] = (data["YrSold"] - data["YearBuilt"]).clip(lower=0)
        data["YearsSinceRemodel"] = (data["YrSold"] - data["YearRemodAdd"]).clip(
            lower=0
        )
        data["GarageAgeAtSale"] = np.where(
            data["GarageYrBlt"].gt(0),
            (data["YrSold"] - data["GarageYrBlt"]).clip(lower=0),
            0,
        )

    if "flags" in groups:
        flag_sources = {
            "HasGarage": "GarageArea",
            "HasBasement": "TotalBsmtSF",
            "HasFireplace": "Fireplaces",
            "HasPool": "PoolArea",
            "HasSecondFloor": "2ndFlrSF",
            "HasMasonry": "MasVnrArea",
        }
        for new_column, source_column in flag_sources.items():
            data[new_column] = data[source_column].fillna(0).gt(0).astype("int8")

    if "interactions" in groups:
        total_sf = (
            data["TotalSF"]
            if "TotalSF" in data
            else data["TotalBsmtSF"] + data["1stFlrSF"] + data["2ndFlrSF"]
        )
        data["OverallQual_x_GrLivArea"] = data["OverallQual"] * data["GrLivArea"]
        data["OverallQual_x_TotalSF"] = data["OverallQual"] * total_sf
        data["GarageScore"] = data["GarageCars"] * data["GarageArea"]

    if "cyclic" in groups:
        data["MoSoldSin"] = np.sin(2 * np.pi * data["MoSold"] / 12)
        data["MoSoldCos"] = np.cos(2 * np.pi * data["MoSold"] / 12)

    if "ordinal" in groups:
        for column, mapping in ORDINAL_MAPS.items():
            data[f"{column}Score"] = data[column].map(mapping).astype(float)

    if "nonlinear" in groups:
        total_sf = (
            data["TotalSF"]
            if "TotalSF" in data
            else data["TotalBsmtSF"] + data["1stFlrSF"] + data["2ndFlrSF"]
        )
        data["OverallQualSquared"] = data["OverallQual"].astype(float) ** 2
        data["OverallCondSquared"] = data["OverallCond"].astype(float) ** 2
        data["QualPerLivingArea"] = data["OverallQual"] * np.log1p(
            data["GrLivArea"].clip(lower=0)
        )
        data["QualPerTotalSF"] = data["OverallQual"] * np.log1p(
            total_sf.clip(lower=0)
        )

    data["MSSubClass"] = data["MSSubClass"].astype(str)
    data["MoSold"] = data["MoSold"].astype(str)
    data["YrSoldCategory"] = data["YrSold"].astype(str)

    return data.drop(columns=[ID_COLUMN, TARGET], errors="ignore")


def prepare_catboost_features(
    dataframe: pd.DataFrame,
    groups: Iterable[str] = (),
) -> tuple[pd.DataFrame, list[str]]:
    data = make_features(dataframe, groups)
    category_columns = data.select_dtypes(exclude=np.number).columns.tolist()
    data[category_columns] = data[category_columns].fillna("Missing").astype(str)
    return data, category_columns


class SkewedLogTransformer(BaseEstimator, TransformerMixin):
    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def fit(self, X: Any, y: Any = None) -> SkewedLogTransformer:
        values = np.asarray(X, dtype=float)
        feature_skew = skew(values, axis=0, bias=False, nan_policy="omit")
        minimum = np.nanmin(values, axis=0)
        maximum = np.nanmax(values, axis=0)
        self.log_mask_ = (
            np.isfinite(feature_skew)
            & (feature_skew > self.threshold)
            & (minimum >= 0)
            & (maximum > 1)
        )
        return self

    def transform(self, X: Any) -> np.ndarray:
        values = np.asarray(X, dtype=float).copy()
        values[:, self.log_mask_] = np.log1p(values[:, self.log_mask_])
        return values


def build_preprocessor(
    features: pd.DataFrame,
    *,
    scale_numeric: bool,
    log_skewed: bool,
    dense: bool,
) -> ColumnTransformer:
    numeric_columns = features.select_dtypes(include=np.number).columns.tolist()
    category_columns = features.select_dtypes(exclude=np.number).columns.tolist()

    numeric_steps: list[tuple[str, Any]] = [
        ("imputer", SimpleImputer(strategy="median", add_indicator=True))
    ]
    if log_skewed:
        numeric_steps.append(("skew_log", SkewedLogTransformer()))
    if scale_numeric:
        numeric_steps.append(("scaler", RobustScaler()))

    category_pipeline = Pipeline(
        [
            (
                "imputer",
                SimpleImputer(strategy="constant", fill_value="Missing"),
            ),
            (
                "onehot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=not dense,
                ),
            ),
        ]
    )

    return ColumnTransformer(
        [
            ("numeric", Pipeline(numeric_steps), numeric_columns),
            ("categorical", category_pipeline, category_columns),
        ],
        sparse_threshold=0 if dense else 0.3,
    )


@dataclass
class OOFResult:
    name: str
    oof_prediction: np.ndarray
    test_prediction: np.ndarray | None
    fold_scores: list[float]
    fitted_models: list[Any]
    best_iterations: list[int]

    @property
    def rmse(self) -> float:
        return float(np.sqrt(np.mean(np.square(self.oof_prediction_error))))

    @property
    def oof_prediction_error(self) -> np.ndarray:
        if not hasattr(self, "_target"):
            raise AttributeError("Target was not attached to OOFResult")
        return self._target - self.oof_prediction

    def attach_target(self, target: np.ndarray) -> OOFResult:
        self._target = np.asarray(target)
        return self


def evaluate_sklearn_model(
    name: str,
    estimator: Any,
    X: pd.DataFrame,
    y: pd.Series,
    splits: list[tuple[np.ndarray, np.ndarray]],
    X_test: pd.DataFrame | None = None,
) -> OOFResult:
    oof = np.zeros(len(X), dtype=float)
    test_predictions: list[np.ndarray] = []
    fold_scores: list[float] = []
    fitted_models: list[Any] = []

    for train_index, valid_index in splits:
        model = clone(estimator)
        model.fit(X.iloc[train_index], y.iloc[train_index])
        valid_prediction = model.predict(X.iloc[valid_index])
        oof[valid_index] = valid_prediction
        fold_scores.append(rmse(y.iloc[valid_index], valid_prediction))
        fitted_models.append(model)

        if X_test is not None:
            test_predictions.append(model.predict(X_test))

    test_prediction = None
    if test_predictions:
        test_prediction = np.mean(test_predictions, axis=0)

    return OOFResult(
        name=name,
        oof_prediction=oof,
        test_prediction=test_prediction,
        fold_scores=fold_scores,
        fitted_models=fitted_models,
        best_iterations=[],
    ).attach_target(y.to_numpy())


def evaluate_catboost_model(
    name: str,
    parameters: dict[str, Any],
    X: pd.DataFrame,
    y: pd.Series,
    category_columns: list[str],
    splits: list[tuple[np.ndarray, np.ndarray]],
    X_test: pd.DataFrame | None = None,
) -> OOFResult:
    from catboost import CatBoostRegressor

    oof = np.zeros(len(X), dtype=float)
    test_predictions: list[np.ndarray] = []
    fold_scores: list[float] = []
    models: list[Any] = []
    best_iterations: list[int] = []

    for train_index, valid_index in splits:
        model = CatBoostRegressor(**parameters)
        model.fit(
            X.iloc[train_index],
            y.iloc[train_index],
            cat_features=category_columns,
            eval_set=(X.iloc[valid_index], y.iloc[valid_index]),
            early_stopping_rounds=200,
            verbose=False,
        )
        valid_prediction = model.predict(X.iloc[valid_index])
        oof[valid_index] = valid_prediction
        fold_scores.append(rmse(y.iloc[valid_index], valid_prediction))
        models.append(model)
        best_iterations.append(int(model.get_best_iteration()) + 1)

        if X_test is not None:
            test_predictions.append(model.predict(X_test))

    test_prediction = None
    if test_predictions:
        test_prediction = np.mean(test_predictions, axis=0)

    return OOFResult(
        name=name,
        oof_prediction=oof,
        test_prediction=test_prediction,
        fold_scores=fold_scores,
        fitted_models=models,
        best_iterations=best_iterations,
    ).attach_target(y.to_numpy())


def rmse(y_true: Any, y_prediction: Any) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_prediction)))


def make_splits(
    row_count: int,
    seed: int = SEED,
    folds: int = 5,
) -> list[tuple[np.ndarray, np.ndarray]]:
    splitter = KFold(n_splits=folds, shuffle=True, random_state=seed)
    return list(splitter.split(np.arange(row_count)))


def optimize_blend_weights(
    predictions: np.ndarray,
    target: np.ndarray,
    l2_penalty: float = 0.0,
) -> np.ndarray:
    model_count = predictions.shape[1]
    initial_weights = np.full(model_count, 1 / model_count)

    result = minimize(
        lambda weights: np.mean(np.square(target - predictions @ weights))
        + l2_penalty * np.sum(np.square(weights)),
        initial_weights,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * model_count,
        constraints={"type": "eq", "fun": lambda weights: weights.sum() - 1},
        options={"maxiter": 2000, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"Blend optimization failed: {result.message}")
    weights = np.clip(result.x, 0, 1)
    return weights / weights.sum()


def cross_fitted_blend(
    predictions: np.ndarray,
    target: np.ndarray,
    seed: int = 2026,
    l2_penalty: float = 0.0,
) -> tuple[np.ndarray, list[np.ndarray]]:
    blend_oof = np.zeros(len(target))
    fold_weights: list[np.ndarray] = []

    for train_index, valid_index in make_splits(len(target), seed=seed):
        weights = optimize_blend_weights(
            predictions[train_index],
            target[train_index],
            l2_penalty=l2_penalty,
        )
        blend_oof[valid_index] = predictions[valid_index] @ weights
        fold_weights.append(weights)

    return blend_oof, fold_weights


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def save_model(path: Path, model: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
