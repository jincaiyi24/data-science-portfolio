"""Offline parallel re-scoring pipeline using the audited Korean v2 classifier.

No DART calls are made. The script reads the existing 1,980-row Korean panel
and cached annual-report text, then writes new v2 workbooks without overwriting
the baseline files.
"""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

import korea_digital_strategy_korean_pipeline as baseline
from ssci_korean_classifier_v2 import classify_sentence_v2


SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR / "korea_digital_strategy_output"
INPUT_PANEL = OUT_DIR / "04_digital_strategy_panel_korean.xlsx"
OUTPUT_PANEL = OUT_DIR / "04_digital_strategy_panel_korean_v2.xlsx"
OUTPUT_SENTENCES = OUT_DIR / "05_representative_digital_sentences_korean_v2.xlsx"
CLASSIFIER_VERSION = "korean_contextual_v2_ai_audit_2026-08-11"

COUNT_COLUMNS = [
    "digital_sentence_count",
    "substantive_digital_sentence_count",
    "bmi_sentence_count",
    "market_signal_sentence_count",
    "boilerplate_digital_sentence_count",
]

EXAMPLE_COLUMNS = [
    "corp_code",
    "corp_name",
    "corp_name_eng",
    "stock_code",
    "year",
    "rcept_no",
    "report_name",
    "sentence_rank",
    "sentence_id",
    "priority",
    "sentence",
    "digital_sentence",
    "substantive_digital_sentence",
    "bmi_sentence",
    "market_signal_sentence",
    "boilerplate_digital_sentence",
    "digital_core_terms_ko",
    "contextual_digital_terms_ko",
    "action_terms_ko",
    "bmi_terms_ko",
    "operational_terms_ko",
    "v2_accounting_noise",
    "v2_name_collision",
    "v2_stale_history",
    "v2_business_purpose",
    "v2_generic_context",
    "v2_specific_plan",
    "v2_external_company_context",
    "classifier_version",
]


def term_hits(sentence: str) -> Dict[str, str]:
    return {
        "digital_core_terms_ko": "; ".join(
            baseline.match_terms(sentence, baseline.DIGITAL_CORE_PATTERNS)
        ),
        "contextual_digital_terms_ko": "; ".join(
            baseline.match_terms(sentence, baseline.CONTEXTUAL_DIGITAL_PATTERNS)
        ),
        "action_terms_ko": "; ".join(
            baseline.match_terms(sentence, baseline.ACTION_PATTERNS)
        ),
        "bmi_terms_ko": "; ".join(
            baseline.match_terms(sentence, baseline.BMI_PATTERNS)
        ),
        "operational_terms_ko": "; ".join(
            baseline.match_terms(sentence, baseline.OPERATIONAL_PATTERNS)
        ),
    }


def score_one(task: Dict[str, Any]) -> Tuple[int, Dict[str, Any], List[Dict[str, Any]]]:
    index = int(task.pop("_row_index"))
    report_year = int(task["year"])
    text_path = Path(str(task["text_cache_path"]))
    counts = {name: 0 for name in COUNT_COLUMNS}
    examples: List[Dict[str, Any]] = []

    if not text_path.exists():
        return index, {**counts, "v2_rescore_status": "missing_cache"}, examples

    try:
        text = text_path.read_text(encoding="utf-8", errors="replace")
        raw_sentences = baseline.split_korean_sentences(text)
        seen: set[str] = set()
        sentences: List[str] = []
        for sentence in raw_sentences:
            key = "".join(sentence.lower().split())
            if key in seen:
                continue
            seen.add(key)
            sentences.append(sentence)
    except Exception as exc:  # pragma: no cover - defensive batch behavior.
        return index, {
            **counts,
            "v2_rescore_status": "error",
            "v2_rescore_error": str(exc),
        }, examples

    for sentence_id, sentence in enumerate(sentences, start=1):
        labels = classify_sentence_v2(sentence, report_year, str(task.get("corp_name") or ""))
        digital = labels["digital_sentence_v2"]
        substantive = labels["substantive_digital_sentence_v2"]
        bmi = labels["bmi_sentence_v2"]
        market = labels["market_signal_sentence_v2"]
        boilerplate = labels["boilerplate_digital_sentence_v2"]
        counts["digital_sentence_count"] += digital
        counts["substantive_digital_sentence_count"] += substantive
        counts["bmi_sentence_count"] += bmi
        counts["market_signal_sentence_count"] += market
        counts["boilerplate_digital_sentence_count"] += boilerplate

        if digital:
            priority = substantive * 100 + bmi * 30 + market * 10 - boilerplate * 50
            examples.append(
                {
                    **{key: task.get(key) for key in [
                        "corp_code", "corp_name", "corp_name_eng", "stock_code",
                        "year", "rcept_no", "report_name"
                    ]},
                    "sentence_id": sentence_id,
                    "priority": priority,
                    "sentence": sentence[:3000],
                    "digital_sentence": digital,
                    "substantive_digital_sentence": substantive,
                    "bmi_sentence": bmi,
                    "market_signal_sentence": market,
                    "boilerplate_digital_sentence": boilerplate,
                    **term_hits(sentence),
                    **{key: labels[key] for key in [
                        "v2_accounting_noise", "v2_name_collision", "v2_stale_history",
                        "v2_business_purpose", "v2_generic_context", "v2_specific_plan",
                        "v2_external_company_context"
                    ]},
                    "classifier_version": CLASSIFIER_VERSION,
                }
            )

    examples.sort(key=lambda row: (-row["priority"], row["sentence_id"]))
    examples = examples[:20]
    for rank, example in enumerate(examples, start=1):
        example["sentence_rank"] = rank

    return index, {
        **counts,
        "v2_analyzable_sentence_count": len(sentences),
        "v2_rescore_status": "ok",
        "v2_rescore_error": "",
    }, examples


def add_scores(panel: pd.DataFrame) -> pd.DataFrame:
    result = panel.copy()
    denominator = pd.to_numeric(
        result["v2_analyzable_sentence_count"], errors="coerce"
    ).fillna(0)
    valid_report = result["v2_rescore_status"].eq("ok") & denominator.gt(0)
    safe = denominator.where(valid_report)
    result["DigitalStrategy"] = (
        pd.to_numeric(result["substantive_digital_sentence_count"], errors="coerce").fillna(0)
        / safe
    )
    result["BMI_Reconstruction"] = (
        pd.to_numeric(result["bmi_sentence_count"], errors="coerce").fillna(0) / safe
    )
    result["MarketSignalDisclosure"] = (
        pd.to_numeric(result["market_signal_sentence_count"], errors="coerce").fillna(0)
        / safe
    )
    result["BoilerplateDisclosure"] = (
        pd.to_numeric(result["boilerplate_digital_sentence_count"], errors="coerce").fillna(0)
        / safe
    )
    result["SignalSubstanceGap"] = (
        result["MarketSignalDisclosure"] - result["DigitalStrategy"]
    )

    result["year"] = pd.to_numeric(result["year"], errors="coerce").astype("Int64")
    result["YearMean_DigitalStrategy"] = result.groupby("year")["DigitalStrategy"].transform("mean")
    if "industry_group" in result.columns and result["industry_group"].notna().any():
        result["IndustryYearMean_DigitalStrategy"] = result.groupby(
            ["industry_group", "year"], dropna=False
        )["DigitalStrategy"].transform("mean")
        result["RelativeDigitalSignal_IndustryYear"] = (
            result["DigitalStrategy"] - result["IndustryYearMean_DigitalStrategy"]
        )
        result["RelativeDigitalSignal"] = result["RelativeDigitalSignal_IndustryYear"]
        result["relative_signal_reference"] = "industry_year"
    else:
        result["IndustryYearMean_DigitalStrategy"] = pd.NA
        result["RelativeDigitalSignal_IndustryYear"] = pd.NA
        result["RelativeDigitalSignal"] = (
            result["DigitalStrategy"] - result["YearMean_DigitalStrategy"]
        )
        result["relative_signal_reference"] = "year"
    result["RelativeDigitalSignal_YearOnly"] = (
        result["DigitalStrategy"] - result["YearMean_DigitalStrategy"]
    )
    result["classifier_version"] = CLASSIFIER_VERSION
    return result


def run(workers: int) -> None:
    panel = pd.read_excel(
        INPUT_PANEL,
        dtype={"corp_code": str, "stock_code": str, "rcept_no": str},
    )
    tasks: List[Dict[str, Any]] = []
    metadata_keys = [
        "corp_code", "corp_name", "corp_name_eng", "stock_code", "year",
        "rcept_no", "report_name", "text_cache_path"
    ]
    for index, row in panel.iterrows():
        task = {key: row.get(key) for key in metadata_keys}
        task["_row_index"] = int(index)
        tasks.append(task)

    updates: Dict[int, Dict[str, Any]] = {}
    all_examples: List[Dict[str, Any]] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(score_one, task.copy()) for task in tasks]
        for future in as_completed(futures):
            index, scores, examples = future.result()
            updates[index] = scores
            all_examples.extend(examples)
            completed += 1
            if completed % 100 == 0 or completed == len(tasks):
                print(f"Rescored {completed:,}/{len(tasks):,}", flush=True)

    update_df = pd.DataFrame.from_dict(updates, orient="index")
    for column in update_df.columns:
        panel[column] = update_df[column]
    panel["total_sentences"] = panel["v2_analyzable_sentence_count"].fillna(
        panel["total_sentences"]
    )
    panel["analyzable_korean_sentence_count"] = panel["total_sentences"]
    panel = add_scores(panel)

    examples = pd.DataFrame(all_examples)
    if examples.empty:
        examples = pd.DataFrame(columns=EXAMPLE_COLUMNS)
    else:
        examples = examples[[col for col in EXAMPLE_COLUMNS if col in examples.columns]]
        examples = examples.sort_values(
            ["corp_code", "year", "sentence_rank"], ignore_index=True
        )

    panel.to_excel(OUTPUT_PANEL, index=False)
    examples.to_excel(OUTPUT_SENTENCES, index=False)
    print(f"Panel: {OUTPUT_PANEL}")
    print(f"Representative sentences: {OUTPUT_SENTENCES}")
    print(f"Panel rows: {len(panel):,}; sentence rows: {len(examples):,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    default_workers = max(1, min(4, (os.cpu_count() or 2) - 1))
    parser.add_argument("--workers", type=int, default=default_workers)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(max(1, args.workers))
