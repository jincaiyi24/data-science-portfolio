from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PREPARED_DIR = PROJECT_ROOT / "data" / "prepared"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"

EXPECTED_TRAIN_COLUMNS = [
    "PassengerId", "Survived", "Pclass", "Name", "Sex", "Age",
    "SibSp", "Parch", "Ticket", "Fare", "Cabin", "Embarked",
]
EXPECTED_TEST_COLUMNS = [column for column in EXPECTED_TRAIN_COLUMNS if column != "Survived"]

MODEL_COLUMNS = [
    "PassengerId", "Pclass", "Sex", "Age", "SibSp", "Parch", "Fare",
    "Embarked", "Title", "FamilySize", "IsAlone", "FamilySizeGroup",
    "Mother", "Child", "Deck", "CabinKnown", "TicketPrefix",
    "TicketGroupSize", "SurnameGroupSize", "FarePerPerson", "LogFare",
    "AgeBand", "AgeWasMissing", "FareWasMissing", "FareOutlier", "AgeOutlier",
]


def load_raw_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = pd.read_csv(RAW_DIR / "train.csv")
    test = pd.read_csv(RAW_DIR / "test.csv")
    sample = pd.read_csv(RAW_DIR / "gender_submission.csv")
    return train, test, sample


def validate_raw_data(
    train: pd.DataFrame, test: pd.DataFrame, sample: pd.DataFrame
) -> dict[str, object]:
    checks = {
        "train_columns_match": train.columns.tolist() == EXPECTED_TRAIN_COLUMNS,
        "test_columns_match": test.columns.tolist() == EXPECTED_TEST_COLUMNS,
        "train_rows": len(train),
        "test_rows": len(test),
        "sample_rows": len(sample),
        "train_id_unique": train["PassengerId"].is_unique,
        "test_id_unique": test["PassengerId"].is_unique,
        "train_test_id_overlap": len(set(train["PassengerId"]) & set(test["PassengerId"])),
        "target_missing": int(train["Survived"].isna().sum()),
        "target_values_valid": set(train["Survived"].unique()) <= {0, 1},
        "sample_ids_match_test": sample["PassengerId"].equals(test["PassengerId"]),
        "exact_duplicate_train_rows": int(train.duplicated().sum()),
        "exact_duplicate_test_rows": int(test.duplicated().sum()),
        "pclass_valid": set(pd.concat([train["Pclass"], test["Pclass"]]).unique()) <= {1, 2, 3},
        "sex_valid": set(pd.concat([train["Sex"], test["Sex"]]).unique()) <= {"female", "male"},
        "embarked_valid": set(pd.concat([train["Embarked"], test["Embarked"]]).dropna().unique()) <= {"C", "Q", "S"},
        "nonnegative_counts": bool((pd.concat([train[["SibSp", "Parch"]], test[["SibSp", "Parch"]]]) >= 0).all().all()),
        "nonnegative_fare": bool(pd.concat([train["Fare"], test["Fare"]]).dropna().ge(0).all()),
        "positive_known_age": bool(pd.concat([train["Age"], test["Age"]]).dropna().gt(0).all()),
    }
    boolean_failures = [
        key for key, value in checks.items()
        if isinstance(value, (bool, np.bool_)) and not value
    ]
    if boolean_failures:
        raise ValueError(f"Raw data validation failed: {boolean_failures}")
    return checks


def extract_title(name: pd.Series) -> pd.Series:
    title = name.str.extract(r",\s*([^.]*)\.", expand=False).str.strip()
    title = title.replace({"Mlle": "Miss", "Ms": "Miss", "Mme": "Mrs"})
    common = {"Mr", "Miss", "Mrs", "Master"}
    return title.where(title.isin(common), "Rare")


def extract_ticket_prefix(ticket: pd.Series) -> pd.Series:
    prefix = ticket.str.replace(r"\d+", "", regex=True)
    prefix = prefix.str.replace(r"[\s./]+", "", regex=True).str.upper()
    return prefix.mask(prefix.eq(""), "NUMERIC")


def family_size_group(size: pd.Series) -> pd.Series:
    return pd.cut(
        size,
        bins=[0, 1, 4, 7, np.inf],
        labels=["Alone", "Small", "Medium", "Large"],
        include_lowest=True,
    ).astype("object")


def add_base_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["AgeWasMissing"] = result["Age"].isna().astype("int8")
    result["FareWasMissing"] = result["Fare"].isna().astype("int8")
    result["Title"] = extract_title(result["Name"])
    result["Surname"] = result["Name"].str.split(",", n=1).str[0].str.strip()
    result["FamilySize"] = result["SibSp"] + result["Parch"] + 1
    result["IsAlone"] = result["FamilySize"].eq(1).astype("int8")
    result["FamilySizeGroup"] = family_size_group(result["FamilySize"])
    result["CabinKnown"] = result["Cabin"].notna().astype("int8")
    result["Deck"] = result["Cabin"].str[0].fillna("Unknown")
    result["TicketPrefix"] = extract_ticket_prefix(result["Ticket"])
    return result


def _fill_from_group_median(
    target: pd.DataFrame,
    source: pd.DataFrame,
    column: str,
    group_columns: list[str],
) -> pd.Series:
    medians = source.groupby(group_columns, observed=True)[column].median()
    keys = pd.MultiIndex.from_frame(target[group_columns])
    return pd.Series(medians.reindex(keys).to_numpy(), index=target.index)


def prepare_datasets(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    train_work = add_base_features(train)
    test_work = add_base_features(test)

    # Counts use both unlabeled tables. This adds no target information.
    combined = pd.concat(
        [train_work.assign(_dataset="train"), test_work.assign(_dataset="test")],
        ignore_index=True,
        sort=False,
    )
    ticket_counts = combined["Ticket"].value_counts()
    surname_counts = combined.groupby(["Surname", "FamilySize"], observed=True).size()
    for frame in (train_work, test_work):
        frame["TicketGroupSize"] = frame["Ticket"].map(ticket_counts).astype("int16")
        surname_keys = pd.MultiIndex.from_frame(frame[["Surname", "FamilySize"]])
        frame["SurnameGroupSize"] = surname_counts.reindex(surname_keys).to_numpy().astype("int16")

    embarked_mode = train_work["Embarked"].mode().iat[0]
    train_work["Embarked"] = train_work["Embarked"].fillna(embarked_mode)
    test_work["Embarked"] = test_work["Embarked"].fillna(embarked_mode)

    age_group = ["Title", "Pclass", "Sex"]
    age_fallback_group = ["Pclass", "Sex"]
    global_age = float(train_work["Age"].median())
    for frame in (train_work, test_work):
        age_fill = _fill_from_group_median(frame, train_work, "Age", age_group)
        age_fill = age_fill.fillna(
            _fill_from_group_median(frame, train_work, "Age", age_fallback_group)
        ).fillna(global_age)
        frame["Age"] = frame["Age"].fillna(age_fill)

    fare_group = ["Pclass", "Embarked"]
    fare_fill = _fill_from_group_median(test_work, train_work, "Fare", fare_group)
    fare_fill = fare_fill.fillna(
        _fill_from_group_median(test_work, train_work, "Fare", ["Pclass"])
    ).fillna(float(train_work["Fare"].median()))
    test_work["Fare"] = test_work["Fare"].fillna(fare_fill)

    age_q1, age_q3 = train_work["Age"].quantile([0.25, 0.75])
    fare_q1, fare_q3 = train_work["Fare"].quantile([0.25, 0.75])
    age_iqr, fare_iqr = age_q3 - age_q1, fare_q3 - fare_q1
    age_bounds = (max(0.0, age_q1 - 1.5 * age_iqr), age_q3 + 1.5 * age_iqr)
    fare_bounds = (max(0.0, fare_q1 - 1.5 * fare_iqr), fare_q3 + 1.5 * fare_iqr)

    for frame in (train_work, test_work):
        frame["FarePerPerson"] = frame["Fare"] / frame["TicketGroupSize"].clip(lower=1)
        frame["LogFare"] = np.log1p(frame["Fare"])
        frame["AgeBand"] = pd.cut(
            frame["Age"],
            bins=[0, 12, 18, 35, 60, np.inf],
            labels=["Child", "Teen", "YoungAdult", "Adult", "Senior"],
            include_lowest=True,
        ).astype("object")
        frame["Child"] = frame["Age"].lt(16).astype("int8")
        frame["Mother"] = (
            frame["Sex"].eq("female")
            & frame["Age"].gt(18)
            & frame["Parch"].gt(0)
            & ~frame["Title"].eq("Miss")
        ).astype("int8")
        frame["AgeOutlier"] = (~frame["Age"].between(*age_bounds)).astype("int8")
        frame["FareOutlier"] = (~frame["Fare"].between(*fare_bounds)).astype("int8")

    train_model = train_work[MODEL_COLUMNS + ["Survived"]].copy()
    test_model = test_work[MODEL_COLUMNS].copy()

    audit = pd.DataFrame(
        [
            ["Age", int(train["Age"].isna().sum()), int(test["Age"].isna().sum()), "Training-only grouped medians", "Title + Pclass + Sex"],
            ["Embarked", int(train["Embarked"].isna().sum()), int(test["Embarked"].isna().sum()), embarked_mode, "Training mode"],
            ["Fare", int(train["Fare"].isna().sum()), int(test["Fare"].isna().sum()), "Training-only grouped median", "Pclass + Embarked"],
            ["Cabin", int(train["Cabin"].isna().sum()), int(test["Cabin"].isna().sum()), "Unknown deck", "No cabin number fabricated"],
        ],
        columns=["Column", "TrainMissingBefore", "TestMissingBefore", "Treatment", "Basis"],
    )
    metadata = {
        "embarked_fill": embarked_mode,
        "global_age_fallback": global_age,
        "age_outlier_bounds": [float(age_bounds[0]), float(age_bounds[1])],
        "fare_outlier_bounds": [float(fare_bounds[0]), float(fare_bounds[1])],
        "model_feature_count_excluding_id": len(MODEL_COLUMNS) - 1,
    }
    return train_work, test_work, audit, metadata


def build_profile(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dataset_name, frame in (("train", train), ("test", test)):
        for column in frame.columns:
            series = frame[column]
            rows.append({
                "Dataset": dataset_name,
                "Column": column,
                "Dtype": str(series.dtype),
                "Rows": len(frame),
                "Missing": int(series.isna().sum()),
                "MissingRate": float(series.isna().mean()),
                "Unique": int(series.nunique(dropna=True)),
            })
    return pd.DataFrame(rows)


def categorical_summary(train: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in ["Survived", "Pclass", "Sex", "Embarked"]:
        counts = train[column].fillna("Missing").value_counts(dropna=False)
        for value, count in counts.items():
            rows.append({
                "Column": column,
                "Value": value,
                "Count": int(count),
                "Rate": float(count / len(train)),
            })
    return pd.DataFrame(rows)


def survival_summary(train_prepared: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in ["Sex", "Pclass", "Embarked", "Title", "FamilySizeGroup", "AgeBand", "CabinKnown"]:
        grouped = train_prepared.groupby(column, observed=True)["Survived"].agg(["count", "sum", "mean"])
        for value, record in grouped.iterrows():
            rows.append({
                "Feature": column,
                "Group": value,
                "Passengers": int(record["count"]),
                "Survivors": int(record["sum"]),
                "SurvivalRate": float(record["mean"]),
            })
    return pd.DataFrame(rows)


def make_figures(train: pd.DataFrame, train_prepared: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    missing = pd.DataFrame({
        "Train": train.isna().mean().mul(100),
    }).query("Train > 0").sort_values("Train")
    ax = missing.plot.barh(figsize=(8, 4), color="#2f6f8f", legend=False)
    ax.set(title="Missing Values in Training Data", xlabel="Missing rate (%)", ylabel="")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.1f%%", padding=3)
    plt.tight_layout()
    plt.savefig(FIGURE_DIR / "01_missing_values.png", dpi=160)
    plt.close()

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    train["Survived"].value_counts().sort_index().rename(index={0: "Did not survive", 1: "Survived"}).plot.bar(
        ax=axes[0], color=["#5a6570", "#d4883b"], rot=0
    )
    train_prepared.groupby("Sex")["Survived"].mean().sort_values().plot.bar(
        ax=axes[1], color="#2f6f8f", rot=0
    )
    train_prepared.groupby("Pclass")["Survived"].mean().sort_index().plot.bar(
        ax=axes[2], color="#5b8c5a", rot=0
    )
    axes[0].set_title("Target Balance")
    axes[0].set_ylabel("Passengers")
    axes[1].set_title("Survival Rate by Sex")
    axes[1].set_ylabel("Survival rate")
    axes[2].set_title("Survival Rate by Passenger Class")
    axes[2].set_ylabel("Survival rate")
    plt.tight_layout()
    plt.savefig(FIGURE_DIR / "02_survival_overview.png", dpi=160)
    plt.close()

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for survived, label, color in [(0, "Did not survive", "#5a6570"), (1, "Survived", "#d4883b")]:
        train_prepared.loc[train_prepared["Survived"].eq(survived), "Age"].plot.hist(
            bins=25, alpha=0.55, ax=axes[0], label=label, color=color
        )
    axes[0].set(title="Age Distribution by Outcome", xlabel="Age", ylabel="Passengers")
    axes[0].legend()
    train_prepared.boxplot(column="LogFare", by="Survived", ax=axes[1], grid=False)
    axes[1].set(title="Log Fare by Outcome", xlabel="Survived", ylabel="log(1 + Fare)")
    fig.suptitle("")
    plt.tight_layout()
    plt.savefig(FIGURE_DIR / "03_age_and_fare.png", dpi=160)
    plt.close()

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    train_prepared.groupby("FamilySizeGroup", observed=True)["Survived"].mean().plot.bar(
        ax=axes[0], color="#5b8c5a", rot=0
    )
    train_prepared.groupby("Title", observed=True)["Survived"].agg(["count", "mean"]).sort_values("mean")["mean"].plot.barh(
        ax=axes[1], color="#2f6f8f"
    )
    axes[0].set(title="Survival Rate by Family Size", xlabel="Family group", ylabel="Survival rate")
    axes[1].set(title="Survival Rate by Title", xlabel="Survival rate", ylabel="")
    plt.tight_layout()
    plt.savefig(FIGURE_DIR / "04_family_and_title.png", dpi=160)
    plt.close()


def write_reports(
    train: pd.DataFrame,
    test: pd.DataFrame,
    train_prepared: pd.DataFrame,
    test_prepared: pd.DataFrame,
    checks: dict[str, object],
    audit: pd.DataFrame,
    metadata: dict[str, object],
) -> None:
    PREPARED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    train_prepared.to_csv(PREPARED_DIR / "train_prepared.csv", index=False)
    test_prepared.to_csv(PREPARED_DIR / "test_prepared.csv", index=False)
    train_prepared[MODEL_COLUMNS + ["Survived"]].to_csv(PREPARED_DIR / "train_model_input.csv", index=False)
    test_prepared[MODEL_COLUMNS].to_csv(PREPARED_DIR / "test_model_input.csv", index=False)

    profile = build_profile(train, test)
    profile.to_csv(OUTPUT_DIR / "data_profile.csv", index=False)
    profile.loc[profile["Missing"].gt(0)].to_csv(OUTPUT_DIR / "missing_values.csv", index=False)
    train.describe(include="number").T.to_csv(OUTPUT_DIR / "numeric_descriptive_statistics.csv")
    categorical_summary(train).to_csv(OUTPUT_DIR / "categorical_descriptive_statistics.csv", index=False)
    survival_summary(train_prepared).to_csv(OUTPUT_DIR / "survival_group_analysis.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "cleaning_audit.csv", index=False)

    outlier_records = train_prepared.loc[
        train_prepared[["AgeOutlier", "FareOutlier"]].any(axis=1),
        ["PassengerId", "Survived", "Pclass", "Sex", "Age", "Fare", "AgeOutlier", "FareOutlier"],
    ].sort_values(["FareOutlier", "Fare"], ascending=[False, False])
    outlier_records.to_csv(OUTPUT_DIR / "outlier_records_for_review.csv", index=False)
    pd.DataFrame([
        {"Variable": "Age", "LowerBound": metadata["age_outlier_bounds"][0], "UpperBound": metadata["age_outlier_bounds"][1], "TrainFlagged": int(train_prepared["AgeOutlier"].sum()), "Treatment": "Retained and flagged"},
        {"Variable": "Fare", "LowerBound": metadata["fare_outlier_bounds"][0], "UpperBound": metadata["fare_outlier_bounds"][1], "TrainFlagged": int(train_prepared["FareOutlier"].sum()), "Treatment": "Retained; LogFare added"},
    ]).to_csv(OUTPUT_DIR / "outlier_summary.csv", index=False)

    feature_dictionary = pd.DataFrame([
        ["PassengerId", "Identifier", "Stable row identifier; exclude from prediction by default"],
        ["Pclass", "Original", "Passenger class: 1, 2, or 3"],
        ["Sex", "Original", "Recorded sex"],
        ["Age", "Cleaned", "Age; missing values filled from training-only grouped medians"],
        ["Fare", "Cleaned", "Fare; one test value filled from training-only grouped median"],
        ["Embarked", "Cleaned", "Port; two training values filled with training mode"],
        ["Title", "Engineered", "Normalized title extracted from Name"],
        ["FamilySize", "Engineered", "SibSp + Parch + 1"],
        ["IsAlone", "Engineered", "1 when FamilySize equals 1"],
        ["FamilySizeGroup", "Engineered", "Alone, small, medium, or large family"],
        ["Mother", "Engineered", "Adult female travelling with parent/child relation"],
        ["Child", "Engineered", "1 when Age is below 16"],
        ["Deck", "Engineered", "First cabin letter; Unknown when cabin is absent"],
        ["CabinKnown", "Engineered", "1 when a cabin record exists"],
        ["TicketPrefix", "Engineered", "Normalized non-numeric ticket prefix"],
        ["TicketGroupSize", "Engineered", "Passenger count sharing the same ticket across train and test"],
        ["SurnameGroupSize", "Engineered", "Count sharing surname and stated family size"],
        ["FarePerPerson", "Engineered", "Fare divided by ticket group size"],
        ["LogFare", "Engineered", "log(1 + Fare), reducing right skew"],
        ["AgeBand", "Engineered", "Life-stage age group"],
        ["AgeWasMissing", "Audit", "1 when original Age was missing"],
        ["FareWasMissing", "Audit", "1 when original Fare was missing"],
        ["FareOutlier", "Audit", "IQR-based fare flag; row retained"],
        ["AgeOutlier", "Audit", "IQR-based age flag; row retained"],
    ], columns=["Feature", "Type", "Definition"])
    feature_dictionary.to_csv(OUTPUT_DIR / "feature_dictionary.csv", index=False)

    quality_report = {
        "raw_validation": checks,
        "cleaning_metadata": metadata,
        "train_prepared_shape": list(train_prepared.shape),
        "test_prepared_shape": list(test_prepared.shape),
        "train_prepared_missing": int(train_prepared[MODEL_COLUMNS + ["Survived"]].isna().sum().sum()),
        "test_prepared_missing": int(test_prepared[MODEL_COLUMNS].isna().sum().sum()),
        "survival_rate": float(train["Survived"].mean()),
        "note": "No model was trained and no target-derived feature was created.",
    }
    with (OUTPUT_DIR / "data_quality_report.json").open("w", encoding="utf-8") as file:
        json.dump(quality_report, file, ensure_ascii=False, indent=2)


def run_pipeline() -> dict[str, object]:
    train, test, sample = load_raw_data()
    checks = validate_raw_data(train, test, sample)
    train_prepared, test_prepared, audit, metadata = prepare_datasets(train, test)
    write_reports(train, test, train_prepared, test_prepared, checks, audit, metadata)
    make_figures(train, train_prepared)
    return {
        "train": train,
        "test": test,
        "sample": sample,
        "train_prepared": train_prepared,
        "test_prepared": test_prepared,
        "audit": audit,
        "metadata": metadata,
        "checks": checks,
    }


if __name__ == "__main__":
    result = run_pipeline()
    print(f"Prepared train: {result['train_prepared'].shape}")
    print(f"Prepared test:  {result['test_prepared'].shape}")
    print(f"Model-input missing values: {result['train_prepared'][MODEL_COLUMNS + ['Survived']].isna().sum().sum() + result['test_prepared'][MODEL_COLUMNS].isna().sum().sum()}")
