from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from config import AUDIT_DIR, DATA_DIR, ID_COLUMN, TARGET


def load_data(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = [data_dir / name for name in ("train.csv", "test.csv", "sample_submission.csv")]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required files: {missing}")
    return tuple(pd.read_csv(path) for path in paths)  # type: ignore[return-value]


def infer_columns(train: pd.DataFrame) -> tuple[list[str], list[str]]:
    features = train.drop(columns=[TARGET, ID_COLUMN])
    categorical = features.select_dtypes(include=["object", "category"]).columns.tolist()
    numerical = features.columns.difference(categorical, sort=False).tolist()
    return numerical, categorical


def _psi(train: pd.Series, test: pd.Series, bins: int = 10) -> float:
    edges = np.unique(np.quantile(train, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    train_share = pd.cut(train, edges).value_counts(normalize=True, sort=False).clip(1e-6)
    test_share = pd.cut(test, edges).value_counts(normalize=True, sort=False).clip(1e-6)
    return float(((test_share - train_share) * np.log(test_share / train_share)).sum())


def audit_data(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, object]:
    numerical, categorical = infer_columns(train)
    schema = pd.DataFrame(
        {
            "column": train.columns,
            "dtype": train.dtypes.astype(str).values,
            "role": [
                "id" if c == ID_COLUMN else "target" if c == TARGET else "categorical" if c in categorical else "numerical"
                for c in train.columns
            ],
            "train_non_null": train.notna().sum().values,
            "train_unique": train.nunique(dropna=False).values,
            "in_test": [c in test.columns for c in train.columns],
        }
    )
    schema.to_csv(AUDIT_DIR / "data_schema.csv", index=False)

    missing = pd.DataFrame(
        {
            "column": sorted(set(train.columns) | set(test.columns)),
        }
    )
    missing["train_missing"] = missing["column"].map(train.isna().sum()).fillna(np.nan)
    missing["test_missing"] = missing["column"].map(test.isna().sum()).fillna(np.nan)
    missing["train_missing_rate"] = missing["train_missing"] / len(train)
    missing["test_missing_rate"] = missing["test_missing"] / len(test)
    missing.to_csv(AUDIT_DIR / "missing_values.csv", index=False)

    shift_rows: list[dict[str, object]] = []
    for col in numerical:
        ks = ks_2samp(train[col], test[col])
        shift_rows.append(
            {"feature": col, "type": "numeric", "shift_metric": "PSI", "shift_value": _psi(train[col], test[col]), "ks_statistic": ks.statistic}
        )
    for col in categorical:
        levels = sorted(set(train[col].astype(str)) | set(test[col].astype(str)))
        p = train[col].astype(str).value_counts(normalize=True).reindex(levels, fill_value=0)
        q = test[col].astype(str).value_counts(normalize=True).reindex(levels, fill_value=0)
        shift_rows.append(
            {"feature": col, "type": "categorical", "shift_metric": "total_variation", "shift_value": float(0.5 * np.abs(p - q).sum()), "ks_statistic": np.nan}
        )
    shift = pd.DataFrame(shift_rows).sort_values("shift_value", ascending=False)
    shift.to_csv(AUDIT_DIR / "train_test_shift.csv", index=False)

    feature_frame = train.drop(columns=[TARGET, ID_COLUMN])
    test_feature_frame = test.drop(columns=[ID_COLUMN])
    train_hash = pd.util.hash_pandas_object(feature_frame, index=False)
    test_hash = pd.util.hash_pandas_object(test_feature_frame, index=False)
    top_share = feature_frame.apply(lambda s: s.value_counts(normalize=True, dropna=False).iloc[0])
    constant = top_share[top_share == 1].index.tolist()
    near_constant = top_share[(top_share >= 0.99) & (top_share < 1)].index.tolist()
    target_counts = train[TARGET].value_counts().to_dict()
    results = {
        "train_rows": len(train),
        "test_rows": len(test),
        "feature_count": len(numerical) + len(categorical),
        "numerical_count": len(numerical),
        "categorical_count": len(categorical),
        "train_duplicate_rows": int(train.duplicated().sum()),
        "test_duplicate_rows": int(test.duplicated().sum()),
        "train_duplicate_ids": int(train[ID_COLUMN].duplicated().sum()),
        "test_duplicate_ids": int(test[ID_COLUMN].duplicated().sum()),
        "train_duplicate_feature_rows": int(train_hash.duplicated().sum()),
        "test_duplicate_feature_rows": int(test_hash.duplicated().sum()),
        "train_test_exact_feature_overlap": int(test_hash.isin(set(train_hash)).sum()),
        "missing_cells_train": int(train.isna().sum().sum()),
        "missing_cells_test": int(test.isna().sum().sum()),
        "constant_columns": constant,
        "near_constant_columns": near_constant,
        "target_counts": target_counts,
        "positive_rate": float(train[TARGET].eq("Yes").mean()),
        "max_shift_feature": shift.iloc[0]["feature"],
        "max_shift_value": float(shift.iloc[0]["shift_value"]),
        "schema_match": set(train.columns) - {TARGET} == set(test.columns),
    }
    (AUDIT_DIR / "data_quality_report.md").write_text(
        "# Data Quality Report\n\n"
        f"- Train: {len(train):,} rows; test: {len(test):,} rows.\n"
        f"- Features: {len(numerical)} numerical and {len(categorical)} categorical.\n"
        f"- Positive target rate: {results['positive_rate']:.2%}.\n"
        f"- Missing cells: train {results['missing_cells_train']:,}; test {results['missing_cells_test']:,}.\n"
        f"- Duplicate rows: train {results['train_duplicate_rows']:,}; test {results['test_duplicate_rows']:,}.\n"
        f"- Duplicate IDs: train {results['train_duplicate_ids']:,}; test {results['test_duplicate_ids']:,}.\n"
        f"- Duplicate feature rows after excluding ID/target: train {results['train_duplicate_feature_rows']:,}; test {results['test_duplicate_feature_rows']:,}.\n"
        f"- Exact train/test feature overlap: {results['train_test_exact_feature_overlap']:,} rows.\n"
        f"- Constant columns: {constant or 'none'}; near-constant columns: {near_constant or 'none'}.\n"
        f"- Largest measured train/test shift: `{results['max_shift_feature']}` ({results['max_shift_value']:.4f}).\n"
        f"- Feature schemas match: {results['schema_match']}.\n\n"
        "PSI and total-variation results are screening statistics, not automatic reasons to remove features.\n",
        encoding="utf-8",
    )
    (AUDIT_DIR / "audit_summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results
