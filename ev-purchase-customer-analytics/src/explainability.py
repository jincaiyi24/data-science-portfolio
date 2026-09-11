from __future__ import annotations

import numpy as np
import pandas as pd
from catboost import Pool

from config import FIGURE_DIR, RANDOM_STATE, TABLE_DIR


def explain_catboost(model, x: pd.DataFrame, sample_size: int = 3000) -> pd.DataFrame:
    import matplotlib.pyplot as plt
    import shap

    sample = x.sample(min(sample_size, len(x)), random_state=RANDOM_STATE)
    categorical = sample.select_dtypes(include=["object", "category"]).columns.tolist()
    values = model.get_feature_importance(Pool(sample, cat_features=categorical), type="ShapValues")[:, :-1]
    importance = pd.DataFrame({"feature": sample.columns, "mean_abs_shap": np.abs(values).mean(axis=0)}).sort_values("mean_abs_shap", ascending=False)
    importance["importance_share"] = importance["mean_abs_shap"] / importance["mean_abs_shap"].sum()
    importance.to_csv(TABLE_DIR / "feature_importance.csv", index=False)

    shap.summary_plot(values, sample, show=False, max_display=15)
    plt.title("SHAP Summary: Drivers of Predicted EV Purchase Propensity")
    plt.tight_layout(); plt.savefig(FIGURE_DIR / "06_shap_summary.png", dpi=220, bbox_inches="tight"); plt.close()

    top = importance.head(12).sort_values("mean_abs_shap")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(top["feature"], top["mean_abs_shap"], color="#2A9D8F")
    ax.set(title="Top Model Drivers by Mean Absolute SHAP", xlabel="Mean |SHAP value|", ylabel="")
    fig.tight_layout(); fig.savefig(FIGURE_DIR / "05_feature_importance.png", dpi=220); plt.close(fig)

    direction_rows = []
    for feature in importance.head(10)["feature"]:
        idx = sample.columns.get_loc(feature)
        raw = sample[feature]
        encoded = raw.astype("category").cat.codes if raw.dtype == "object" else raw
        correlation = pd.Series(encoded).corr(pd.Series(values[:, idx]))
        direction_rows.append({"feature": feature, "mean_abs_shap": importance.set_index("feature").loc[feature, "mean_abs_shap"], "direction_correlation": correlation})
    direction = pd.DataFrame(direction_rows)
    direction.to_csv(TABLE_DIR / "feature_direction.csv", index=False)
    return importance


def explain_tree_pipeline(pipeline, x: pd.DataFrame, sample_size: int = 3000) -> pd.DataFrame:
    import matplotlib.pyplot as plt
    import shap

    sample = x.sample(min(sample_size, len(x)), random_state=RANDOM_STATE)
    transformer = pipeline.named_steps["preprocessor"]
    estimator = pipeline.named_steps["model"]
    transformed = transformer.transform(sample)
    transformed = transformed.toarray() if hasattr(transformed, "toarray") else np.asarray(transformed)
    transformed_names = transformer.get_feature_names_out().tolist()
    raw_features = []
    categorical = sample.select_dtypes(include=["object", "category"]).columns.tolist()
    for name in transformed_names:
        clean = name.split("__", 1)[-1]
        raw_features.append(next((col for col in categorical if clean.startswith(f"{col}_")), clean))

    explanation = shap.TreeExplainer(estimator)(transformed)
    values = explanation.values
    aggregated = np.column_stack([values[:, np.array(raw_features) == feature].sum(axis=1) for feature in x.columns])
    importance = pd.DataFrame({"feature": x.columns, "mean_abs_shap": np.abs(aggregated).mean(axis=0)}).sort_values("mean_abs_shap", ascending=False)
    importance["importance_share"] = importance["mean_abs_shap"] / importance["mean_abs_shap"].sum()
    importance.to_csv(TABLE_DIR / "feature_importance.csv", index=False)

    plot_data = sample.copy()
    for col in categorical:
        if col == "Range_Anxiety_Level":
            plot_data[col] = plot_data[col].map({"Low": 0, "Medium": 1, "High": 2})
        elif set(plot_data[col].unique()) <= {"No", "Yes"}:
            plot_data[col] = plot_data[col].map({"No": 0, "Yes": 1})
        else:
            plot_data[col] = plot_data[col].astype("category").cat.codes
    shap.summary_plot(aggregated, plot_data, show=False, max_display=15)
    plt.title("SHAP Summary: Final XGBoost Purchase Propensity Model")
    plt.tight_layout(); plt.savefig(FIGURE_DIR / "06_shap_summary.png", dpi=220, bbox_inches="tight"); plt.close()

    top = importance.head(12).sort_values("mean_abs_shap")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(top["feature"], top["mean_abs_shap"], color="#2A9D8F")
    ax.set(title="Top Drivers in the Final Model", xlabel="Mean |SHAP value|", ylabel="")
    fig.tight_layout(); fig.savefig(FIGURE_DIR / "05_feature_importance.png", dpi=220); plt.close(fig)

    direction = []
    for feature in importance.head(10).feature:
        feature_values = plot_data[feature].astype(float)
        direction.append({"feature": feature, "mean_abs_shap": importance.set_index("feature").loc[feature, "mean_abs_shap"], "direction_correlation": feature_values.corr(pd.Series(aggregated[:, x.columns.get_loc(feature)], index=sample.index))})
    pd.DataFrame(direction).to_csv(TABLE_DIR / "feature_direction.csv", index=False)
    return importance
