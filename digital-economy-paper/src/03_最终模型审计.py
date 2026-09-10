from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs" / "ssci_empirical_completion_20260816"
OPTIMIZED = ROOT / "outputs" / "model_optimization_20260816"
FINAL = ROOT / "outputs" / "韩国数字化战略论文_正式版_20260816"
RESULT_OUT = FINAL / "02_模型与结果"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_optimizer():
    path = ROOT / "work" / "ssci_empirical_completion" / "08_optimize_models.py"
    spec = importlib.util.spec_from_file_location("optimizer", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    RESULT_OUT.mkdir(parents=True, exist_ok=True)
    optimizer = load_optimizer()
    panel = optimizer.add_derived_variables()
    lag = pd.to_numeric(panel["correction_lag_days"], errors="coerce")
    samples = [
        ("TEMPORAL_FULL", panel, "完整样本"),
        ("TEMPORAL_NO_CORRECTION", panel.loc[lag.eq(0)], "仅未更正年报"),
        ("TEMPORAL_LAG_LE90", panel.loc[lag.le(90)], "文本更正滞后不超过90天"),
        ("TEMPORAL_LAG_LE275", panel.loc[lag.le(275)], "文本更正滞后不超过275天"),
    ]
    results: list[dict[str, Any]] = []
    for sample_id, sample, note in samples:
        for outcome in ["SalesGrowth_w_t1", "ROA_AvgAssets_w_t1", "OperatingMargin_w_t1"]:
            rows, _, _ = optimizer.fit_panel(
                sample,
                f"{sample_id}_{outcome}",
                "operating_temporal_audit",
                "robustness",
                note,
                outcome,
                ["Digital_z"],
                optimizer.CORE_CONTROLS,
                effect_spec="firm_year",
                covariance="firm",
                sample_note=note,
            )
            results.extend(rows)
    frame = pd.DataFrame(results)
    ok = frame["status"].eq("ok")
    frame.loc[ok, "fdr_temporal_family"] = optimizer.bh_adjust(frame.loc[ok, "p_value"])
    frame.to_csv(RESULT_OUT / "05_文本时间边界稳健性.csv", index=False, encoding="utf-8-sig")

    operating = pd.read_csv(OPTIMIZED / "05_operating_model_optimization.csv")
    car = pd.read_csv(OPTIMIZED / "06_car_model_optimization.csv")
    joint = pd.read_csv(OPTIMIZED / "07_joint_nonlinearity_and_hurdle_tests.csv")
    preferred = car.loc[
        car["model_id"].eq("CAR_EVENT_DATE_FE_TWO_WAY")
        & car["focal"].eq("Digital_z")
        & car["status"].eq("ok")
    ].iloc[0]
    lagged = car.loc[
        car["model_id"].eq("CAR_EVENT_DATE_FE_LAGGED_CONTROLS")
        & car["focal"].eq("Digital_z")
        & car["status"].eq("ok")
    ].iloc[0]
    placebo = car.loc[
        car["model_id"].eq("CAR_PLACEBO_LEAD_LEVEL")
        & car["focal"].eq("Digital_lead1_z")
        & car["status"].eq("ok")
    ].iloc[0]
    audit = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "panel_rows": int(len(panel)),
        "firms": int(panel["corp_code"].nunique()),
        "duplicate_firm_years": int(panel.duplicated(["corp_code", "year"]).sum()),
        "year_min": int(panel["year"].min()),
        "year_max": int(panel["year"].max()),
        "correction_lag_over_90_rows": int(lag.gt(90).sum()),
        "correction_lag_over_90_share": float(lag.gt(90).mean()),
        "correction_lag_over_275_rows": int(lag.gt(275).sum()),
        "correction_lag_over_275_share": float(lag.gt(275).mean()),
        "operating_models": int(len(operating)),
        "operating_raw_p_lt_005": int(operating.loc[operating["status"].eq("ok"), "p_value"].lt(0.05).sum()),
        "operating_fdr_lt_005": int(operating.loc[operating["status"].eq("ok"), "fdr_within_family"].lt(0.05).sum()),
        "joint_tests_fdr_lt_005": int(joint.loc[joint["status"].eq("ok"), "fdr_all_joint_tests"].lt(0.05).sum()),
        "preferred_car_beta": float(preferred["coefficient"]),
        "preferred_car_p": float(preferred["p_value"]),
        "preferred_car_fdr": float(preferred["fdr_within_family"]),
        "lagged_control_car_beta": float(lagged["coefficient"]),
        "lagged_control_car_p": float(lagged["p_value"]),
        "future_level_placebo_beta": float(placebo["coefficient"]),
        "future_level_placebo_p": float(placebo["p_value"]),
        "temporal_restriction_any_raw_p_lt_005": int(frame.loc[ok, "p_value"].lt(0.05).sum()),
        "temporal_restriction_any_fdr_lt_005": int(frame.loc[ok, "fdr_temporal_family"].lt(0.05).sum()),
        "source_panel_sha256": sha256(SOURCE / "03_frozen_augmented_research_panel.csv"),
        "source_event_sha256": sha256(SOURCE / "15_latest_text_aligned_event_study.csv"),
        "model_decision": "retain operating firm/year FE models and CAR event-date FE with firm/event-date two-way clustering",
        "causal_scope": "associational until independent text validation and a defensible external treatment are available",
    }
    (RESULT_OUT / "06_最终模型审计摘要.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
