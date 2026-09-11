from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mysql.connection import create_database_engine, ensure_database, load_settings
from mysql.exporter import reconcile_python_sql
from mysql.loader import load_tables, prepare_tables
from mysql.query_runner import run_exports, write_performance_report
from mysql.schema import create_schema
from mysql.validator import validate_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load and validate the EV analytics MySQL project.")
    parser.add_argument("--database", help="Override MYSQL_DATABASE for this run.")
    parser.add_argument("--chunk-size", type=int, default=5_000)
    parser.add_argument("--skip-load", action="store_true", help="Reuse data already loaded in MySQL.")
    parser.add_argument("--skip-queries", action="store_true", help="Skip analytical CSV exports.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = ROOT / "outputs/sql"
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = load_settings(args.database)
    print(f"Connecting to {settings.masked_summary()}")
    ensure_database(settings)
    engine = create_database_engine(settings)
    try:
        create_schema(engine, ROOT / "sql")
        tables = prepare_tables(ROOT)
        if not args.skip_load:
            load_log = load_tables(engine, tables, output_dir, args.chunk_size)
            print(load_log[["table", "rows_loaded", "status"]].to_string(index=False))
        validation = validate_database(engine, tables, output_dir)
        print(f"Validation: {validation.status.eq('PASS').sum()}/{len(validation)} checks passed")
        if not args.skip_queries:
            query_log = run_exports(engine, ROOT / "sql", output_dir)
            print(f"Exports: {len(query_log)} queries completed")
        reconciliation = reconcile_python_sql(engine, tables, output_dir)
        print(f"Reconciliation: {reconciliation.status.eq('PASS').sum()}/{len(reconciliation)} metrics matched")
        write_performance_report(engine, ROOT / "sql", output_dir)
        print(f"MySQL pipeline complete. Outputs: {output_dir}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
