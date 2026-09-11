from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .loader import PreparedTables


def _python_metrics(tables: PreparedTables) -> dict[str, float]:
    features = tables.features
    segments = tables.segments
    train = features.loc[features.source_set.eq("train")]
    y = train.will_buy_ev.eq("Yes")
    merged = train.merge(segments[["id", "customer_segment", "high_potential_flag"]], on="id", validate="one_to_one")
    metrics = {
        "overall_purchase_rate": float(y.mean()),
        "high_potential_share": float(segments.high_potential_flag.mean()),
        "subsidy_yes_purchase_rate": float(y[train.subsidy_available.eq("Yes")].mean()),
        "subsidy_no_purchase_rate": float(y[train.subsidy_available.eq("No")].mean()),
        "home_charge_yes_purchase_rate": float(y[train.home_charging_possible.eq("Yes")].mean()),
        "home_charge_no_purchase_rate": float(y[train.home_charging_possible.eq("No")].mean()),
    }
    for segment, group in merged.groupby("customer_segment", observed=True):
        metrics[f"segment_count::{segment}"] = float(len(group))
        metrics[f"segment_purchase_rate::{segment}"] = float(group.will_buy_ev.eq("Yes").mean())
    return metrics


SQL_METRICS = """
SELECT 'overall_purchase_rate' metric, SUM(will_buy_ev='Yes') numerator, COUNT(*) denominator
FROM ev_customer_features WHERE source_set='train'
UNION ALL
SELECT 'high_potential_share', SUM(high_potential_flag=1), COUNT(*) FROM ev_customer_segments
UNION ALL
SELECT 'subsidy_yes_purchase_rate', SUM(will_buy_ev='Yes'), COUNT(*) FROM ev_customer_features WHERE source_set='train' AND subsidy_available='Yes'
UNION ALL
SELECT 'subsidy_no_purchase_rate', SUM(will_buy_ev='Yes'), COUNT(*) FROM ev_customer_features WHERE source_set='train' AND subsidy_available='No'
UNION ALL
SELECT 'home_charge_yes_purchase_rate', SUM(will_buy_ev='Yes'), COUNT(*) FROM ev_customer_features WHERE source_set='train' AND home_charging_possible='Yes'
UNION ALL
SELECT 'home_charge_no_purchase_rate', SUM(will_buy_ev='Yes'), COUNT(*) FROM ev_customer_features WHERE source_set='train' AND home_charging_possible='No'
UNION ALL
SELECT CONCAT('segment_count::', s.customer_segment), COUNT(*), 1
FROM ev_customer_segments s JOIN ev_customer_features f ON f.id=s.id
WHERE f.source_set='train' GROUP BY s.customer_segment
UNION ALL
SELECT CONCAT('segment_purchase_rate::', s.customer_segment), SUM(f.will_buy_ev='Yes'), COUNT(*)
FROM ev_customer_segments s JOIN ev_customer_features f ON f.id=s.id
WHERE f.source_set='train' GROUP BY s.customer_segment
"""


def reconcile_python_sql(engine: Engine, tables: PreparedTables, output_dir: Path, tolerance: float = 1e-10) -> pd.DataFrame:
    python_values = _python_metrics(tables)
    with engine.connect() as connection:
        sql_frame = pd.read_sql(text(SQL_METRICS), connection)
        sql_frame["metric_value"] = sql_frame["numerator"].astype(float) / sql_frame["denominator"].astype(float)
        sql_values = sql_frame.set_index("metric")["metric_value"].to_dict()
    rows = []
    for metric, python_value in python_values.items():
        sql_value = sql_values.get(metric)
        difference = abs(python_value - sql_value) if sql_value is not None else float("inf")
        rows.append(
            {
                "metric": metric,
                "python_value": python_value,
                "sql_value": sql_value,
                "absolute_difference": difference,
                "tolerance": tolerance,
                "status": "PASS" if difference <= tolerance else "FAIL",
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(output_dir / "13_python_sql_reconciliation.csv", index=False)
    if not result.status.eq("PASS").all():
        raise AssertionError("Python/MySQL reconciliation failed.")
    return result
