from __future__ import annotations

import numpy as np
import pandas as pd

from config import DASHBOARD_DIR, FIGURE_DIR, TABLE_DIR, TARGET


def _target(frame: pd.DataFrame) -> pd.Series:
    return frame[TARGET].eq("Yes").astype(int)


def _segment_table(frame: pd.DataFrame, column: str, segment: pd.Series | None = None) -> pd.DataFrame:
    labels = frame[column].astype(str) if segment is None else segment.astype(str)
    y = _target(frame)
    overall = y.mean()
    out = pd.DataFrame({"segment_value": labels, "target": y}).groupby("segment_value", observed=True)["target"].agg(["size", "mean"]).reset_index()
    out.columns = ["segment_value", "customer_count", "purchase_rate"]
    out.insert(0, "segment_variable", column)
    out["difference_vs_overall"] = out["purchase_rate"] - overall
    return out


def create_eda_outputs(train: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    sns.set_theme(style="whitegrid", context="notebook")
    y = _target(train)
    numerical = ["Age", "Annual_Income_USD", "Daily_Commute_km", "Number_of_Cars_Owned"]
    categorical = ["Gender", "City_Type", "Current_Car_Type", "Home_Charging_Possible", "Subsidy_Available", "Range_Anxiety_Level"]
    rows = []
    for col in numerical:
        summary = train[col].describe(percentiles=[0.25, 0.5, 0.75]).to_dict()
        rows.append({"feature": col, **summary})
    pd.DataFrame(rows).to_csv(TABLE_DIR / "customer_profile.csv", index=False)

    segment_tables = []
    for col in categorical:
        segment_tables.append(_segment_table(train, col))
    for col in ["Age", "Annual_Income_USD", "Daily_Commute_km"]:
        bins = pd.qcut(train[col], q=5, duplicates="drop")
        segment_tables.append(_segment_table(train, f"{col}_quintile", bins))
    segment_result = pd.concat(segment_tables, ignore_index=True)
    segment_result.to_csv(TABLE_DIR / "purchase_rate_by_segment.csv", index=False)

    infra = []
    for col in ["Home_Charging_Possible", "Charging_Stations_Near_Home", "Charging_Stations_Near_Work"]:
        if train[col].nunique() > 5:
            bins = pd.qcut(train[col], q=5, duplicates="drop")
            infra.append(_segment_table(train, f"{col}_quintile", bins))
        else:
            infra.append(_segment_table(train, col))
    pd.concat(infra, ignore_index=True).to_csv(TABLE_DIR / "infrastructure_analysis.csv", index=False)

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    counts = train[TARGET].value_counts().reindex(["No", "Yes"])
    sns.barplot(x=counts.index, y=counts.values, hue=counts.index, legend=False, palette=["#4C78A8", "#F58518"], ax=ax)
    ax.set(title="EV Purchase Intent Is Imbalanced", xlabel="Will buy EV", ylabel="Customers")
    for i, value in enumerate(counts.values):
        ax.text(i, value, f"{value:,}\n({value / len(train):.1%})", ha="center", va="bottom")
    fig.tight_layout(); fig.savefig(FIGURE_DIR / "01_target_balance.png", dpi=220); plt.close(fig)

    selected = segment_result[segment_result["segment_variable"].isin(["City_Type", "Subsidy_Available", "Home_Charging_Possible", "Range_Anxiety_Level"])]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (name, group) in zip(axes.flat, selected.groupby("segment_variable", sort=False)):
        orders = {
            "City_Type": ["Urban", "Suburban", "Rural"],
            "Subsidy_Available": ["No", "Yes"],
            "Home_Charging_Possible": ["No", "Yes"],
            "Range_Anxiety_Level": ["Low", "Medium", "High"],
        }
        group = group.set_index("segment_value").reindex(orders[name]).reset_index()
        sns.barplot(data=group, x="segment_value", y="purchase_rate", color="#2A9D8F", ax=ax)
        ax.axhline(y.mean(), color="#E76F51", linestyle="--", linewidth=1.5, label="Overall")
        ax.set(title=name.replace("_", " "), xlabel="", ylabel="Purchase rate")
        ax.tick_params(axis="x", rotation=20)
    fig.suptitle("Purchase Rate Across Actionable Customer Attributes", fontsize=15)
    fig.tight_layout(); fig.savefig(FIGURE_DIR / "02_actionable_segment_rates.png", dpi=220); plt.close(fig)

    continuous = segment_result[segment_result["segment_variable"].str.endswith("_quintile")]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, (name, group) in zip(axes, continuous.groupby("segment_variable", sort=False)):
        sns.lineplot(data=group, x="segment_value", y="purchase_rate", marker="o", color="#4C78A8", ax=ax)
        ax.axhline(y.mean(), color="#E76F51", linestyle="--", linewidth=1.2)
        ax.set(title=name.replace("_quintile", "").replace("_", " "), xlabel="Quantile bin", ylabel="Purchase rate")
        ax.tick_params(axis="x", rotation=30)
    fig.suptitle("Purchase Intent by Customer Quantiles", fontsize=15)
    fig.tight_layout(); fig.savefig(FIGURE_DIR / "03_numeric_quintile_rates.png", dpi=220); plt.close(fig)


def assign_segments(frame: pd.DataFrame, prediction: np.ndarray, reference: pd.DataFrame | None = None) -> pd.Series:
    ref = reference if reference is not None else frame.assign(prediction=prediction)
    pred_ref = ref["prediction"] if "prediction" in ref else pd.Series(prediction)
    q30, q35, q50, q80 = pred_ref.quantile([0.30, 0.35, 0.50, 0.80])
    income_q40 = ref["Annual_Income_USD"].quantile(0.40)
    nearby_stations = frame["Charging_Stations_Near_Home"] + frame["Charging_Stations_Near_Work"]
    stations_q25 = (ref["Charging_Stations_Near_Home"] + ref["Charging_Stations_Near_Work"]).quantile(0.25)
    conditions = [
        prediction >= q80,
        (prediction >= q50) & frame["Home_Charging_Possible"].eq("No") & (nearby_stations <= stations_q25),
        (prediction >= q50) & frame["Environmental_Concern_Level"].ge(4),
        (prediction >= q35) & frame["Subsidy_Available"].eq("Yes") & frame["Annual_Income_USD"].le(income_q40),
        prediction <= q30,
    ]
    choices = ["High Potential", "Infrastructure-Constrained", "Eco-Motivated", "Price-Sensitive", "Low Propensity"]
    return pd.Series(np.select(conditions, choices, default="Moderate Potential"), index=frame.index, name="customer_segment")


def create_business_outputs(train: pd.DataFrame, test: pd.DataFrame, oof: np.ndarray, test_pred: np.ndarray, feature_driver: pd.DataFrame) -> pd.DataFrame:
    train_scored = train.copy()
    train_scored["actual_purchase"] = _target(train)
    train_scored["prediction"] = oof
    train_scored["customer_segment"] = assign_segments(train_scored, oof)
    reference = train_scored
    test_scored = test.copy()
    test_scored["prediction"] = test_pred
    test_scored["customer_segment"] = assign_segments(test_scored, test_pred, reference)

    segment_summary = train_scored.groupby("customer_segment", observed=True).agg(
        customer_count=("id", "size"),
        predicted_purchase_probability=("prediction", "mean"),
        actual_purchase_rate=("actual_purchase", "mean"),
        average_income=("Annual_Income_USD", "mean"),
        average_environmental_concern=("Environmental_Concern_Level", "mean"),
        average_commute_km=("Daily_Commute_km", "mean"),
        home_charging_share=("Home_Charging_Possible", lambda s: s.eq("Yes").mean()),
        subsidy_share=("Subsidy_Available", lambda s: s.eq("Yes").mean()),
    ).reset_index()
    segment_summary["customer_share"] = segment_summary["customer_count"] / len(train_scored)
    segment_summary = segment_summary.sort_values("predicted_purchase_probability", ascending=False)
    segment_summary.to_csv(TABLE_DIR / "customer_segments.csv", index=False)

    export = train_scored.drop(columns=["actual_purchase"]).rename(
        columns={
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
            "prediction": "predicted_probability",
        }
    )
    export.to_csv(DASHBOARD_DIR / "customer_overview.csv", index=False)
    segment_summary.to_csv(DASHBOARD_DIR / "segment_analysis.csv", index=False)
    feature_driver.to_csv(DASHBOARD_DIR / "feature_driver.csv", index=False)
    test_scored.rename(columns={"prediction": "predicted_probability"}).to_csv(DASHBOARD_DIR / "purchase_propensity.csv", index=False)
    return segment_summary
