from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageStat

REQUIRED_FILES = (
    "README.md",
    "requirements.txt",
    "data/README.md",
    "src/train_and_predict.py",
    "src/house_prices_core.py",
    "src/create_figures.py",
    "results/submission_v3.csv",
    "results/v3_summary.json",
    "results/kaggle_rank_snapshot.csv",
    "results/kaggle_submission_history.csv",
    "results/reproducibility_check.json",
    "notebooks/final_results_walkthrough.ipynb",
    "report/项目复盘与实证分析.md",
    "report/模型原理通俗说明.md",
    "report/Ames房价预测_实证分析报告.docx",
    "report/Ames房价预测_实证分析报告.pdf",
)


def check_required_files(root: Path) -> list[str]:
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    if missing:
        raise AssertionError(f"Missing required files: {missing}")
    return [f"required_files={len(REQUIRED_FILES)}"]


def check_submission(root: Path) -> list[str]:
    submission = pd.read_csv(root / "results/submission_v3.csv")
    assert list(submission.columns) == ["Id", "SalePrice"]
    assert len(submission) == 1459
    assert submission["Id"].is_unique
    assert submission["Id"].is_monotonic_increasing
    prices = submission["SalePrice"].to_numpy(dtype=float)
    assert np.isfinite(prices).all() and (prices > 0).all()
    return [
        f"submission_rows={len(submission)}",
        f"prediction_range={prices.min():.2f}..{prices.max():.2f}",
    ]


def check_results(root: Path) -> list[str]:
    summary = json.loads((root / "results/v3_summary.json").read_text(encoding="utf-8"))
    assert summary["robust_crossfit_calibrated_rmse"] < 0.11
    assert abs(sum(summary["selected_weights"].values()) - 1.0) < 1e-9
    rank = pd.read_csv(root / "results/kaggle_rank_snapshot.csv").iloc[0]
    history = pd.read_csv(root / "results/kaggle_submission_history.csv")
    reproducibility = json.loads(
        (root / "results/reproducibility_check.json").read_text(encoding="utf-8")
    )
    assert float(rank["Score"]) == 0.12163
    assert int(rank["Rank"]) == 430
    assert set(history["Version"]) == {"V2", "V3"}
    assert reproducibility["status"] == "PASS"
    assert reproducibility["max_absolute_log_difference"] < 1e-6
    assert float(history.loc[history["Version"].eq("V3"), "PublicScore"].iloc[0]) < float(
        history.loc[history["Version"].eq("V2"), "PublicScore"].iloc[0]
    )
    return [
        "score_and_rank_evidence=PASS",
        "weights_sum=1.0",
        "full_retraining_reproducibility=PASS",
    ]


def check_figures(root: Path) -> list[str]:
    manifest = json.loads((root / "figures/chart_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 10
    for name in manifest:
        path = root / "figures" / name
        assert path.is_file()
        image = Image.open(path).convert("RGB")
        assert image.width >= 1200 and image.height >= 700
        assert max(ImageStat.Stat(image).stddev) > 10
    return [f"figures={len(manifest)}", "figure_pixels=PASS"]


def check_markdown_links(root: Path) -> list[str]:
    checked = 0
    for document in [root / "README.md", root / "report/项目复盘与实证分析.md"]:
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"!?(?:\[[^]]*\])\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            assert (document.parent / target).resolve().exists(), f"Broken link: {target}"
            checked += 1
    return [f"markdown_links={checked}"]


def check_code_and_notebook(root: Path) -> list[str]:
    source_files = sorted((root / "src").glob("*.py"))
    for path in source_files:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    notebook = json.loads(
        (root / "notebooks/final_results_walkthrough.ipynb").read_text(encoding="utf-8")
    )
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    errors = [
        output
        for cell in code_cells
        for output in cell.get("outputs", [])
        if output.get("output_type") == "error"
    ]
    assert code_cells and not errors
    assert all(cell.get("execution_count") is not None for cell in code_cells)
    return [f"python_files_compiled={len(source_files)}", "executed_notebook=PASS"]


def check_report_artifacts(root: Path) -> list[str]:
    docx = root / "report/Ames房价预测_实证分析报告.docx"
    pdf = root / "report/Ames房价预测_实证分析报告.pdf"
    assert docx.stat().st_size > 500_000
    assert pdf.stat().st_size > 500_000
    with zipfile.ZipFile(docx) as archive:
        names = set(archive.namelist())
        assert "word/document.xml" in names
        assert len([name for name in names if name.startswith("word/media/")]) >= 10
    assert pdf.read_bytes()[:5] == b"%PDF-"
    return ["docx_structure=PASS", "pdf_structure=PASS"]


def check_no_raw_competition_data(root: Path) -> list[str]:
    forbidden = {"train.csv", "test.csv", "sample_submission.csv"}
    found = [path for path in root.rglob("*.csv") if path.name in forbidden]
    assert not found, f"Raw competition files should not be bundled: {found}"
    return ["raw_competition_data=not_bundled"]


def run(root: Path) -> dict[str, object]:
    checks = []
    for check in (
        check_required_files,
        check_submission,
        check_results,
        check_figures,
        check_markdown_links,
        check_code_and_notebook,
        check_report_artifacts,
        check_no_raw_competition_data,
    ):
        checks.extend(check(root))
    result = {"status": "PASS", "project": root.name, "checks": checks}
    (root / "results/portfolio_qa.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Validate the portfolio package")
    parser.add_argument("--project-dir", type=Path, default=Path("."))
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    run(arguments.project_dir.resolve())
