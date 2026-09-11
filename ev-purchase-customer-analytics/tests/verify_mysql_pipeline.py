from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mysql.connection import create_database_engine, load_settings
from mysql.query_runner import EXPORTS, all_named_queries


def main() -> None:
    required = [
        "scripts/run_mysql_pipeline.py",
        ".env.example",
        "docs/sql/SQL_PROJECT_MASTER_GUIDE_CN.md",
        "docs/sql/index_design.md",
        "docs/sql/mysql_execution_report.md",
        "docs/interview/EV_SQL_INTERVIEW_CN.md",
        "docs/interview/EV_SQL_CODING_QUESTIONS_CN.md",
        "docs/interview/EV_SQL_PROJECT_PITCH_CN.md",
    ] + [f"sql/{i:02d}_{name}.sql" for i, name in enumerate([
        "create_database", "schema", "data_quality", "customer_profile", "purchase_propensity",
        "segment_analysis", "join_analysis", "window_functions", "ranking_decile",
        "model_validation", "business_kpi", "business_case_analysis", "interview_queries",
    ])]
    missing = [path for path in required if not (ROOT / path).exists()]
    assert not missing, f"Missing MySQL deliverables: {missing}"

    queries = all_named_queries(ROOT / "sql")
    assert set(EXPORTS).issubset(queries), "Named SQL export is missing"
    for filename in EXPORTS.values():
        assert (ROOT / "outputs/sql" / filename).exists(), f"Missing SQL export: {filename}"

    validation = pd.read_csv(ROOT / "outputs/sql/mysql_validation.csv")
    reconciliation = pd.read_csv(ROOT / "outputs/sql/13_python_sql_reconciliation.csv")
    query_log = pd.read_csv(ROOT / "outputs/sql/mysql_query_log.csv")
    assert len(validation) == 13 and validation.status.eq("PASS").all()
    assert len(reconciliation) == 18 and reconciliation.status.eq("PASS").all()
    assert reconciliation.absolute_difference.max() == 0
    assert len(query_log) == 13 and query_log.status.eq("PASS").all()

    guide = (ROOT / "docs/sql/SQL_PROJECT_MASTER_GUIDE_CN.md").read_text(encoding="utf-8")
    interview = (ROOT / "docs/interview/EV_SQL_INTERVIEW_CN.md").read_text(encoding="utf-8")
    coding = (ROOT / "docs/interview/EV_SQL_CODING_QUESTIONS_CN.md").read_text(encoding="utf-8")
    assert len(re.findall(r"^## 第 \d+ 章", guide, re.MULTILINE)) == 25
    assert len(re.findall(r"^## \d+\.", interview, re.MULTILINE)) >= 50
    assert len(re.findall(r"^## \d+\.", coding, re.MULTILINE)) >= 30

    engine = create_database_engine(load_settings())
    try:
        with engine.connect() as connection:
            counts = dict(connection.execute(text("""
                SELECT 'features', COUNT(*) FROM ev_customer_features
                UNION ALL SELECT 'predictions', COUNT(*) FROM ev_model_predictions
                UNION ALL SELECT 'segments', COUNT(*) FROM ev_customer_segments
                UNION ALL SELECT 'metrics', COUNT(*) FROM ev_model_metrics
            """)).all())
    finally:
        engine.dispose()
    assert counts == {"features": 955236, "predictions": 955236, "segments": 955236, "metrics": 55}

    scan_files = [
        *ROOT.glob("*.md"), *ROOT.glob("*.txt"), *ROOT.glob("*.example"),
        *ROOT.glob("src/**/*.py"), *ROOT.glob("scripts/**/*.py"), *ROOT.glob("sql/*.sql"),
        *ROOT.glob("docs/**/*.md"), *ROOT.glob("reports/*.md"), *ROOT.glob("tests/*.py"),
    ]
    forbidden = [
        re.compile(r"^MYSQL_PASSWORD=(?!replace_with_local_password)\S+", re.MULTILINE),
        re.compile(r"[A-Za-z]:\\Users\\"),
    ]
    hits = []
    for path in scan_files:
        content = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(content) for pattern in forbidden):
            hits.append(str(path.relative_to(ROOT)))
    assert not hits, f"Sensitive/local content found: {hits}"
    print("MYSQL QA PASS: 4 tables, 13 checks, 13 exports, 18 reconciliations, 25/50/30 learning assets")


if __name__ == "__main__":
    main()
