from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


PRIMARY_SEED = 2026
RANDOM_SEEDS = [42, 2026, 3407, 777, 2025]


def find_data(root: Path) -> tuple[Path, Path, Path | None]:
    train_files = list(root.rglob("train.csv"))
    test_files = list(root.rglob("test.csv"))
    if not train_files or not test_files:
        raise FileNotFoundError("train.csv or test.csv was not found below the project root")
    pairs = [(a, b) for a in train_files for b in test_files if a.parent == b.parent]
    if not pairs:
        raise FileNotFoundError("train.csv and test.csv were not found in the same directory")
    train_path, test_path = sorted(pairs, key=lambda pair: ("raw" not in str(pair[0]).lower(), len(str(pair[0]))))[0]
    sample = train_path.parent / "gender_submission.csv"
    return train_path, test_path, sample if sample.exists() else None


def normalize_title(name: pd.Series) -> pd.Series:
    title = name.str.extract(r",\s*([^.]+)\.", expand=False).str.strip()
    title = title.replace({"Mlle": "Miss", "Ms": "Miss", "Mme": "Mrs"})
    return title.where(title.isin(["Mr", "Mrs", "Miss", "Master"]), "Rare")


def normalize_ticket(ticket: pd.Series) -> pd.Series:
    return ticket.str.upper().str.replace(r"[\s./]+", "", regex=True)


def ticket_prefix(ticket: pd.Series) -> pd.Series:
    prefix = ticket.str.replace(r"\d+", "", regex=True)
    return prefix.mask(prefix.eq(""), "NUMERIC")


def ticket_number(ticket: pd.Series) -> pd.Series:
    number = ticket.str.extract(r"(\d+)$", expand=False)
    return pd.to_numeric(number, errors="coerce")


def basic_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["Title"] = normalize_title(out["Name"])
    out["Surname"] = out["Name"].str.split(",", n=1).str[0].str.strip().str.upper()
    out["NameLength"] = out["Name"].str.len()
    out["FamilySize"] = out["SibSp"] + out["Parch"] + 1
    out["IsAlone"] = out["FamilySize"].eq(1).astype("int8")
    out["FamilyID"] = out["Surname"] + "_" + out["FamilySize"].astype(str)
    out.loc[out["FamilySize"].eq(1), "FamilyID"] = "SOLO_" + out.loc[out["FamilySize"].eq(1), "PassengerId"].astype(str)
    out["TicketNormalized"] = normalize_ticket(out["Ticket"])
    out["TicketPrefix"] = ticket_prefix(out["TicketNormalized"])
    out["TicketNumber"] = ticket_number(out["TicketNormalized"])
    out["TicketNumericLength"] = out["TicketNormalized"].str.extract(r"(\d+)$", expand=False).str.len().fillna(0)
    out["HasCabin"] = out["Cabin"].notna().astype("int8")
    out["Deck"] = out["Cabin"].str[0].fillna("Unknown")
    out["CabinCount"] = out["Cabin"].fillna("").str.split().str.len().replace(0, 0)
    out["AgeMissing"] = out["Age"].isna().astype("int8")
    out["FareMissing"] = out["Fare"].isna().astype("int8")
    return out


@dataclass
class FeatureBuilder:
    frequency_source: pd.DataFrame
    age_strategy: str = "smart"
    child_age: int = 16
    combined_frequency: bool = True

    def fit(self, frame: pd.DataFrame) -> "FeatureBuilder":
        base = basic_features(frame)
        source = basic_features(self.frequency_source if self.combined_frequency else frame)
        self.ticket_counts_ = source["TicketNormalized"].value_counts()
        self.family_counts_ = source["FamilyID"].value_counts()
        self.female_family_counts_ = source.loc[source["Sex"].eq("female"), "FamilyID"].value_counts()
        self.child_family_counts_ = source.loc[source["Age"].lt(self.child_age), "FamilyID"].value_counts()
        self.title_counts_ = base["Title"].value_counts()
        self.embarked_mode_ = base["Embarked"].mode().iat[0]
        self.global_age_ = float(base["Age"].median())
        self.global_fare_ = float(base["Fare"].median())
        self.age_tables_ = {
            "tps": base.groupby(["Title", "Pclass", "Sex"], observed=True)["Age"].median(),
            "tp": base.groupby(["Title", "Pclass"], observed=True)["Age"].median(),
            "t": base.groupby("Title", observed=True)["Age"].median(),
            "ps": base.groupby(["Pclass", "Sex"], observed=True)["Age"].median(),
        }
        self.fare_table_ = base.groupby(["Pclass", "Embarked"], observed=True)["Fare"].median()
        _, self.fare_edges_ = pd.qcut(base["Fare"].fillna(self.global_fare_), 4, retbins=True, duplicates="drop")
        self.fare_edges_[0], self.fare_edges_[-1] = -np.inf, np.inf
        return self

    @staticmethod
    def _map_multi(frame: pd.DataFrame, columns: list[str], table: pd.Series) -> pd.Series:
        keys = pd.MultiIndex.from_frame(frame[columns])
        return pd.Series(table.reindex(keys).to_numpy(), index=frame.index)

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = basic_features(frame)
        out["Embarked"] = out["Embarked"].fillna(self.embarked_mode_)
        if self.age_strategy == "median":
            age_fill = pd.Series(self.global_age_, index=out.index)
        elif self.age_strategy == "pclass_sex":
            age_fill = self._map_multi(out, ["Pclass", "Sex"], self.age_tables_["ps"]).fillna(self.global_age_)
        elif self.age_strategy == "title_pclass":
            age_fill = self._map_multi(out, ["Title", "Pclass"], self.age_tables_["tp"])
            age_fill = age_fill.fillna(out["Title"].map(self.age_tables_["t"])).fillna(self.global_age_)
        else:
            age_fill = self._map_multi(out, ["Title", "Pclass", "Sex"], self.age_tables_["tps"])
            age_fill = age_fill.fillna(self._map_multi(out, ["Title", "Pclass"], self.age_tables_["tp"]))
            age_fill = age_fill.fillna(out["Title"].map(self.age_tables_["t"])).fillna(self.global_age_)
        out["Age"] = out["Age"].fillna(age_fill)
        fare_fill = self._map_multi(out, ["Pclass", "Embarked"], self.fare_table_).fillna(self.global_fare_)
        out["Fare"] = out["Fare"].fillna(fare_fill)
        out["TicketGroupSize"] = out["TicketNormalized"].map(self.ticket_counts_).fillna(1).astype(int)
        out["FamilyGroupSize"] = out["FamilyID"].map(self.family_counts_).fillna(1).astype(int)
        out["FemaleFamilySize"] = out["FamilyID"].map(self.female_family_counts_).fillna(0).astype(int)
        out["ChildFamilySize"] = out["FamilyID"].map(self.child_family_counts_).fillna(0).astype(int)
        out["SharedTicket"] = out["TicketGroupSize"].gt(1).astype("int8")
        out["TitleFrequency"] = out["Title"].map(self.title_counts_).fillna(0)
        out["FarePerPerson"] = out["Fare"] / out["TicketGroupSize"].clip(lower=1)
        out["LogFare"] = np.log1p(out["Fare"])
        out["LogFarePerPerson"] = np.log1p(out["FarePerPerson"])
        out["FareBand"] = pd.cut(out["Fare"], bins=self.fare_edges_, labels=False, include_lowest=True).astype(str)
        out["FamilySizeBand"] = pd.cut(
            out["FamilySize"], [0, 1, 2, 4, np.inf], labels=["1", "2", "3-4", "5+"]
        ).astype(str)
        out["AgeBand"] = pd.cut(
            out["Age"], [0, 12, 18, 35, 60, np.inf], labels=["Child", "Teen", "YoungAdult", "Adult", "Senior"], include_lowest=True
        ).astype(str)
        out["IsChild"] = out["Age"].lt(self.child_age).astype("int8")
        out["IsMaster"] = out["Title"].eq("Master").astype("int8")
        out["IsMother"] = (
            out["Sex"].eq("female") & out["Age"].gt(18) & out["Parch"].gt(0) & ~out["Title"].eq("Miss")
        ).astype("int8")
        out["Sex_Pclass"] = out["Sex"] + "_" + out["Pclass"].astype(str)
        out["Title_Pclass"] = out["Title"] + "_" + out["Pclass"].astype(str)
        out["Sex_AgeBand"] = out["Sex"] + "_" + out["AgeBand"]
        out["Family_Pclass"] = out["FamilySizeBand"] + "_" + out["Pclass"].astype(str)
        out["Alone_Sex"] = out["IsAlone"].astype(str) + "_" + out["Sex"]
        out["Alone_Pclass"] = out["IsAlone"].astype(str) + "_" + out["Pclass"].astype(str)
        out["Deck_Pclass"] = out["Deck"] + "_" + out["Pclass"].astype(str)
        return out


FEATURE_GROUPS = {
    "basic": ["Pclass", "Sex", "Age", "SibSp", "Parch", "Fare", "Embarked"],
    "title": ["Title", "NameLength", "TitleFrequency"],
    "family": ["FamilySize", "IsAlone", "FamilySizeBand", "FamilyGroupSize", "FemaleFamilySize", "ChildFamilySize", "IsMother", "IsChild", "IsMaster"],
    "ticket": ["TicketPrefix", "TicketNumber", "TicketGroupSize", "SharedTicket", "TicketNumericLength"],
    "fare": ["FarePerPerson", "LogFare", "LogFarePerPerson", "FareBand"],
    "cabin": ["HasCabin", "Deck", "CabinCount"],
    "age": ["AgeBand", "AgeMissing", "FareMissing"],
    "interactions": ["Sex_Pclass", "Title_Pclass", "Sex_AgeBand", "Family_Pclass", "Alone_Sex", "Alone_Pclass", "Deck_Pclass"],
    "group": [
        "FamilySurvivalRate", "FamilySurvivalCount", "TicketSurvivalRate", "TicketSurvivalCount",
        "WCGFamilyRate", "WCGFamilyCount", "WCGTicketRate", "WCGTicketCount",
    ],
    "group_family": ["FamilySurvivalRate", "FamilySurvivalCount", "WCGFamilyRate", "WCGFamilyCount"],
    "group_ticket": ["TicketSurvivalRate", "TicketSurvivalCount", "WCGTicketRate", "WCGTicketCount"],
}


FEATURE_SETS = {
    "E0_Basic": ["basic"],
    "E1_Title": ["basic", "title"],
    "E2_Family": ["basic", "title", "family"],
    "E3_Ticket": ["basic", "title", "family", "ticket"],
    "E4_Fare": ["basic", "title", "family", "ticket", "fare"],
    "E5_Cabin": ["basic", "title", "family", "ticket", "fare", "cabin"],
    "E6_SmartAge": ["basic", "title", "family", "ticket", "fare", "cabin", "age"],
    "E7_Interactions": ["basic", "title", "family", "ticket", "fare", "cabin", "age", "interactions"],
    "E8_FamilySurvival": ["basic", "title", "family", "ticket", "fare", "cabin", "age", "interactions", "group_family"],
    "E9_TicketSurvival": ["basic", "title", "family", "ticket", "fare", "cabin", "age", "interactions", "group_family", "group_ticket"],
    "E10_Group": ["basic", "title", "family", "ticket", "fare", "cabin", "age", "interactions", "group"],
}


def feature_columns(name: str) -> list[str]:
    return list(dict.fromkeys(column for group in FEATURE_SETS[name] for column in FEATURE_GROUPS[group]))


def _lookup_group_stats(keys: pd.Series, source_keys: pd.Series, y: pd.Series, prior: float, alpha: float) -> tuple[pd.Series, pd.Series]:
    stats = pd.DataFrame({"key": source_keys, "y": np.asarray(y)}).groupby("key")["y"].agg(["sum", "count"])
    sums = keys.map(stats["sum"])
    counts = keys.map(stats["count"]).fillna(0)
    rates = (sums.fillna(0) + alpha * prior) / (counts + alpha)
    return rates.astype(float), counts.astype(float)


def add_group_features(
    source: pd.DataFrame,
    y: pd.Series,
    target: pd.DataFrame,
    training_target: bool,
    alpha: float = 1.0,
) -> pd.DataFrame:
    out = target.copy()
    y_series = pd.Series(np.asarray(y), index=source.index)
    prior = float(y_series.mean())
    for key, prefix in [("FamilyID", "Family"), ("TicketNormalized", "Ticket")]:
        if training_target:
            grouped_sum = y_series.groupby(source[key]).transform("sum") - y_series
            grouped_count = y_series.groupby(source[key]).transform("count") - 1
            out[f"{prefix}SurvivalRate"] = (grouped_sum + alpha * prior) / (grouped_count + alpha)
            out[f"{prefix}SurvivalCount"] = grouped_count.astype(float)
        else:
            rate, count = _lookup_group_stats(out[key], source[key], y_series, prior, alpha)
            out[f"{prefix}SurvivalRate"] = rate
            out[f"{prefix}SurvivalCount"] = count

    reference = source["Sex"].eq("female") | source["IsChild"].eq(1)
    reference_source = source.loc[reference]
    reference_y = y_series.loc[reference]
    for key, prefix in [("FamilyID", "WCGFamily"), ("TicketNormalized", "WCGTicket")]:
        if training_target:
            stats = pd.DataFrame({"key": reference_source[key], "y": reference_y}).groupby("key")["y"].agg(["sum", "count"])
            sums = out[key].map(stats["sum"]).fillna(0)
            counts = out[key].map(stats["count"]).fillna(0)
            self_reference = reference.astype(int)
            sums = sums - y_series * self_reference
            counts = counts - self_reference
            out[f"{prefix}Rate"] = (sums + alpha * prior) / (counts + alpha)
            out[f"{prefix}Count"] = counts.clip(lower=0).astype(float)
        else:
            rate, count = _lookup_group_stats(out[key], reference_source[key], reference_y, prior, alpha)
            out[f"{prefix}Rate"] = rate
            out[f"{prefix}Count"] = count
    return out


def make_preprocessor(frame: pd.DataFrame, columns: list[str]) -> ColumnTransformer:
    categorical = [column for column in columns if not pd.api.types.is_numeric_dtype(frame[column])]
    numeric = [column for column in columns if column not in categorical]
    return ColumnTransformer([
        ("num", Pipeline([("impute", SimpleImputer(strategy="median"))]), numeric),
        ("cat", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), categorical),
    ], remainder="drop", verbose_feature_names_out=False)


def score_metrics(y_true: pd.Series | np.ndarray, probability: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    prediction = (probability >= threshold).astype(int)
    return {
        "Accuracy": accuracy_score(y_true, prediction),
        "Precision": precision_score(y_true, prediction, zero_division=0),
        "Recall": recall_score(y_true, prediction, zero_division=0),
        "F1": f1_score(y_true, prediction, zero_division=0),
        "AUC": roc_auc_score(y_true, probability),
    }


@dataclass
class FoldData:
    train_matrix: np.ndarray
    valid_matrix: np.ndarray
    test_matrix: np.ndarray
    y_train: np.ndarray
    y_valid: np.ndarray
    valid_index: np.ndarray
    feature_names: np.ndarray


def build_fold_data(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_set: str,
    seed: int,
    age_strategy: str = "smart",
    child_age: int = 16,
    combined_frequency: bool = True,
) -> list[FoldData]:
    y = train["Survived"].astype(int).reset_index(drop=True)
    raw_x = train.drop(columns="Survived").reset_index(drop=True)
    test_x = test.reset_index(drop=True)
    frequency_source = pd.concat([raw_x, test_x], ignore_index=True)
    use_group = any(group.startswith("group") for group in FEATURE_SETS[feature_set])
    columns = feature_columns(feature_set)
    folds = []
    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    for train_index, valid_index in splitter.split(raw_x, y):
        fold_train, fold_valid = raw_x.iloc[train_index], raw_x.iloc[valid_index]
        y_train, y_valid = y.iloc[train_index], y.iloc[valid_index]
        builder = FeatureBuilder(frequency_source, age_strategy, child_age, combined_frequency).fit(fold_train)
        engineered_train = builder.transform(fold_train)
        engineered_valid = builder.transform(fold_valid)
        engineered_test = builder.transform(test_x)
        if use_group:
            engineered_train = add_group_features(engineered_train, y_train, engineered_train, True)
            engineered_valid = add_group_features(engineered_train, y_train, engineered_valid, False)
            engineered_test = add_group_features(engineered_train, y_train, engineered_test, False)
        preprocessor = make_preprocessor(engineered_train, columns)
        train_matrix = preprocessor.fit_transform(engineered_train[columns])
        folds.append(FoldData(
            train_matrix=train_matrix,
            valid_matrix=preprocessor.transform(engineered_valid[columns]),
            test_matrix=preprocessor.transform(engineered_test[columns]),
            y_train=y_train.to_numpy(),
            y_valid=y_valid.to_numpy(),
            valid_index=valid_index,
            feature_names=preprocessor.get_feature_names_out(),
        ))
    return folds


def evaluate_on_folds(
    model_factory: Callable[[], object],
    folds: list[FoldData],
    row_count: int,
    test_count: int,
    scale: bool,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, float]], list[object]]:
    oof = np.zeros(row_count)
    test_probability = np.zeros(test_count)
    fold_metrics = []
    fitted_models = []
    for fold_number, fold in enumerate(folds, 1):
        model = model_factory()
        if scale:
            model = Pipeline([("scale", StandardScaler()), ("model", model)])
        model.fit(fold.train_matrix, fold.y_train)
        train_probability = model.predict_proba(fold.train_matrix)[:, 1]
        valid_probability = model.predict_proba(fold.valid_matrix)[:, 1]
        oof[fold.valid_index] = valid_probability
        test_probability += model.predict_proba(fold.test_matrix)[:, 1] / len(folds)
        metrics = score_metrics(fold.y_valid, valid_probability)
        metrics.update({
            "Fold": fold_number,
            "TrainAccuracy": accuracy_score(fold.y_train, (train_probability >= 0.5).astype(int)),
            "ValidationSamples": len(fold.y_valid),
        })
        fold_metrics.append(metrics)
        fitted_models.append(model)
    return oof, test_probability, fold_metrics, fitted_models


def full_training_matrices(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_set: str,
    age_strategy: str = "smart",
    child_age: int = 16,
    combined_frequency: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    y = train["Survived"].astype(int).reset_index(drop=True)
    raw_x = train.drop(columns="Survived").reset_index(drop=True)
    test_x = test.reset_index(drop=True)
    source = pd.concat([raw_x, test_x], ignore_index=True)
    builder = FeatureBuilder(source, age_strategy, child_age, combined_frequency).fit(raw_x)
    train_eng, test_eng = builder.transform(raw_x), builder.transform(test_x)
    if any(group.startswith("group") for group in FEATURE_SETS[feature_set]):
        train_eng = add_group_features(train_eng, y, train_eng, True)
        test_eng = add_group_features(train_eng, y, test_eng, False)
    columns = feature_columns(feature_set)
    preprocessor = make_preprocessor(train_eng, columns)
    train_matrix = preprocessor.fit_transform(train_eng[columns])
    test_matrix = preprocessor.transform(test_eng[columns])
    return train_matrix, test_matrix, y.to_numpy(), preprocessor.get_feature_names_out()


def audit_data(train: pd.DataFrame, test: pd.DataFrame, sample: pd.DataFrame | None) -> dict[str, object]:
    expected = ["PassengerId", "Survived", "Pclass", "Name", "Sex", "Age", "SibSp", "Parch", "Ticket", "Fare", "Cabin", "Embarked"]
    report = {
        "train_shape": list(train.shape),
        "test_shape": list(test.shape),
        "train_columns_valid": train.columns.tolist() == expected,
        "test_columns_valid": test.columns.tolist() == [c for c in expected if c != "Survived"],
        "train_dtypes": train.dtypes.astype(str).to_dict(),
        "test_dtypes": test.dtypes.astype(str).to_dict(),
        "train_missing": train.isna().sum().loc[lambda s: s.gt(0)].to_dict(),
        "test_missing": test.isna().sum().loc[lambda s: s.gt(0)].to_dict(),
        "duplicate_train_rows": int(train.duplicated().sum()),
        "duplicate_test_rows": int(test.duplicated().sum()),
        "train_id_unique": bool(train["PassengerId"].is_unique),
        "test_id_unique": bool(test["PassengerId"].is_unique),
        "id_overlap": int(len(set(train["PassengerId"]) & set(test["PassengerId"]))),
        "target_distribution": train["Survived"].value_counts().sort_index().to_dict(),
        "target_rate": float(train["Survived"].mean()),
        "sample_matches_test": bool(sample is None or sample["PassengerId"].equals(test["PassengerId"])),
        "name_parse_failures": int(normalize_title(train["Name"]).isna().sum() + normalize_title(test["Name"]).isna().sum()),
        "ticket_parse_failures": int(normalize_ticket(train["Ticket"]).isna().sum() + normalize_ticket(test["Ticket"]).isna().sum()),
    }
    failures = [key for key in ["train_columns_valid", "test_columns_valid", "train_id_unique", "test_id_unique", "sample_matches_test"] if not report[key]]
    if report["id_overlap"] or failures:
        raise ValueError(f"Data audit failed: {failures}, id_overlap={report['id_overlap']}")
    return report


def save_json(value: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
