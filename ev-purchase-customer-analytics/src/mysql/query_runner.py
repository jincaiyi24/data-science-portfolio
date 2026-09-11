from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


NAME_PATTERN = re.compile(r"^\s*--\s*name:\s*([a-z0-9_]+)\s*$", re.IGNORECASE | re.MULTILINE)

EXPORTS = {
    "data_quality": "01_data_quality.csv",
    "customer_profile": "02_customer_profile.csv",
    "purchase_propensity": "03_purchase_propensity.csv",
    "segment_analysis": "04_segment_analysis.csv",
    "join_coverage": "05_join_coverage.csv",
    "city_segment_ranking": "06_city_segment_ranking.csv",
    "income_segment_ranking": "07_income_segment_ranking.csv",
    "prediction_deciles": "08_prediction_deciles.csv",
    "top_decile_profile": "09_top_decile_profile.csv",
    "model_vs_actual": "10_model_vs_actual.csv",
    "model_validation": "11_model_validation.csv",
    "business_kpi": "12_business_kpi.csv",
    "business_case_analysis": "business_case_analysis.csv",
}


def parse_named_queries(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    matches = list(NAME_PATTERN.finditer(content))
    queries: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        query = content[match.end():end].strip().rstrip(";").strip()
        if query:
            queries[match.group(1).lower()] = query
    return queries


def all_named_queries(sql_dir: Path) -> dict[str, str]:
    queries: dict[str, str] = {}
    for path in sorted(sql_dir.glob("*.sql")):
        if path.name.startswith(("00_", "01_", "12_")):
            continue
        queries.update(parse_named_queries(path))
    return queries


def run_exports(engine: Engine, sql_dir: Path, output_dir: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    queries = all_named_queries(sql_dir)
    missing = sorted(set(EXPORTS) - set(queries))
    if missing:
        raise KeyError(f"Named SQL exports are missing: {missing}")
    logs = []
    with engine.connect() as connection:
        for name, filename in EXPORTS.items():
            started = time.perf_counter()
            frame = pd.read_sql(text(queries[name]), connection)
            frame.to_csv(output_dir / filename, index=False)
            logs.append(
                {
                    "query_name": name,
                    "output_file": filename,
                    "rows_exported": len(frame),
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "status": "PASS",
                }
            )
    log = pd.DataFrame(logs)
    log.to_csv(output_dir / "mysql_query_log.csv", index=False)
    return log


def write_performance_report(engine: Engine, sql_dir: Path, output_dir: Path) -> None:
    queries = all_named_queries(sql_dir)
    selected = ["purchase_propensity", "segment_analysis", "city_segment_ranking"]
    sections = ["# MySQL Query Performance", "", "Generated with MySQL `EXPLAIN` on the live project tables.", ""]
    with engine.connect() as connection:
        for name in selected:
            explain = pd.read_sql(text(f"EXPLAIN {queries[name]}"), connection)
            sections.extend([f"## {name}", "", explain.to_markdown(index=False), ""])
    sections.extend(
        [
            "## Index interpretation",
            "",
            "- Customer slicing uses indexes on city, subsidy, source set and segment.",
            "- Propensity ranking uses the prediction probability/decile index; window queries may still sort because ranking requires an ordered result.",
            "- Foreign-key joins use primary-key lookups on `id`, so join coverage checks avoid full Cartesian work.",
            "- Low-cardinality indexes help filtered reporting but are not expected to replace scans for full-population aggregates.",
            "",
        ]
    )
    (output_dir / "query_performance_report.md").write_text("\n".join(sections), encoding="utf-8")
