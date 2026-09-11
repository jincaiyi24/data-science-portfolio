from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .loader import PreparedTables


def validate_database(engine: Engine, expected: PreparedTables, output_dir: Path) -> pd.DataFrame:
    checks = [
        ("feature_row_count", "SELECT COUNT(*) FROM ev_customer_features", len(expected.features), "equal"),
        ("prediction_row_count", "SELECT COUNT(*) FROM ev_model_predictions", len(expected.predictions), "equal"),
        ("segment_row_count", "SELECT COUNT(*) FROM ev_customer_segments", len(expected.segments), "equal"),
        ("metric_row_count", "SELECT COUNT(*) FROM ev_model_metrics", len(expected.metrics), "equal"),
        ("feature_duplicate_ids", "SELECT COUNT(*)-COUNT(DISTINCT id) FROM ev_customer_features", 0, "equal"),
        ("prediction_duplicate_ids", "SELECT COUNT(*)-COUNT(DISTINCT id) FROM ev_model_predictions", 0, "equal"),
        ("segment_duplicate_ids", "SELECT COUNT(*)-COUNT(DISTINCT id) FROM ev_customer_segments", 0, "equal"),
        ("train_target_nulls", "SELECT COUNT(*) FROM ev_customer_features WHERE source_set='train' AND will_buy_ev IS NULL", 0, "equal"),
        ("test_target_non_nulls", "SELECT COUNT(*) FROM ev_customer_features WHERE source_set='test' AND will_buy_ev IS NOT NULL", 0, "equal"),
        ("prediction_nulls", "SELECT COUNT(*) FROM ev_model_predictions WHERE predicted_probability IS NULL", 0, "equal"),
        ("prediction_out_of_range", "SELECT COUNT(*) FROM ev_model_predictions WHERE predicted_probability NOT BETWEEN 0 AND 1", 0, "equal"),
        ("missing_prediction_joins", "SELECT COUNT(*) FROM ev_customer_features f LEFT JOIN ev_model_predictions p ON p.id=f.id WHERE p.id IS NULL", 0, "equal"),
        ("missing_segment_joins", "SELECT COUNT(*) FROM ev_customer_features f LEFT JOIN ev_customer_segments s ON s.id=f.id WHERE s.id IS NULL", 0, "equal"),
    ]
    rows = []
    with engine.connect() as connection:
        for check, sql, expected_value, rule in checks:
            actual = connection.execute(text(sql)).scalar_one()
            passed = actual == expected_value if rule == "equal" else False
            rows.append({"check": check, "expected": expected_value, "actual": actual, "status": "PASS" if passed else "FAIL"})
    result = pd.DataFrame(rows)
    result.to_csv(output_dir / "mysql_validation.csv", index=False)
    summary = [
        "# MySQL Pipeline Validation",
        "",
        f"- Checks passed: {(result.status == 'PASS').sum()}/{len(result)}",
        f"- Overall status: {'PASS' if result.status.eq('PASS').all() else 'FAIL'}",
        "",
        result.to_markdown(index=False),
        "",
    ]
    (output_dir / "mysql_validation_report.md").write_text("\n".join(summary), encoding="utf-8")
    if not result.status.eq("PASS").all():
        failed = result.loc[result.status.eq("FAIL"), "check"].tolist()
        raise AssertionError(f"MySQL validation failed: {failed}")
    return result
