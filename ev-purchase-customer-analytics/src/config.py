from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "outputs"
AUDIT_DIR = OUTPUT_DIR / "audit"
TABLE_DIR = OUTPUT_DIR / "tables"
FIGURE_DIR = OUTPUT_DIR / "figures"
MODEL_DIR = OUTPUT_DIR / "models"
SUBMISSION_DIR = OUTPUT_DIR / "submissions"
DASHBOARD_DIR = OUTPUT_DIR / "dashboard"
REPORT_DIR = ROOT / "reports"
NOTEBOOK_DIR = ROOT / "notebooks"

TARGET = "Will_Buy_EV"
ID_COLUMN = "id"
RANDOM_STATE = 42
CV_SPLITS = 5
VALIDATION_SEEDS = (19, 42, 73, 101, 2026)
OPTUNA_TRIALS = 12
OPTUNA_SAMPLE_SIZE = 180_000


def ensure_directories() -> None:
    for path in (
        PROCESSED_DIR,
        AUDIT_DIR,
        TABLE_DIR,
        FIGURE_DIR,
        MODEL_DIR,
        SUBMISSION_DIR,
        DASHBOARD_DIR,
        REPORT_DIR,
        NOTEBOOK_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
