from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path


FORBIDDEN_PARTS = {
    "data/raw",
    "data/processed",
    "data/external",
    "outputs/models",
    "outputs/submissions",
    "outputs/research",
    "outputs/audit/current_leaderboard",
}
FORBIDDEN_NAMES = {
    "train.csv",
    "test.csv",
    "sample_submission.csv",
    "submission.csv",
    "submission_final.csv",
    "leaderboard.csv",
    "customer_overview.csv",
    "purchase_propensity.csv",
    "kaggle.json",
}
FORBIDDEN_SUFFIXES = {".joblib", ".cbm", ".pyc", ".pkl"}
TEXT_SUFFIXES = {".md", ".py", ".sql", ".json", ".txt", ".toml", ".yml", ".yaml"}
SECRET_PATTERNS = {
    "absolute Windows user path": re.compile(r"[A-Za-z]:\\Users\\", re.I),
    "Kaggle credential assignment": re.compile(r"KAGGLE_(?:KEY|USERNAME)\s*=", re.I),
    "MySQL password assignment": re.compile(r"^MYSQL_PASSWORD\s*=\s*(?!replace_with_local_password)[^\s#]+", re.I | re.M),
    "hard-coded account identifier": re.compile(
        r"(?:account|username|user_name)\s*[:=]\s*[\"'][^\"']+[\"']", re.I
    ),
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH )?PRIVATE KEY", re.I),
}


def normalized(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def inspect_directory(root: Path) -> list[str]:
    errors: list[str] = []
    files = [path for path in root.rglob("*") if path.is_file()]

    for path in files:
        rel = normalized(path, root)
        rel_lower = rel.lower()
        if any(rel_lower == part or rel_lower.startswith(part + "/") for part in FORBIDDEN_PARTS):
            errors.append(f"forbidden path: {rel}")
        if path.name.lower() in FORBIDDEN_NAMES:
            errors.append(f"forbidden file: {rel}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden artifact: {rel}")

        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    errors.append(f"{label}: {rel}")

        if path.suffix.lower() == ".ipynb":
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for index, cell in enumerate(notebook.get("cells", []), start=1):
                if cell.get("cell_type") != "code":
                    continue
                if cell.get("outputs"):
                    errors.append(f"notebook output remains: {rel} cell {index}")
                if cell.get("execution_count") is not None:
                    errors.append(f"execution count remains: {rel} cell {index}")

    required = ["README.md", ".gitignore", ".env.example", "PUBLICATION_NOTICE.md", "LICENSE"]
    errors.extend(f"missing required file: {name}" for name in required if not (root / name).exists())
    return errors


def inspect_zip(path: Path) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = [name.replace("\\", "/").lower() for name in archive.namelist()]
    for name in names:
        parts = name.split("/", 1)
        rel = parts[1] if len(parts) == 2 else parts[0]
        if any(rel == part or rel.startswith(part + "/") for part in FORBIDDEN_PARTS):
            errors.append(f"forbidden path in zip: {name}")
        if Path(rel).name in FORBIDDEN_NAMES:
            errors.append(f"forbidden file in zip: {name}")
        if Path(rel).suffix in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden artifact in zip: {name}")
    return errors


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors = inspect_zip(target) if target.suffix.lower() == ".zip" else inspect_directory(target)
    if errors:
        print("PUBLICATION SAFETY CHECK FAILED")
        for error in sorted(set(errors)):
            print(f"- {error}")
        raise SystemExit(1)
    print(f"PUBLICATION SAFETY CHECK PASSED: {target}")


if __name__ == "__main__":
    main()
