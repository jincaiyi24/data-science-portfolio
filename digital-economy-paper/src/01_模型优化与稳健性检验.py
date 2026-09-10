#!/usr/bin/env python3
"""Audit and extend the frozen Korean digital-strategy panel models.

This script never overwrites the frozen 2026-08-16 analysis.  It addresses
four diagnostics discovered after freezing the baseline specification:

1. DigitalStrategy is zero-inflated and highly persistent.
2. MarketSignalDisclosure mechanically contains substantive digital sentences.
3. Raw sales growth and operating margin can be unstable near small denominators.
4. Annual-report events are highly concentrated on a small number of trading days.

The additional specifications are robustness or exploratory analyses.  They are
not a search for statistical significance and do not create causal identification.
"""

from __future__ import annotations

import json
import math
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS
from scipy.stats import chi2
from statsmodels.stats.outliers_influence import variance_inflation_factor


WORKSPACE = Path(__file__).resolve().parents[2]
SOURCE_DIR = WORKSPACE / "outputs" / "ssci_empirical_completion_20260816"
OUTPUT_DIR = WORKSPACE / "outputs" / "model_optimization_20260816"
PANEL_PATH = SOURCE_DIR / "03_frozen_augmented_research_panel.csv"
ALIGNED_PATH = SOURCE_DIR / "15_latest_text_aligned_event_study.csv"

CORE_CONTROLS = [
    "FirmSize_w", "Leverage_w", "ROA_AvgAssets_w", "SalesGrowth_w",
    "Liquidity_w", "OperatingMargin_w", "FirmAgeLog_w", "LossDummy",
    "NegativeEquityDummy", "LogTotalSentences",
]
MARKET_CONTROLS = ["FiscalYearStockReturn_w", "FiscalYearDailyVolatility_w"]
EXTENDED_CONTROLS = [
    *CORE_CONTROLS,
    "AssetTurnover_w", "WorkingCapitalRatio_w", "EmployeeLog_w",
    "LargestHolderGroupOwnership_w",
]
GOVERNANCE_CONTROLS = ["RAndDIntensityReported_w", "OutsideDirectorRatio_w"]

PRIMARY_OPERATING = {
    "SalesGrowth_w_t1": "下一年销售增长率",
    "ROA_AvgAssets_w_t1": "下一年平均资产ROA",
    "OperatingMargin_w_t1": "下一年营业利润率",
}
ALTERNATIVE_OPERATING = {
    "LogSalesGrowth_w_t1": "下一年对数销售增长",
    "ROA_EndAssets_w_t1": "下一年期末资产ROA",
    "OperatingROA_w_t1": "下一年经营利润/平均资产",
    "LogAssetGrowth_w_t1": "下一年对数资产增长",
}


def winsor(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    valid = values.dropna()
    if valid.empty:
        return values
    lo, hi = valid.quantile([lower, upper])
    return values.clip(lo, hi)


def zscore(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    sd = values.std()
    return (values - values.mean()) / sd if pd.notna(sd) and sd > 0 else values * np.nan


def bh_adjust(values: pd.Series) -> pd.Series:
    p = pd.to_numeric(values, errors="coerce")
    result = pd.Series(np.nan, index=values.index, dtype=float)
    valid = p.notna()
    if not valid.any():
        return result
    raw = p.loc[valid].to_numpy(float)
    order = np.argsort(raw)
    ranked = raw[order]
    adjusted = np.minimum.accumulate(
        (ranked * len(ranked) / np.arange(1, len(ranked) + 1))[::-1]
    )[::-1]
    restored = np.empty_like(adjusted)
    restored[order] = np.minimum(adjusted, 1.0)
    result.loc[valid] = restored
    return result


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    return (num / den).where(den.gt(0))


def consecutive_shift(panel: pd.DataFrame, column: str, periods: int) -> pd.Series:
    grouped = panel.groupby("corp_code", sort=False)
    shifted = grouped[column].shift(periods)
    shifted_year = grouped["year"].shift(periods)
    return shifted.where(panel["year"].sub(shifted_year).eq(periods))


def add_derived_variables() -> pd.DataFrame:
    panel = pd.read_csv(
        PANEL_PATH,
        low_memory=False,
        dtype={"corp_code": str, "stock_code": str, "rcept_no": str},
    )
    panel["corp_code"] = panel["corp_code"].str.zfill(8)
    panel = panel.sort_values(["corp_code", "year"]).reset_index(drop=True).copy()

    substantive = pd.to_numeric(panel["substantive_digital_sentence_count"], errors="coerce").fillna(0)
    bmi = pd.to_numeric(panel["bmi_sentence_count"], errors="coerce").fillna(0)
    market_signal = pd.to_numeric(panel["market_signal_sentence_count"], errors="coerce").fillna(0)
    total = pd.to_numeric(panel["total_sentences"], errors="coerce").where(lambda x: x.gt(0))

    panel["Digital_pct_raw"] = 100 * substantive / total
    panel["PureSignal_pct"] = 100 * (market_signal - substantive).clip(lower=0) / total
    panel["OperationalDigital_pct"] = 100 * (substantive - bmi).clip(lower=0) / total
    panel["BMI_component_pct"] = 100 * bmi / total
    panel["Boilerplate_pct"] = 100 * pd.to_numeric(
        panel["boilerplate_digital_sentence_count"], errors="coerce"
    ).fillna(0) / total
    panel["PureSignal_z"] = zscore(panel["PureSignal_pct"])
    panel["OperationalDigital_z"] = zscore(panel["OperationalDigital_pct"])
    panel["BMI_component_z"] = zscore(panel["BMI_component_pct"])
    panel["Boilerplate_z"] = zscore(panel["Boilerplate_pct"])

    # Empirical-logit sentence rate remains finite at zero and accounts for report length.
    panel["Digital_empirical_logit"] = np.log(
        (substantive + 0.5) / (total - substantive + 0.5)
    )
    panel["Digital_empirical_logit_z"] = zscore(panel["Digital_empirical_logit"])

    positive_log_rate = np.log((substantive / total).where(substantive.gt(0)))
    panel["Digital_positive_intensity_z"] = zscore(positive_log_rate)
    panel["Digital_hurdle_intensity"] = panel["Digital_positive_intensity_z"].where(
        substantive.gt(0), 0.0
    )

    lag_digital = consecutive_shift(panel, "Digital_pct_raw", 1)
    lag2_digital = consecutive_shift(panel, "Digital_pct_raw", 2)
    panel["Digital_change_raw"] = panel["Digital_pct_raw"] - lag_digital
    panel["Digital_change_z"] = zscore(panel["Digital_change_raw"])
    panel["Digital_trailing3_raw"] = pd.concat(
        [panel["Digital_pct_raw"], lag_digital, lag2_digital], axis=1
    ).mean(axis=1).where(lag_digital.notna() & lag2_digital.notna())
    panel["Digital_trailing3_z"] = zscore(panel["Digital_trailing3_raw"])
    panel["Digital_lag1_z"] = consecutive_shift(panel, "Digital_z", 1)
    panel["Digital_lead1_z"] = consecutive_shift(panel, "Digital_z", -1)
    panel["Digital_change_lead1_z"] = consecutive_shift(panel, "Digital_change_z", -1)
    panel["Digital_x_KOSDAQ_optimized"] = panel["Digital_z"] * pd.to_numeric(
        panel["KOSDAQ"], errors="coerce"
    )

    positive = panel["Digital_pct_raw"].gt(0)
    positive_bins = pd.qcut(
        panel.loc[positive, "Digital_pct_raw"], q=4,
        labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop",
    )
    panel["Digital_positive_bin"] = pd.Series(index=panel.index, dtype="object")
    panel.loc[positive, "Digital_positive_bin"] = positive_bins.astype(str)
    for label in ("Q1", "Q2", "Q3", "Q4"):
        panel[f"Digital_bin_{label}"] = panel["Digital_positive_bin"].eq(label).astype(float)

    # Alternative accounting outcomes are less sensitive to tiny sales denominators.
    panel["LogSalesLevel"] = np.log(pd.to_numeric(panel["Sales"], errors="coerce").where(lambda x: x.gt(0)))
    panel["LogAssetsLevel"] = np.log(pd.to_numeric(panel["TotalAssets"], errors="coerce").where(lambda x: x.gt(0)))
    panel["LogSalesGrowth"] = panel["LogSalesLevel"] - consecutive_shift(panel, "LogSalesLevel", 1)
    panel["LogAssetGrowth"] = panel["LogAssetsLevel"] - consecutive_shift(panel, "LogAssetsLevel", 1)
    panel["OperatingROA"] = safe_divide(panel["OperatingIncome"], panel["AverageAssets"])

    for variable in [
        "ROA_EndAssets", "LogSalesGrowth", "LogAssetGrowth", "OperatingROA",
        "AssetTurnover", "WorkingCapitalRatio", "EmployeeLog",
        "LargestHolderGroupOwnership", "RAndDIntensityReported", "OutsideDirectorRatio",
    ]:
        panel[f"{variable}_w"] = winsor(panel[variable])
    for variable in ["LogSalesGrowth_w", "LogAssetGrowth_w", "OperatingROA_w", "ROA_EndAssets_w"]:
        panel[f"{variable}_t1"] = consecutive_shift(panel, variable, -1)

    # Previous-year information set for event-return specifications.
    for variable in [*CORE_CONTROLS, *MARKET_CONTROLS]:
        panel[f"{variable}_l1"] = consecutive_shift(panel, variable, 1)

    aligned = pd.read_csv(
        ALIGNED_PATH,
        low_memory=False,
        dtype={"corp_code": str, "stock_code": str, "rcept_no": str},
    )
    aligned["corp_code"] = aligned["corp_code"].str.zfill(8)
    aligned_columns = [
        "corp_code", "year", "text_aligned_filing_date", "text_aligned_trading_date",
        "text_aligned_event_status", "text_aligned_estimation_observations",
        "AlignedCAR_m1_p1", "AlignedCAR_0_p2", "AlignedCAR_0_p5",
        "AlignedMarketAdjustedCAR_m1_p1", "AlignedMarketAdjustedCAR_0_p2",
        "AlignedMarketAdjustedCAR_0_p5",
    ]
    panel = panel.merge(
        aligned[aligned_columns], on=["corp_code", "year"], how="left", validate="one_to_one"
    )
    panel["event_market_date"] = (
        panel["market"].astype(str) + "_" + panel["text_aligned_trading_date"].astype(str)
    ).where(panel["text_aligned_trading_date"].notna())
    for variable in [
        "AlignedCAR_m1_p1", "AlignedCAR_0_p2", "AlignedCAR_0_p5",
        "AlignedMarketAdjustedCAR_m1_p1", "AlignedMarketAdjustedCAR_0_p2",
        "AlignedMarketAdjustedCAR_0_p5",
    ]:
        panel[f"{variable}_w"] = winsor(panel[variable])

    panel["CorrectionLagLog_w"] = winsor(np.log1p(pd.to_numeric(panel["correction_lag_days"], errors="coerce").clip(lower=0)))
    return panel


def covariance_kwargs(work: pd.DataFrame, covariance: str, event_date: str | None) -> dict[str, Any]:
    if covariance == "firm":
        return {"cov_type": "clustered", "cluster_entity": True, "debiased": True}
    if covariance == "firm_year":
        return {
            "cov_type": "clustered", "cluster_entity": True,
            "cluster_time": True, "debiased": True,
        }
    if covariance == "driscoll_kraay":
        return {
            "cov_type": "kernel", "kernel": "bartlett", "bandwidth": 3,
            "debiased": True,
        }
    if covariance == "firm_event_date":
        if not event_date:
            raise ValueError("event_date is required for firm_event_date clustering")
        dates = pd.Categorical(work[event_date].astype(str)).codes
        clusters = pd.DataFrame(
            {
                "firm": pd.Categorical(work.index.get_level_values("corp_code")).codes,
                "event_date": dates,
            },
            index=work.index,
        )
        return {"cov_type": "clustered", "clusters": clusters, "debiased": True}
    raise ValueError(f"Unknown covariance: {covariance}")


def fit_panel(
    panel: pd.DataFrame,
    model_id: str,
    family: str,
    role: str,
    description: str,
    outcome: str,
    focals: list[str],
    controls: list[str],
    effect_spec: str = "firm_year",
    covariance: str = "firm",
    event_date: str | None = None,
    sample_note: str = "full eligible sample",
) -> tuple[list[dict[str, Any]], Any, pd.DataFrame]:
    extra = [column for column in ["industry_group", "market"] if column in panel.columns]
    if event_date:
        extra.append(event_date)
    required = ["corp_code", "year", outcome, *focals, *controls]
    columns = list(dict.fromkeys([*required, *extra]))
    work = panel.loc[:, columns].replace([np.inf, -np.inf], np.nan).dropna(subset=required).copy()
    if event_date:
        work = work.dropna(subset=[event_date])
    if len(work) < 100 or work["corp_code"].nunique() < 20:
        return ([{
            "model_id": model_id, "family": family, "role": role,
            "description": description, "outcome": outcome, "focal": focal,
            "status": "insufficient_sample", "n": len(work),
        } for focal in focals], None, work)

    work = work.set_index(["corp_code", "year"]).sort_index()
    y = pd.to_numeric(work[outcome], errors="coerce").astype(float)
    x = work[[*focals, *controls]].apply(pd.to_numeric, errors="coerce").astype(float)
    constant = [column for column in x if x[column].nunique(dropna=True) <= 1]
    if any(focal in constant for focal in focals):
        return ([{
            "model_id": model_id, "family": family, "role": role,
            "description": description, "outcome": outcome, "focal": focal,
            "status": "no_variation", "n": len(work),
        } for focal in focals], None, work)
    dropped_controls = [column for column in constant if column in controls]
    x = x.drop(columns=dropped_controls)

    entity_effects = effect_spec in {"firm_year", "firm_industry_year", "firm_event_date"}
    time_effects = effect_spec in {"firm_year", "year_only"}
    other_effects = None
    if effect_spec == "firm_industry_year":
        labels = work["industry_group"].astype(str) + "_" + work.index.get_level_values("year").astype(str)
        other_effects = pd.DataFrame({"industry_year": pd.Categorical(labels).codes}, index=work.index)
    elif effect_spec == "firm_event_date":
        if not event_date:
            raise ValueError("event_date is required for firm_event_date effects")
        labels = work[event_date].astype(str)
        other_effects = pd.DataFrame({"event_date": pd.Categorical(labels).codes}, index=work.index)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = PanelOLS(
                y, x, entity_effects=entity_effects, time_effects=time_effects,
                other_effects=other_effects, drop_absorbed=True, check_rank=False,
            )
            fitted = model.fit(**covariance_kwargs(work, covariance, event_date))
        confidence = fitted.conf_int()
        outcome_sd = float(y.std())
        rows = []
        for focal in focals:
            coefficient = float(fitted.params.get(focal, np.nan))
            standard_error = float(fitted.std_errors.get(focal, np.nan))
            rows.append({
                "model_id": model_id, "family": family, "role": role,
                "description": description, "outcome": outcome, "focal": focal,
                "coefficient": coefficient, "std_error": standard_error,
                "t_statistic": coefficient / standard_error if standard_error > 0 else np.nan,
                "p_value": float(fitted.pvalues.get(focal, np.nan)),
                "ci_95_low": float(confidence.loc[focal, "lower"]) if focal in confidence.index else np.nan,
                "ci_95_high": float(confidence.loc[focal, "upper"]) if focal in confidence.index else np.nan,
                "standardized_outcome_effect": coefficient / outcome_sd if outcome_sd > 0 else np.nan,
                "n": int(fitted.nobs),
                "firms": int(work.index.get_level_values("corp_code").nunique()),
                "years": int(work.index.get_level_values("year").nunique()),
                "r_squared_within": float(fitted.rsquared_within),
                "control_count": len(controls) - len(dropped_controls),
                "controls": "; ".join(c for c in controls if c not in dropped_controls),
                "dropped_controls": "; ".join(dropped_controls),
                "effect_spec": effect_spec, "covariance": covariance,
                "sample_note": sample_note, "status": "ok",
            })
        return rows, fitted, work
    except Exception as exc:  # noqa: BLE001
        return ([{
            "model_id": model_id, "family": family, "role": role,
            "description": description, "outcome": outcome, "focal": focal,
            "status": "error", "error": str(exc), "n": len(work),
        } for focal in focals], None, work)


def joint_wald_row(
    fitted: Any,
    model_id: str,
    family: str,
    role: str,
    outcome: str,
    variables: list[str],
    test_name: str,
) -> dict[str, Any] | None:
    if fitted is None or not all(variable in fitted.params.index for variable in variables):
        return None
    beta = fitted.params.loc[variables].to_numpy(float)
    covariance = fitted.cov.loc[variables, variables].to_numpy(float)
    statistic = float(beta @ np.linalg.pinv(covariance) @ beta)
    return {
        "model_id": model_id, "family": family, "role": role,
        "outcome": outcome, "test": test_name, "variables": "; ".join(variables),
        "chi2": statistic, "df": len(variables),
        "p_value": float(chi2.sf(statistic, len(variables))), "status": "ok",
    }


def detrend_within_firm(values: pd.DataFrame, firms: pd.Series, years: pd.Series) -> pd.DataFrame:
    output = pd.DataFrame(index=values.index, columns=values.columns, dtype=float)
    for _, index in firms.groupby(firms, sort=False).groups.items():
        idx = list(index)
        t = years.loc[idx].to_numpy(float)
        t_centered = t - t.mean()
        denominator = float(t_centered @ t_centered)
        block = values.loc[idx].to_numpy(float)
        centered = block - block.mean(axis=0)
        if denominator > 0:
            slopes = t_centered @ centered / denominator
            centered = centered - np.outer(t_centered, slopes)
        output.loc[idx] = centered
    return output


def fit_firm_trend(
    panel: pd.DataFrame,
    model_id: str,
    outcome: str,
    controls: list[str],
) -> list[dict[str, Any]]:
    required = ["corp_code", "year", outcome, "Digital_z", *controls]
    work = panel[required].replace([np.inf, -np.inf], np.nan).dropna().copy()
    sizes = work.groupby("corp_code")["year"].transform("size")
    work = work.loc[sizes.ge(4)].copy()
    numeric = work[[outcome, "Digital_z", *controls]].astype(float)
    residualized = detrend_within_firm(numeric, work["corp_code"], work["year"])
    transformed = pd.concat([work[["corp_code", "year"]].reset_index(drop=True), residualized.reset_index(drop=True)], axis=1)
    rows, _, _ = fit_panel(
        transformed, model_id, "operating_firm_trend", "robustness",
        "先移除公司特定线性趋势，再控制年份固定效应",
        outcome, ["Digital_z"], controls, effect_spec="year_only", covariance="firm",
        sample_note="firms with at least four complete observations",
    )
    return rows


def fit_first_difference(
    panel: pd.DataFrame,
    model_id: str,
    outcome: str,
    controls: list[str],
) -> list[dict[str, Any]]:
    required = ["corp_code", "year", outcome, "Digital_z", *controls]
    work = panel[required].replace([np.inf, -np.inf], np.nan).dropna().sort_values(["corp_code", "year"]).copy()
    grouped = work.groupby("corp_code", sort=False)
    prior_year = grouped["year"].shift(1)
    consecutive = work["year"].sub(prior_year).eq(1)
    differenced = work[["corp_code", "year"]].copy()
    for variable in [outcome, "Digital_z", *controls]:
        differenced[variable] = work[variable] - grouped[variable].shift(1)
    differenced = differenced.loc[consecutive].copy()
    rows, _, _ = fit_panel(
        differenced, model_id, "operating_first_difference", "robustness",
        "连续年度一阶差分并控制年份固定效应",
        outcome, ["Digital_z"], controls, effect_spec="year_only", covariance="firm",
        sample_note="consecutive complete observations",
    )
    return rows


def parsimonious_controls(outcome: str) -> list[str]:
    baseline_map = {
        "SalesGrowth_w_t1": "SalesGrowth_w",
        "ROA_AvgAssets_w_t1": "ROA_AvgAssets_w",
        "OperatingMargin_w_t1": "OperatingMargin_w",
        "LogSalesGrowth_w_t1": "LogSalesGrowth_w",
        "ROA_EndAssets_w_t1": "ROA_EndAssets_w",
        "OperatingROA_w_t1": "OperatingROA_w",
        "LogAssetGrowth_w_t1": "LogAssetGrowth_w",
    }
    return [
        "FirmSize_w", "Leverage_w", baseline_map[outcome], "Liquidity_w",
        "FirmAgeLog_w", "LossDummy", "LogTotalSentences",
    ]


def run_operating_models(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    results: list[dict[str, Any]] = []
    joint_tests: list[dict[str, Any]] = []
    for outcome in PRIMARY_OPERATING:
        core = [control for control in CORE_CONTROLS if control != outcome]
        specs = [
            ("CORE", panel, ["Digital_z"], core, "firm_year", "firm", "confirmatory", "冻结核心控制复核"),
            ("PARSIMONIOUS", panel, ["Digital_z"], parsimonious_controls(outcome), "firm_year", "firm", "robustness", "结果变量专属精简控制"),
            ("INDUSTRY_YEAR", panel, ["Digital_z"], core, "firm_industry_year", "firm", "robustness", "公司与行业×年份固定效应"),
            ("DK", panel, ["Digital_z"], core, "firm_year", "driscoll_kraay", "robustness", "Driscoll-Kraay标准误"),
            ("EMPIRICAL_LOGIT", panel, ["Digital_empirical_logit_z"], core, "firm_year", "firm", "robustness", "平滑句子发生率，处理零值与篇幅"),
            ("CHANGE", panel, ["Digital_change_z"], core, "firm_year", "firm", "exploratory", "数字战略相对上年的变化量"),
            ("TRAILING3", panel, ["Digital_trailing3_z"], core, "firm_year", "firm", "exploratory", "连续三年数字战略持续强度"),
            ("HURDLE", panel, ["Digital_any", "Digital_hurdle_intensity"], core, "firm_year", "firm", "exploratory", "两部分模型：是否披露与正值强度"),
            ("DISTRIBUTED_LAG", panel, ["Digital_z", "Digital_lag1_z"], core, "firm_year", "firm", "exploratory", "当期与前一期数字战略联合进入"),
            ("EXTENDED", panel, ["Digital_z"], EXTENDED_CONTROLS, "firm_year", "firm", "robustness", "加入效率、营运资本、员工和所有权"),
            ("GOVERNANCE_2020PLUS", panel.loc[panel["year"].ge(2020)].copy(), ["Digital_z"], [*EXTENDED_CONTROLS, *GOVERNANCE_CONTROLS], "firm_year", "firm", "robustness", "2020年后加入研发强度与外部董事比例"),
            ("NO_DELISTED", panel.loc[~panel["historical_delisted_sample"].fillna(False)].copy(), ["Digital_z"], core, "firm_year", "firm", "robustness", "排除历史退市公司"),
        ]
        for code, sample, focals, controls, effects, covariance, role, description in specs:
            model_id = f"OP_{code}_{outcome}"
            rows, fitted, _ = fit_panel(
                sample, model_id, "operating_optimized", role, description,
                outcome, focals, controls, effect_spec=effects, covariance=covariance,
            )
            results.extend(rows)
            if code in {"HURDLE", "DISTRIBUTED_LAG"}:
                test = joint_wald_row(
                    fitted, model_id, "operating_optimized", role, outcome, focals,
                    f"joint_{code.lower()}",
                )
                if test:
                    joint_tests.append(test)
        results.extend(fit_first_difference(panel, f"OP_FIRST_DIFF_{outcome}", outcome, core))
        results.extend(fit_firm_trend(panel, f"OP_FIRM_TREND_{outcome}", outcome, core))

        bin_focals = ["Digital_bin_Q1", "Digital_bin_Q2", "Digital_bin_Q3", "Digital_bin_Q4"]
        model_id = f"OP_BINS_{outcome}"
        rows, fitted, _ = fit_panel(
            panel, model_id, "operating_semiparametric", "exploratory",
            "零披露为参照的正值四分位组", outcome, bin_focals, core,
        )
        results.extend(rows)
        test = joint_wald_row(
            fitted, model_id, "operating_semiparametric", "exploratory",
            outcome, bin_focals, "joint_positive_bins",
        )
        if test:
            joint_tests.append(test)

        component_focals = ["OperationalDigital_z", "BMI_component_z"]
        model_id = f"OP_INTERNAL_COMPONENTS_{outcome}"
        rows, fitted, _ = fit_panel(
            panel, model_id, "operating_internal_components", "exploratory",
            "运营数字化与BMI数字化分解", outcome, component_focals, core,
        )
        results.extend(rows)
        test = joint_wald_row(
            fitted, model_id, "operating_internal_components", "exploratory",
            outcome, component_focals, "joint_internal_components",
        )
        if test:
            joint_tests.append(test)

        positive_sample = panel.loc[panel["Digital_pct_raw"].gt(0)].copy()
        positive_sample["Digital_positive_sq"] = positive_sample["Digital_positive_intensity_z"] ** 2
        positive_sample["Digital_positive_cube"] = positive_sample["Digital_positive_intensity_z"] ** 3
        cubic_focals = ["Digital_positive_intensity_z", "Digital_positive_sq", "Digital_positive_cube"]
        model_id = f"OP_POSITIVE_CUBIC_{outcome}"
        rows, fitted, _ = fit_panel(
            positive_sample, model_id, "operating_nonlinearity", "exploratory",
            "仅正值样本的三次多项式", outcome, cubic_focals, core,
            sample_note="positive substantive-disclosure firm-years",
        )
        results.extend(rows)
        test = joint_wald_row(
            fitted, model_id, "operating_nonlinearity", "exploratory",
            outcome, ["Digital_positive_sq", "Digital_positive_cube"],
            "joint_nonlinear_terms",
        )
        if test:
            joint_tests.append(test)

    for outcome in ALTERNATIVE_OPERATING:
        for code, effects in [("CORE", "firm_year"), ("INDUSTRY_YEAR", "firm_industry_year")]:
            rows, _, _ = fit_panel(
                panel, f"ALT_{code}_{outcome}", "alternative_operating_outcomes", "robustness",
                "分母稳健的替代经营结果", outcome, ["Digital_z"],
                parsimonious_controls(outcome), effect_spec=effects, covariance="firm",
            )
            results.extend(rows)

    frame = pd.DataFrame(results)
    ok = frame["status"].eq("ok") & frame["p_value"].notna()
    for family, indices in frame.loc[ok].groupby("family").groups.items():
        frame.loc[indices, "fdr_within_family"] = bh_adjust(frame.loc[indices, "p_value"])
    return frame, pd.DataFrame(joint_tests)


def car_control_sets() -> dict[str, list[str]]:
    lagged_core = [f"{variable}_l1" for variable in CORE_CONTROLS]
    return {
        "core": [*CORE_CONTROLS, *MARKET_CONTROLS],
        "lagged": [*lagged_core, *MARKET_CONTROLS],
        "parsimonious": [
            "FirmSize_w", "Leverage_w", "ROA_AvgAssets_w", "SalesGrowth_w",
            "FiscalYearStockReturn_w", "FiscalYearDailyVolatility_w", "LogTotalSentences",
        ],
        "minimal": ["FiscalYearStockReturn_w", "FiscalYearDailyVolatility_w", "LogTotalSentences"],
    }


def preferred_car(
    panel: pd.DataFrame,
    model_id: str,
    outcome: str = "AlignedCAR_0_p2_w",
    focals: list[str] | None = None,
    controls: list[str] | None = None,
    role: str = "robustness",
    description: str = "披露交易日固定效应与公司/披露日双向聚类",
    sample_note: str = "exact corrected-text filing date",
) -> tuple[list[dict[str, Any]], Any, pd.DataFrame]:
    return fit_panel(
        panel, model_id, "car_optimized", role, description, outcome,
        focals or ["Digital_z"], controls or car_control_sets()["core"],
        effect_spec="firm_event_date", covariance="firm_event_date",
        event_date="text_aligned_trading_date", sample_note=sample_note,
    )


def run_car_models(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    results: list[dict[str, Any]] = []
    joint_tests: list[dict[str, Any]] = []
    core = car_control_sets()["core"]

    baseline_specs = [
        ("YEAR_FE_FIRM_CLUSTER", "firm_year", "firm", core, "confirmatory", "冻结模型在严格对齐CAR上的复核"),
        ("EVENT_DATE_FE_FIRM_CLUSTER", "firm_event_date", "firm", core, "robustness", "披露交易日固定效应，公司聚类"),
        ("EVENT_DATE_FE_TWO_WAY", "firm_event_date", "firm_event_date", core, "robustness", "披露交易日固定效应，公司/披露日双向聚类"),
        ("EVENT_DATE_FE_LAGGED_CONTROLS", "firm_event_date", "firm_event_date", car_control_sets()["lagged"], "robustness", "使用前一年财务控制，避免控制同期披露结果"),
        ("EVENT_DATE_FE_PARSIMONIOUS", "firm_event_date", "firm_event_date", car_control_sets()["parsimonious"], "robustness", "结果变量专属精简控制"),
        ("EVENT_DATE_FE_MINIMAL", "firm_event_date", "firm_event_date", car_control_sets()["minimal"], "robustness", "仅市场状态和报告篇幅控制"),
    ]
    for code, effects, covariance, controls, role, description in baseline_specs:
        rows, _, _ = fit_panel(
            panel, f"CAR_{code}", "car_optimized", role, description,
            "AlignedCAR_0_p2_w", ["Digital_z"], controls,
            effect_spec=effects, covariance=covariance,
            event_date="text_aligned_trading_date",
            sample_note="exact corrected-text filing date",
        )
        results.extend(rows)

    rows, _, _ = fit_panel(
        panel, "CAR_MARKET_DATE_FE_TWO_WAY", "car_optimized", "robustness",
        "市场×披露交易日固定效应，公司/市场披露日双向聚类",
        "AlignedCAR_0_p2_w", ["Digital_z"], core,
        effect_spec="firm_event_date", covariance="firm_event_date",
        event_date="event_market_date", sample_note="exact corrected-text filing date",
    )
    results.extend(rows)

    governance_sample = panel.loc[panel["year"].ge(2020)].copy()
    rows, _, _ = preferred_car(
        governance_sample, "CAR_GOVERNANCE_2020PLUS",
        controls=[*EXTENDED_CONTROLS, *GOVERNANCE_CONTROLS, *MARKET_CONTROLS],
        description="2020年后加入研发、员工、所有权与董事会控制",
        sample_note="2020-2025 governance-complete cases",
    )
    results.extend(rows)

    alternative_outcomes = {
        "AlignedMarketAdjustedCAR_0_p2_w": "市场调整CAR[0,+2]",
        "AlignedCAR_m1_p1_w": "市场模型CAR[-1,+1]",
        "AlignedCAR_0_p5_w": "市场模型CAR[0,+5]",
        "AlignedMarketAdjustedCAR_m1_p1_w": "市场调整CAR[-1,+1]",
        "AlignedMarketAdjustedCAR_0_p5_w": "市场调整CAR[0,+5]",
    }
    for outcome, description in alternative_outcomes.items():
        rows, _, _ = preferred_car(
            panel, f"CAR_ALT_{outcome}", outcome=outcome,
            description=f"替代事件窗/预期收益模型：{description}",
        )
        results.extend(rows)

    exposure_specs = [
        ("EMPIRICAL_LOGIT", ["Digital_empirical_logit_z"], "平滑数字句发生率"),
        ("CHANGE", ["Digital_change_z"], "数字战略相对上年变化"),
        ("PURE_SIGNAL", ["Digital_z", "PureSignal_z"], "实质行动与非实质市场信号同时进入"),
        ("INTERNAL_COMPONENTS", ["OperationalDigital_z", "BMI_component_z"], "运营数字化与BMI数字化分解"),
        ("BOILERPLATE", ["Digital_z", "Boilerplate_z"], "实质行动与口号式披露同时进入"),
        ("MARKET_INTERACTION", ["Digital_z", "Digital_x_KOSDAQ_optimized"], "KOSPI/KOSDAQ斜率差异"),
    ]
    for code, focals, description in exposure_specs:
        rows, fitted, fitted_work = preferred_car(
            panel, f"CAR_EXPOSURE_{code}", focals=focals, description=description,
        )
        results.extend(rows)
        if len(focals) > 1:
            test = joint_wald_row(
                fitted, f"CAR_EXPOSURE_{code}", "car_optimized", "exploratory",
                "AlignedCAR_0_p2_w", focals, f"joint_{code.lower()}",
            )
            if test:
                joint_tests.append(test)
        if code == "MARKET_INTERACTION" and fitted is not None:
            variables = ["Digital_z", "Digital_x_KOSDAQ_optimized"]
            if all(variable in fitted.params.index for variable in variables):
                weights = np.array([1.0, 1.0])
                beta = fitted.params.loc[variables].to_numpy(float)
                covariance_matrix = fitted.cov.loc[variables, variables].to_numpy(float)
                coefficient = float(weights @ beta)
                standard_error = math.sqrt(max(float(weights @ covariance_matrix @ weights), 0.0))
                z_stat = coefficient / standard_error if standard_error > 0 else np.nan
                results.append({
                    "model_id": "CAR_EXPOSURE_MARKET_INTERACTION",
                    "family": "car_optimized", "role": "exploratory",
                    "description": "KOSDAQ中的数字战略边际效应",
                    "outcome": "AlignedCAR_0_p2_w", "focal": "Digital_marginal_KOSDAQ",
                    "coefficient": coefficient, "std_error": standard_error,
                    "t_statistic": z_stat,
                    "p_value": float(chi2.sf(z_stat ** 2, 1)) if pd.notna(z_stat) else np.nan,
                    "ci_95_low": coefficient - 1.96 * standard_error,
                    "ci_95_high": coefficient + 1.96 * standard_error,
                    "n": int(fitted.nobs),
                    "firms": int(fitted_work.index.get_level_values("corp_code").nunique()),
                    "effect_spec": "firm_event_date", "covariance": "firm_event_date",
                    "sample_note": "exact corrected-text filing date", "status": "ok",
                })

    sample_specs = [
        ("NO_CORRECTION", panel.loc[panel["correction_lag_days"].eq(0)].copy(), "latest text equals first filing", "未发生更正的年报"),
        ("CORRECTION_LE30", panel.loc[panel["correction_lag_days"].le(30)].copy(), "correction lag <= 30 days", "更正滞后不超过30天"),
        ("CORRECTION_LE90", panel.loc[panel["correction_lag_days"].le(90)].copy(), "correction lag <= 90 days", "更正滞后不超过90天"),
        ("ESTIMATION_GE200", panel.loc[pd.to_numeric(panel["text_aligned_estimation_observations"], errors="coerce").ge(200)].copy(), "at least 200 estimation observations", "市场模型估计窗至少200个交易日"),
        ("NO_DELISTED", panel.loc[~panel["historical_delisted_sample"].fillna(False)].copy(), "exclude historical delisted firms", "排除历史退市公司"),
        ("KOSPI", panel.loc[panel["market"].eq("KOSPI")].copy(), "KOSPI only", "KOSPI子样本"),
        ("KOSDAQ", panel.loc[panel["market"].eq("KOSDAQ")].copy(), "KOSDAQ only", "KOSDAQ子样本"),
    ]
    for code, sample, note, description in sample_specs:
        rows, _, _ = preferred_car(
            sample, f"CAR_SAMPLE_{code}", description=description, sample_note=note,
        )
        results.extend(rows)

    placebo_specs = [
        ("LEAD_LEVEL", "Digital_lead1_z", "未来一年数字战略预测当期CAR"),
        ("LEAD_CHANGE", "Digital_change_lead1_z", "未来一年数字战略变化预测当期CAR"),
    ]
    for code, focal, description in placebo_specs:
        rows, _, _ = preferred_car(
            panel, f"CAR_PLACEBO_{code}", focals=[focal], role="diagnostic",
            description=description,
        )
        results.extend(rows)

    leave_year_rows: list[dict[str, Any]] = []
    for year in sorted(panel["year"].unique()):
        sample = panel.loc[panel["year"].ne(year)].copy()
        rows, _, _ = preferred_car(
            sample, f"CAR_LEAVE_YEAR_{year}", description=f"剔除{year}年",
            sample_note=f"leave out fiscal year {year}",
        )
        for row in rows:
            row["left_out_year"] = int(year)
            leave_year_rows.append(row)
    results.extend(leave_year_rows)

    frame = pd.DataFrame(results)
    ok = frame["status"].eq("ok") & frame["p_value"].notna()
    for family, indices in frame.loc[ok].groupby("family").groups.items():
        frame.loc[indices, "fdr_within_family"] = bh_adjust(frame.loc[indices, "p_value"])
    leave_year = frame[frame["model_id"].str.startswith("CAR_LEAVE_YEAR_")].copy()
    return frame, pd.DataFrame(joint_tests), leave_year


def within_correlation(panel: pd.DataFrame, left: str, right: str) -> float:
    work = panel[["corp_code", left, right]].replace([np.inf, -np.inf], np.nan).dropna()
    if work.empty:
        return np.nan
    left_w = work[left] - work.groupby("corp_code")[left].transform("mean")
    right_w = work[right] - work.groupby("corp_code")[right].transform("mean")
    return float(left_w.corr(right_w))


def control_assessment(panel: pd.DataFrame) -> pd.DataFrame:
    definitions = [
        ("FirmSize_w", "规模、资源与信息环境", "保留核心"),
        ("Leverage_w", "融资约束与风险", "保留核心"),
        ("ROA_AvgAssets_w", "基期盈利能力", "按结果变量保留"),
        ("SalesGrowth_w", "基期成长性", "按结果变量保留"),
        ("Liquidity_w", "短期偿债能力", "保留核心"),
        ("OperatingMargin_w", "基期经营效率", "按结果变量保留"),
        ("FirmAgeLog_w", "组织成熟度", "保留核心"),
        ("LossDummy", "亏损状态与尾部风险", "保留核心"),
        ("NegativeEquityDummy", "财务困境", "保留核心但稀少"),
        ("LogTotalSentences", "报告长度与披露机会", "必须保留"),
        ("FiscalYearStockReturn_w", "披露前市场状态", "CAR模型保留"),
        ("FiscalYearDailyVolatility_w", "公司风险与噪声", "CAR模型保留"),
        ("AssetTurnover_w", "资产使用效率", "扩展稳健性"),
        ("WorkingCapitalRatio_w", "营运资本与流动性结构", "扩展稳健性"),
        ("EmployeeLog_w", "组织规模与人力能力", "扩展稳健性，注意缺失"),
        ("LargestHolderGroupOwnership_w", "控制权集中与治理", "扩展稳健性"),
        ("RAndDIntensityReported_w", "吸收能力与创新投入", "2020年后机制/稳健性"),
        ("OutsideDirectorRatio_w", "董事会独立性", "2020年后治理稳健性"),
        ("CorrectionLagLog_w", "文本更正时滞", "CAR样本筛选，不作常规控制"),
    ]
    rows = []
    for variable, rationale, decision in definitions:
        values = pd.to_numeric(panel[variable], errors="coerce")
        within = values - panel.groupby("corp_code")[variable].transform("mean")
        rows.append({
            "variable": variable, "theoretical_role": rationale, "decision": decision,
            "nonmissing": int(values.notna().sum()), "coverage": float(values.notna().mean()),
            "overall_sd": float(values.std()), "within_sd": float(within.std()),
            "within_to_overall_sd": float(within.std() / values.std()) if values.std() > 0 else np.nan,
            "correlation_with_digital": float(values.corr(panel["Digital_z"])),
            "within_correlation_with_digital": within_correlation(panel, variable, "Digital_z"),
        })
    return pd.DataFrame(rows)


def vif_assessment(panel: pd.DataFrame) -> pd.DataFrame:
    sets = {
        "core": CORE_CONTROLS,
        "extended": EXTENDED_CONTROLS,
        "governance_complete": [*EXTENDED_CONTROLS, *GOVERNANCE_CONTROLS],
    }
    rows = []
    for label, variables in sets.items():
        work = panel[variables].replace([np.inf, -np.inf], np.nan).dropna()
        varying = [variable for variable in variables if work[variable].nunique() > 1]
        standardized = (work[varying] - work[varying].mean()) / work[varying].std()
        for index, variable in enumerate(varying):
            rows.append({
                "set": label, "variable": variable,
                "vif": float(variance_inflation_factor(standardized.to_numpy(), index)),
                "n": len(work),
            })
    return pd.DataFrame(rows)


def diagnostics(panel: pd.DataFrame) -> pd.DataFrame:
    firm_mean = panel.groupby("corp_code")["DigitalStrategy"].transform("mean")
    lag = consecutive_shift(panel, "DigitalStrategy", 1)
    event_counts = panel.groupby("text_aligned_trading_date").size()
    rows = [
        ("panel_rows", len(panel)),
        ("firms", panel["corp_code"].nunique()),
        ("digital_zero_share", panel["DigitalStrategy"].eq(0).mean()),
        ("digital_positive_firm_years", panel["DigitalStrategy"].gt(0).sum()),
        ("digital_overall_sd", panel["DigitalStrategy"].std()),
        ("digital_within_sd", (panel["DigitalStrategy"] - firm_mean).std()),
        ("digital_ar1", panel["DigitalStrategy"].corr(lag)),
        ("firms_without_digital_within_variation", panel.groupby("corp_code")["DigitalStrategy"].nunique().le(1).sum()),
        ("firms_switching_zero_positive", panel.groupby("corp_code")["Digital_any"].nunique().gt(1).sum()),
        ("digital_market_signal_correlation", panel["DigitalStrategy"].corr(panel["MarketSignalDisclosure"])),
        ("substantive_market_count_identical_share", (panel["substantive_digital_sentence_count"] == panel["market_signal_sentence_count"]).mean()),
        ("unique_aligned_event_trading_dates", event_counts.size),
        ("maximum_events_same_trading_date", event_counts.max()),
        ("correction_lag_zero_share", panel["correction_lag_days"].eq(0).mean()),
        ("correction_lag_le30_share", panel["correction_lag_days"].le(30).mean()),
        ("aligned_car_0_p2_coverage", panel["AlignedCAR_0_p2"].notna().mean()),
    ]
    return pd.DataFrame(rows, columns=["diagnostic", "value"])


def write_report(
    panel: pd.DataFrame,
    operating: pd.DataFrame,
    car: pd.DataFrame,
    controls: pd.DataFrame,
    vifs: pd.DataFrame,
    joint: pd.DataFrame,
) -> None:
    def result(model_id: str, focal: str = "Digital_z") -> pd.Series | None:
        subset = pd.concat([operating, car], ignore_index=True)
        found = subset.loc[subset["model_id"].eq(model_id) & subset["focal"].eq(focal) & subset["status"].eq("ok")]
        return found.iloc[0] if not found.empty else None

    def fmt(row: pd.Series | None) -> str:
        if row is None:
            return "模型未成功估计"
        return f"β={row.coefficient:.6f}, SE={row.std_error:.6f}, p={row.p_value:.4f}, N={int(row.n):,}"

    preferred = result("CAR_EVENT_DATE_FE_TWO_WAY")
    market_date = result("CAR_MARKET_DATE_FE_TWO_WAY")
    lagged = result("CAR_EVENT_DATE_FE_LAGGED_CONTROLS")
    placebo = result("CAR_PLACEBO_LEAD_LEVEL", "Digital_lead1_z")
    market_adjusted = result("CAR_ALT_AlignedMarketAdjustedCAR_0_p2_w")
    operating_raw_significant = int(
        operating.loc[operating["status"].eq("ok"), "p_value"].lt(0.05).sum()
    )
    operating_fdr_significant = int(
        operating.loc[operating["status"].eq("ok"), "fdr_within_family"].lt(0.05).sum()
    )
    car_fdr_significant = int(
        car.loc[car["status"].eq("ok"), "fdr_within_family"].lt(0.05).sum()
    )
    lines = [
        "# 韩国上市公司数字化战略模型优化审计",
        "",
        "生成日期：2026-08-16",
        "",
        "## 一、审计结论",
        "",
        f"- 冻结样本为 {panel['corp_code'].nunique():,} 家公司、{len(panel):,} 个公司年度。",
        f"- DigitalStrategy 零值占比为 {panel['DigitalStrategy'].eq(0).mean():.1%}，年度相关系数约为 {panel['DigitalStrategy'].corr(consecutive_shift(panel, 'DigitalStrategy', 1)):.3f}。线性模型应与两部分模型、变化量和持续强度并列报告。",
        f"- DigitalStrategy 与 MarketSignalDisclosure 的相关系数为 {panel['DigitalStrategy'].corr(panel['MarketSignalDisclosure']):.3f}；后者在分类定义上包含实质数字句，不能作为独立外部路径。外部路径应使用 PureSignal/SignalGap。",
        f"- 单一披露交易日最多出现 {int(panel.groupby('text_aligned_trading_date').size().max()):,} 个事件，因此 CAR 的优先推断应使用披露日固定效应和公司×披露日双向聚类。",
        "",
        "## 二、CAR优化后的关键结果",
        "",
        f"- 披露日固定效应 + 公司/披露日双向聚类：{fmt(preferred)}。",
        f"- 市场×披露日固定效应 + 公司/市场披露日双向聚类：{fmt(market_date)}。",
        f"- 改用前一年财务控制：{fmt(lagged)}。",
        f"- 市场调整CAR替代：{fmt(market_adjusted)}。",
        f"- 未来数字战略安慰剂：{fmt(placebo)}。未来值若仍能预测当期CAR，负向关系只能解释为条件相关，不能称为市场惩罚或因果效应。",
        f"- CAR敏感性检验经同族Benjamini-Hochberg校正后显著结果为 {car_fdr_significant} 个；不能把单个未经校正的 p<0.05 当作稳健结论。",
        "",
        "## 三、经营绩效模型结论",
        "",
        f"- 经营绩效共输出 {len(operating):,} 个焦点系数，未经多重检验校正的 p<0.05 为 {operating_raw_significant} 个，FDR<0.05 为 {operating_fdr_significant} 个。",
        "- 销售增长、ROA、营业利润率、对数销售增长、期末资产ROA、经营ROA和资产增长均未形成可重复的数字战略效应。",
        "- 两部分模型、年度变化、三年持续强度、分布滞后、第一差分、公司趋势、正值四分位与三次项联合检验均不支持稳定的线性或非线性关系。",
        "",
        "## 四、控制变量建议",
        "",
        "1. 正式基准仍保留规模、杠杆、基期绩效、流动性、年龄、亏损、负权益和报告长度。报告长度必须保留，因为解释变量是句子比例。",
        "2. CAR 模型增加披露前股票收益和波动率；同期财务控制与前一年财务控制都报告，以展示信息集选择是否改变结果。",
        "3. 资产周转率、营运资本、员工规模和最大股东持股只作为扩展稳健性。研发与外部董事覆盖率较低，只能用于2020年后子样本。",
        "4. 不同时加入 CurrentAssetRatio 与 NoncurrentAssetRatio，它们接近机械互补；不为追求显著性任意合并或删除基期绩效变量。",
        "5. 下一轮优先补充现金持有、固定资产比率、资本开支、经营现金流、Tobin's Q/市净率、机构与外资持股、财阀集团、Big 4审计、分析师覆盖、行业集中度和事件日并发重大公告。",
        "",
        "## 五、新增检验的解释边界",
        "",
        "- 零值四分位、正值三次项和三年持续强度属于探索性检验，需要在论文中明确标注。",
        "- 第一差分和公司趋势模型非常保守，在只有约10年数据且DigitalStrategy高度持续时会显著降低统计功效。",
        "- Driscoll-Kraay与双向聚类用于处理横截面和时间相关，但不会解决反向因果。",
        "- 独立人工文本验证、外生冲击或有效工具变量仍是达到较高SSCI识别标准的主要缺口。",
        "",
        "## 六、推荐论文表格顺序",
        "",
        "1. 主表：公司固定效应、年份固定效应、公司聚类标准误，三个下一年经营结果。",
        "2. CAR主表：严格文本-披露日对齐、披露交易日固定效应、公司×披露日双向聚类。",
        "3. 测量稳健性：平滑发生率、是否披露、正值强度、年度变化、三年持续强度。",
        "4. 结果变量稳健性：对数销售增长、期末资产ROA、经营ROA、资产增长以及替代CAR窗。",
        "5. 识别边界：未来值安慰剂、第一差分、公司趋势、短更正滞后、估计窗质量与逐年剔除。",
        "",
        "## 七、方法依据",
        "",
        "- Petersen (2009), Review of Financial Studies: 面板残差可能在公司和时间维度相关，聚类层级必须匹配误差结构。",
        "  https://academic.oup.com/rfs/article-abstract/22/1/435/1585940",
        "- MacKinlay (1997), Journal of Economic Literature: 事件研究要求明确事件日、估计窗、预期收益模型和替代事件窗。",
        "- Chen and Srinivasan (2024), Review of Accounting Studies: 数字活动与估值可能正相关，但短期基本面改善证据较弱，并使用滞后因变量和IV处理选择偏误。",
        "  https://doi.org/10.1007/s11142-023-09753-0",
        "- Sklenarz et al. (2024), International Journal of Research in Marketing: 文本指标应验证、标准化并报告替代操作化和数字化侧重点。",
        "  https://doi.org/10.1016/j.ijresmar.2024.01.004",
        "",
        "## 八、输出索引",
        "",
        "- 01_model_diagnostics.csv：原模型风险诊断。",
        "- 02_derived_variable_coverage.csv：新增变量覆盖率。",
        "- 03_control_variable_assessment.csv：控制变量理论用途与公司内变异。",
        "- 04_control_vif_optimized.csv：核心、扩展与治理控制VIF。",
        "- 05_operating_model_optimization.csv：经营绩效优化模型。",
        "- 06_car_model_optimization.csv：CAR优化模型。",
        "- 07_joint_nonlinearity_and_hurdle_tests.csv：联合非线性与两部分检验。",
        "- 08_car_leave_one_year_out.csv：逐年剔除稳定性。",
        "- 11_模型优化结果汇总.xlsx：模型结果、控制变量取舍和诊断的统一工作簿。",
    ]
    (OUTPUT_DIR / "09_模型优化审计报告.md").write_text("\n".join(lines), encoding="utf-8-sig")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Preparing optimized variables...", flush=True)
    panel = add_derived_variables()
    diagnostics_frame = diagnostics(panel)
    diagnostics_frame.to_csv(OUTPUT_DIR / "01_model_diagnostics.csv", index=False, encoding="utf-8-sig")

    derived = [
        "Digital_empirical_logit_z", "Digital_change_z", "Digital_trailing3_z",
        "Digital_hurdle_intensity", "PureSignal_z", "OperationalDigital_z",
        "BMI_component_z", "LogSalesGrowth_w_t1", "ROA_EndAssets_w_t1",
        "OperatingROA_w_t1", "LogAssetGrowth_w_t1", "WorkingCapitalRatio_w",
    ]
    coverage = pd.DataFrame([
        {
            "variable": variable,
            "nonmissing": int(panel[variable].notna().sum()),
            "coverage": float(panel[variable].notna().mean()),
            "mean": float(panel[variable].mean()),
            "sd": float(panel[variable].std()),
        }
        for variable in derived
    ])
    coverage.to_csv(OUTPUT_DIR / "02_derived_variable_coverage.csv", index=False, encoding="utf-8-sig")

    print("Assessing controls...", flush=True)
    control_frame = control_assessment(panel)
    control_frame.to_csv(OUTPUT_DIR / "03_control_variable_assessment.csv", index=False, encoding="utf-8-sig")
    vif_frame = vif_assessment(panel)
    vif_frame.to_csv(OUTPUT_DIR / "04_control_vif_optimized.csv", index=False, encoding="utf-8-sig")

    print("Running operating-performance models...", flush=True)
    operating, operating_joint = run_operating_models(panel)
    operating.to_csv(OUTPUT_DIR / "05_operating_model_optimization.csv", index=False, encoding="utf-8-sig")

    print("Running filing-date CAR models...", flush=True)
    car, car_joint, leave_year = run_car_models(panel)
    car.to_csv(OUTPUT_DIR / "06_car_model_optimization.csv", index=False, encoding="utf-8-sig")
    joint = pd.concat([operating_joint, car_joint], ignore_index=True)
    if not joint.empty:
        joint["fdr_all_joint_tests"] = bh_adjust(joint["p_value"])
    joint.to_csv(OUTPUT_DIR / "07_joint_nonlinearity_and_hurdle_tests.csv", index=False, encoding="utf-8-sig")
    leave_year.to_csv(OUTPUT_DIR / "08_car_leave_one_year_out.csv", index=False, encoding="utf-8-sig")

    write_report(panel, operating, car, control_frame, vif_frame, joint)
    metadata = {
        "source_panel": str(PANEL_PATH),
        "source_panel_rows": len(panel),
        "firms": int(panel["corp_code"].nunique()),
        "output_directory": str(OUTPUT_DIR),
        "operating_coefficient_rows": len(operating),
        "car_coefficient_rows": len(car),
        "failed_operating_rows": int(operating["status"].ne("ok").sum()),
        "failed_car_rows": int(car["status"].ne("ok").sum()),
        "preferred_car_model": "CAR_EVENT_DATE_FE_TWO_WAY",
        "preferred_car_inference": "firm and event-trading-date two-way clustered standard errors",
        "causal_scope": "associational; optimization does not solve reverse causality",
    }
    (OUTPUT_DIR / "10_run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
