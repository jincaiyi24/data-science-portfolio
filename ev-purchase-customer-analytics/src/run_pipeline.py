from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import nbformat
import numpy as np
import optuna
import pandas as pd
import seaborn as sns
from catboost import CatBoostClassifier
from nbclient import NotebookClient
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from business_analysis import create_business_outputs, create_eda_outputs
from config import (
    AUDIT_DIR,
    CV_SPLITS,
    DASHBOARD_DIR,
    FIGURE_DIR,
    ID_COLUMN,
    MODEL_DIR,
    NOTEBOOK_DIR,
    OPTUNA_SAMPLE_SIZE,
    OPTUNA_TRIALS,
    RANDOM_STATE,
    REPORT_DIR,
    ROOT,
    PROCESSED_DIR,
    SUBMISSION_DIR,
    TABLE_DIR,
    TARGET,
    VALIDATION_SEEDS,
    ensure_directories,
)
from data import audit_data, load_data
from evaluation import cv_predict_pipeline, evaluate_catboost, evaluate_pipeline
from explainability import explain_tree_pipeline
from features import add_features, split_xy
from models import build_catboost, build_sklearn_model


warnings.filterwarnings("ignore", category=FutureWarning)
optuna.logging.set_verbosity(optuna.logging.WARNING)


def row(name: str, summary: dict[str, float]) -> dict[str, object]:
    return {"model": name, **summary}


def evaluate_named(name: str, x: pd.DataFrame, y: pd.Series, params: dict | None = None, folds: int = CV_SPLITS, seed: int = RANDOM_STATE):
    if name == "CatBoost":
        return evaluate_catboost(x, y, folds=folds, seed=seed, params=params)
    return evaluate_pipeline(build_sklearn_model(name, x, seed, params), x, y, folds=folds, seed=seed)


def tune_model(name: str, x: pd.DataFrame, y: pd.Series, trials: int = OPTUNA_TRIALS) -> tuple[dict, pd.DataFrame]:
    sample_idx, _ = train_test_split(np.arange(len(x)), train_size=min(OPTUNA_SAMPLE_SIZE, len(x)), stratify=y, random_state=RANDOM_STATE)
    sx, sy = x.iloc[sample_idx].reset_index(drop=True), y.iloc[sample_idx].reset_index(drop=True)

    def objective(trial: optuna.Trial) -> float:
        if name == "CatBoost":
            params = {
                "iterations": trial.suggest_int("iterations", 250, 550, step=100),
                "depth": trial.suggest_int("depth", 6, 9),
                "learning_rate": trial.suggest_float("learning_rate", 0.025, 0.10, log=True),
                "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 2.0, 12.0, log=True),
                "random_strength": trial.suggest_float("random_strength", 0.1, 2.0, log=True),
            }
        elif name == "LightGBM":
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 400, 1000, step=100),
                "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.08, log=True),
                "num_leaves": trial.suggest_int("num_leaves", 20, 80),
                "min_child_samples": trial.suggest_int("min_child_samples", 20, 100),
                "subsample": trial.suggest_float("subsample", 0.7, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.7, 1.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 8.0, log=True),
            }
        else:
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 400, 900, step=100),
                "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.09, log=True),
                "max_depth": trial.suggest_int("max_depth", 5, 10),
                "min_child_weight": trial.suggest_float("min_child_weight", 2.0, 12.0),
                "subsample": trial.suggest_float("subsample", 0.7, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.7, 1.0),
                "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 8.0, log=True),
            }
        summary, _ = evaluate_named(name, sx, sy, params=params, folds=3, seed=RANDOM_STATE)
        return float(summary["mean_roc_auc"])

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    history = study.trials_dataframe(attrs=("number", "value", "duration", "params", "state"))
    history.insert(0, "model", name)
    return study.best_params, history


def cv_predict_named(name: str, x: pd.DataFrame, y: pd.Series, test: pd.DataFrame, params: dict | None):
    if name == "CatBoost":
        return evaluate_catboost(x, y, folds=CV_SPLITS, seed=RANDOM_STATE, params=params, return_oof=True, test=test)
    model = build_sklearn_model(name, x, RANDOM_STATE, params)
    return cv_predict_pipeline(model, x, y, test, folds=CV_SPLITS, seed=RANDOM_STATE)


def make_model_charts(model_comparison: pd.DataFrame, multiseed: pd.DataFrame, ensemble: pd.DataFrame) -> None:
    sns.set_theme(style="whitegrid")
    ordered = model_comparison.sort_values("mean_roc_auc")
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.barh(ordered["model"], ordered["mean_roc_auc"], xerr=ordered["std_roc_auc"], color="#4C78A8")
    ax.set(title="Cross-Validated Model Comparison", xlabel="Mean ROC-AUC (5-fold)", ylabel="")
    ax.set_xlim(max(0.5, ordered["mean_roc_auc"].min() - 0.03), min(1.0, ordered["mean_roc_auc"].max() + 0.015))
    fig.tight_layout(); fig.savefig(FIGURE_DIR / "04_model_comparison.png", dpi=220); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    sns.pointplot(data=multiseed, x="seed", y="mean_auc", color="#E76F51", ax=ax)
    ax.set(title="Top Model Stability Across Random Seeds", xlabel="CV random seed", ylabel="Mean ROC-AUC")
    fig.tight_layout(); fig.savefig(FIGURE_DIR / "07_multiseed_stability.png", dpi=220); plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    plot = ensemble.sort_values("oof_auc")
    ax.barh(plot["method"], plot["oof_auc"], color="#2A9D8F")
    ax.set(title="OOF Ensemble Comparison", xlabel="OOF ROC-AUC", ylabel="")
    ax.set_xlim(plot["oof_auc"].min() - 0.002, plot["oof_auc"].max() + 0.001)
    fig.tight_layout(); fig.savefig(FIGURE_DIR / "08_ensemble_comparison.png", dpi=220); plt.close(fig)


def generate_reports(
    audit: dict[str, object],
    model_comparison: pd.DataFrame,
    ablation: pd.DataFrame,
    multiseed: pd.DataFrame,
    ensemble: pd.DataFrame,
    final_method: str,
    final_auc: float,
    importance: pd.DataFrame,
    segments: pd.DataFrame,
    segment_rates: pd.DataFrame,
    tune_names: list[str],
) -> None:
    top_features = importance.head(10)["feature"].tolist()
    top_segment = segments.iloc[0]
    business_auc = float(ensemble.loc[ensemble.method.eq("Multi-seed XGBoost Bagging"), "oof_auc"].iloc[0]) if ensemble.method.eq("Multi-seed XGBoost Bagging").any() else final_auc
    kaggle_path = AUDIT_DIR / "kaggle_result.json"
    kaggle = json.loads(kaggle_path.read_text(encoding="utf-8")) if kaggle_path.exists() else None
    kaggle_text = (
        f"Public ROC-AUC {kaggle['public_score']:.5f}; rank {kaggle['rank']:,}/{kaggle['teams']:,} (top {kaggle['top_percent']:.1f}%)"
        if kaggle else "Pending verified Kaggle submission"
    )
    kaggle_cn = f"；Kaggle 公榜 {kaggle['public_score']:.5f}、{kaggle['rank']}/{kaggle['teams']} 名" if kaggle else ""
    kaggle_kr = f" Kaggle Public AUC {kaggle['public_score']:.5f}, {kaggle['rank']}/{kaggle['teams']}위입니다." if kaggle else ""
    kaggle_en = f" and {kaggle['public_score']:.5f} Kaggle Public AUC (rank {kaggle['rank']}/{kaggle['teams']})" if kaggle else ""
    lookup = segment_rates.set_index(["segment_variable", "segment_value"])["purchase_rate"]

    def rate(variable: str, value: str) -> float:
        return float(lookup.get((variable, value), np.nan))

    income_rows = segment_rates[segment_rates.segment_variable.eq("Annual_Income_USD_quintile")].sort_values("segment_value")
    commute_rows = segment_rates[segment_rates.segment_variable.eq("Daily_Commute_km_quintile")].sort_values("segment_value")
    report = f"""# Business Report

## Executive finding

The analysis covers {audit['train_rows']:,} labelled customers. The observed EV-purchase-intent rate is {audit['positive_rate']:.2%}. Business segmentation uses the interpretable base-feature model (OOF ROC-AUC {business_auc:.6f}); the separate competition model reaches {final_auc:.6f}. Both measure ranking quality, not causal impact or guaranteed conversion.

## Answers to the business questions

1. **Highest-propensity customers.** `{top_segment['customer_segment']}` has the highest OOF predicted propensity ({top_segment['predicted_purchase_probability']:.2%}) and represents {top_segment['customer_share']:.2%} of labelled customers.
2. **Income.** Purchase rate moves from {income_rows.iloc[0].purchase_rate:.2%} in the lowest income quintile to {income_rows.iloc[-1].purchase_rate:.2%} in the highest; the relationship is descriptive, not causal.
3. **Subsidy.** Observed purchase rates are {rate('Subsidy_Available', 'Yes'):.2%} with subsidy availability and {rate('Subsidy_Available', 'No'):.2%} without it.
4. **Environmental concern.** Its model contribution is ranked #{top_features.index('Environmental_Concern_Level') + 1 if 'Environmental_Concern_Level' in top_features else '>10'} among the displayed SHAP drivers.
5. **Range anxiety.** Purchase rates are {rate('Range_Anxiety_Level', 'Low'):.2%} for low, {rate('Range_Anxiety_Level', 'Medium'):.2%} for medium, and {rate('Range_Anxiety_Level', 'High'):.2%} for high anxiety.
6. **Home charging.** Purchase rates are {rate('Home_Charging_Possible', 'Yes'):.2%} with home charging and {rate('Home_Charging_Possible', 'No'):.2%} without it.
7. **City type.** Urban, suburban and rural rates are {rate('City_Type', 'Urban'):.2%}, {rate('City_Type', 'Suburban'):.2%}, and {rate('City_Type', 'Rural'):.2%}.
8. **Commute.** The lowest and highest commute quintiles have purchase rates of {commute_rows.iloc[0].purchase_rate:.2%} and {commute_rows.iloc[-1].purchase_rate:.2%}.
9. **Interactions.** Feature ablation tests charging access, range pressure, income-per-car and motivation/infrastructure interactions; their value is judged by CV change rather than narrative plausibility.
10. **Priority audiences.** Start with High Potential; use different treatment for Infrastructure-Constrained, Eco-Motivated and Price-Sensitive groups rather than one generic campaign.

## Recommended actions

1. **Finding -> Evidence -> Interpretation -> Action:** High-propensity customers are concentrated in the top scored segment -> OOF mean {top_segment['predicted_purchase_probability']:.2%} -> the model can prioritize outreach -> pilot a ranked campaign and measure incremental conversion with a holdout group.
2. **Finding -> Evidence -> Interpretation -> Action:** Home charging status separates observed intent ({rate('Home_Charging_Possible', 'Yes'):.2%} vs {rate('Home_Charging_Possible', 'No'):.2%}) -> infrastructure is associated with readiness -> offer installation partnerships to otherwise promising customers.
3. **Finding -> Evidence -> Interpretation -> Action:** Subsidy availability separates observed intent ({rate('Subsidy_Available', 'Yes'):.2%} vs {rate('Subsidy_Available', 'No'):.2%}) -> financial support is associated with propensity -> surface eligibility and total-cost information in targeted messaging.
4. **Finding -> Evidence -> Interpretation -> Action:** Range-anxiety groups differ -> anxiety is a useful barrier signal -> tailor range, charging-network and trip-planning communication, then validate impact experimentally.

## Limits

The dataset is synthetic and the target is stated intent, not a recorded purchase. SHAP and segment comparisons explain model associations; they do not establish causality. Deployment would require calibration, fresh-data monitoring and randomized campaign tests.
"""
    (REPORT_DIR / "business_report.md").write_text(report, encoding="utf-8")

    best_model = model_comparison.sort_values("mean_roc_auc", ascending=False).iloc[0]
    model_report = f"""# Model Report

## Validation design

- Primary metric: ROC-AUC.
- Splitter: 5-fold shuffled StratifiedKFold, random state {RANDOM_STATE}.
- Preprocessing is fitted inside each fold. CatBoost receives native low-cardinality categorical fields.
- Secondary metrics: accuracy, precision, recall, F1 and log loss.

## Results

The strongest initial tree model was **{best_model.model}** at {best_model.mean_roc_auc:.6f} +/- {best_model.std_roc_auc:.6f}. Optuna was run for {OPTUNA_TRIALS} trials on each of {', '.join(tune_names)} using a fixed stratified sample of {min(OPTUNA_SAMPLE_SIZE, int(audit['train_rows'])):,} rows and 3-fold CV. Full-data validation remained 5-fold.

Business feature engineering was evaluated as BASE, FE_V1 and FE_V2. The selected deployable version was **{ablation.sort_values('mean_roc_auc', ascending=False).iloc[0].feature_version}**, and five-seed XGBoost bagging reached {business_auc:.6f}. A separate competition track added digit, frequency and fold-safe target-encoding features. The final Kaggle method was **{final_method}**, with OOF ROC-AUC **{final_auc:.6f}**.

Across five CV seeds, the top model mean ROC-AUC ranged from {multiseed.mean_auc.min():.6f} to {multiseed.mean_auc.max():.6f}, with an average of {multiseed.mean_auc.mean():.6f}. This audit is reported separately from the single-seed model-selection result.

Kaggle verification: **{kaggle_text}**.

## Why these models

Logistic regression tests whether mostly linear additive effects are sufficient. Random Forest supplies a bagged nonlinear baseline. XGBoost and LightGBM learn boosted decision rules efficiently; CatBoost additionally handles categorical variables natively. The ensemble is retained only when its OOF AUC exceeds the best component. Synthetic-artifact features are kept out of the business interpretation track because their predictive value may not transfer to real customers.

## Important limitations

Optuna used a stratified subsample and 12 trials per model to keep the search proportionate to local compute. These results are evidence for a good configuration, not proof of a global optimum. Kaggle public score is an external check and must not replace local validation.

An independently trained four-feature logistic model on the public 10,000-row source dataset transferred at 0.937619 AUC on the competition train set, so external labels were rejected rather than blended. The accepted competition gain comes from competition-train cross-validation, not copied predictions.
"""
    (REPORT_DIR / "model_report.md").write_text(model_report, encoding="utf-8")

    audit_report = f"""# Project Audit

- Source files: `train.csv`, `test.csv`, `sample_submission.csv` from Kaggle competition `playground-series-s6e9`.
- External-data check: public CC0 EV source dataset, used only for a rejected transfer experiment (AUC 0.937619), not final training.
- Rows: {audit['train_rows']:,} train; {audit['test_rows']:,} test.
- Target / ID: `{TARGET}` / `{ID_COLUMN}`.
- Missing cells: {audit['missing_cells_train']:,} train; {audit['missing_cells_test']:,} test.
- Duplicate IDs: {audit['train_duplicate_ids']:,} train; {audit['test_duplicate_ids']:,} test.
- CV: {CV_SPLITS}-fold stratified, seed {RANDOM_STATE}; stability seeds {list(VALIDATION_SEEDS)}.
- Models: Dummy, Logistic Regression, Random Forest, XGBoost, LightGBM, CatBoost.
- Feature versions: BASE, FE_V1, FE_V2.
- Optuna: {OPTUNA_TRIALS} trials per selected model, 3-fold stratified CV on up to {OPTUNA_SAMPLE_SIZE:,} rows.
- Business model: Multi-seed XGBoost Bagging; OOF ROC-AUC {business_auc:.6f}.
- Kaggle method: {final_method}; OOF ROC-AUC {final_auc:.6f}.
- Submission: `outputs/submissions/submission_final.csv`.
- Kaggle result: {kaggle_text}.
- Metric sources: `outputs/tables/*.csv`; audit sources: `outputs/audit/*`; plots: `outputs/figures/*`.
"""
    (REPORT_DIR / "project_audit.md").write_text(audit_report, encoding="utf-8")

    powerbi = """# Power BI Dashboard Specification

## Page 1: Executive Overview

Use KPI cards for customers, observed purchase rate, mean predicted propensity and High Potential share. Add a segment bar chart and slicers for city, vehicle type and subsidy. Source: `customer_overview.csv` and `segment_analysis.csv`.

## Page 2: Customer Profile

Use age and income histograms, a city-type bar chart and a vehicle-type stacked bar. Axis: customer count or observed purchase rate; filters: segment, gender and charging status. Business question: which profiles combine scale and propensity?

## Page 3: Purchase Drivers

Use a horizontal feature-importance bar from `feature_driver.csv`, plus clustered bars for subsidy, environmental concern, range anxiety and charging. Business question: which attributes are associated with model scores and observed intent?

## Page 4: Customer Segments

Use a segment comparison matrix with customer count, share, predicted propensity, observed rate, income and charging share. Add a scatter plot: X = customer share, Y = propensity, size = customer count. Business question: where should differentiated campaigns focus?

The environment does not create a genuine `.pbix`; the supplied CSVs are Power BI-ready and the specification avoids a fake binary file.
"""
    (REPORT_DIR / "powerbi_dashboard_spec.md").write_text(powerbi, encoding="utf-8")

    sql_guide = """# SQL Learning Guide

- `00_schema.sql` creates one customer-level table because the source is a single wide customer dataset; no fictional order tables are introduced.
- `01_data_quality.sql` checks row count, NULLs, duplicate IDs and domain violations before analysis.
- `02_customer_profile.sql` uses `CASE WHEN` to create readable age and income buckets, then `GROUP BY` to compare customer profiles.
- `03_purchase_propensity.sql` uses a CTE so the derived charging-access band is defined once and reused cleanly.
- `04_segment_analysis.sql` uses CTEs and window functions. `AVG() OVER()` supplies the overall benchmark while `RANK()` orders segments without collapsing the result.
- `05_business_kpi.sql` reports only customer analytics supported by this dataset: intent rate, charging access, subsidy availability and segment propensity. It does not invent GMV, CAC or LTV.

There is no natural multi-table relationship in the source, so a `JOIN` is intentionally absent. Adding one only to demonstrate syntax would misrepresent the data model.
"""
    (REPORT_DIR / "sql_learning_guide.md").write_text(sql_guide, encoding="utf-8")

    cn = f"""# 简历项目要点

- 基于 {int(audit['train_rows']) / 10000:.1f} 万条客户记录构建电动车购买倾向分析流程，完成数据质量审计、业务分群与 Power BI 数据准备。
- 采用 5 折分层交叉验证比较 6 类模型，并通过特征消融、多随机种子审计与 OOF 融合，将最终验证 ROC-AUC 提升至 {final_auc:.4f}{kaggle_cn}。
- 结合 SHAP 与规则型客户分群识别关键购买关联因素，形成可执行的优先触达、充电支持与补贴沟通建议。
"""
    kr = f"""# 이력서 프로젝트 요약

- {int(audit['train_rows']) / 10000:.1f}만 건의 고객 데이터를 기반으로 EV 구매 성향 분석 파이프라인을 구축하고 데이터 품질 점검, 고객 세분화, Power BI용 데이터를 완성했습니다.
- 5-fold Stratified CV로 6개 모델을 비교하고 feature ablation, multi-seed audit, OOF blending을 적용해 최종 ROC-AUC {final_auc:.4f}를 기록했습니다.{kaggle_kr}
- SHAP과 규칙 기반 세그먼트를 결합해 주요 구매 연관 요인을 해석하고 타깃 마케팅, 충전 지원, 보조금 커뮤니케이션 방안을 제안했습니다.
"""
    en = f"""# Resume Project Bullets

- Built an end-to-end EV purchase propensity workflow on {int(audit['train_rows']):,} customer records, covering data-quality audit, business segmentation and Power BI-ready outputs.
- Compared six model families with 5-fold stratified CV, then applied feature ablation, multi-seed validation and OOF blending to reach {final_auc:.4f} OOF ROC-AUC{kaggle_en}.
- Combined SHAP with interpretable customer segments to identify purchase-associated drivers and propose targeted outreach, charging-support and subsidy-communication actions.
"""
    (REPORT_DIR / "resume_bullets_CN.md").write_text(cn, encoding="utf-8")
    (REPORT_DIR / "resume_bullets_KR.md").write_text(kr, encoding="utf-8")
    (REPORT_DIR / "resume_bullets_EN.md").write_text(en, encoding="utf-8")

    readme = f"""# EV Purchase Propensity & Customer Analytics

This portfolio project turns {audit['train_rows']:,} synthetic customer records into a validated EV-purchase propensity model and an actionable customer-segmentation workflow.

## Business Problem

Rank customers by EV purchase intent, explain the associated drivers and identify audiences for differentiated campaigns without presenting model associations as causal effects.

## Dataset

The [Kaggle Playground Series S6E9](https://www.kaggle.com/competitions/playground-series-s6e9/overview) provides {audit['train_rows']:,} labelled rows, {audit['test_rows']:,} test rows and 13 customer, infrastructure and motivation features. The target is `Will_Buy_EV`; raw competition data are excluded from Git.

## Analytics Workflow

Data audit -> business EDA -> baselines -> boosted-tree comparison -> Optuna tuning -> feature ablation -> multi-seed audit -> business SHAP/segments -> synthetic-artifact competition model -> OOF blend -> Kaggle submission.

## Model Validation

All primary comparisons use shuffled 5-fold StratifiedKFold. Preprocessing and target encoding are fitted within training folds. Five random seeds test split stability, and blend weights are selected only from out-of-fold predictions.

## Key Results

- Competition OOF ROC-AUC: **{final_auc:.6f}** using **{final_method}**.
- Business-model OOF ROC-AUC: **{business_auc:.6f}** using base-feature five-seed XGBoost bagging.
- Validation: 5-fold StratifiedKFold plus five-seed stability audit.
- Leading drivers: {', '.join(top_features[:6])}.
- Highest-priority segment: **{top_segment['customer_segment']}** ({top_segment['customer_share']:.1%} of labelled customers; {top_segment['predicted_purchase_probability']:.1%} mean OOF propensity).
- Kaggle result: **{kaggle_text}**.

## Customer Insights

See [`reports/business_report.md`](reports/business_report.md) for evidence on income, subsidies, charging, environmental concern, range anxiety, city type and commute distance.

## Business Recommendations

Prioritize scored High Potential customers, tailor infrastructure support for customers without home charging, and test subsidy/range messaging with randomized holdouts before scaling.

## Kaggle Result

{kaggle_text}. This is a public-leaderboard snapshot; the private final ranking can change when the competition closes.

## SQL Analytics

MySQL 8 scripts in `sql/` cover data quality, customer profiles, propensity segments, window functions and supported business KPIs without inventing transaction metrics.

## Power BI

Dashboard-ready local CSVs are generated under `outputs/dashboard/`; the four-page design is documented in `reports/powerbi_dashboard_spec.md`.

## Repository Structure

`src/` contains reusable pipeline code, `notebooks/` the executed narrative, `reports/` recruiter-facing findings, and `outputs/` validated metrics and figures. Raw and row-level competition data are excluded from Git.

## Reproducibility

```bash
python -m pip install -r requirements.txt
python src/run_pipeline.py
python src/run_validation_audit.py
python src/external_data_check.py
python src/advanced_model.py
python src/refresh_outputs.py
```

Place official Kaggle files in `data/raw/`. The pipeline uses relative paths and a single random-state configuration.

## Limitations

The competition data are synthetic and the target is intent rather than observed purchase. Optuna uses a bounded stratified sample to control local compute. Digit/frequency features are competition-specific and excluded from business interpretation. External deployment requires probability calibration, drift monitoring and campaign experiments.
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")


def build_notebook() -> None:
    sections = [
        ("Executive Summary", "Display the validated result and the portfolio decision context.", "display(pd.read_csv(ROOT/'outputs/tables/ensemble_results.csv'))"),
        ("Data Overview", "Confirm sample scale, fields and target.", "display(pd.read_csv(ROOT/'outputs/audit/data_schema.csv'))"),
        ("Data Quality", "Missingness, duplicate and distribution-shift checks precede modeling.", "display(pd.read_csv(ROOT/'outputs/audit/missing_values.csv')); display(pd.read_csv(ROOT/'outputs/audit/train_test_shift.csv').head(10))"),
        ("Business EDA", "Compare actionable customer attributes against the overall purchase-intent rate.", "display(Image(filename=str(ROOT/'outputs/figures/02_actionable_segment_rates.png')))"),
        ("Baseline", "Dummy and logistic models establish whether the feature set carries useful signal.", "display(pd.read_csv(ROOT/'outputs/tables/baseline_results.csv'))"),
        ("Model Comparison", "Tree ensembles test nonlinearities and interactions under the same folds.", "display(pd.read_csv(ROOT/'outputs/tables/model_comparison.csv')); display(Image(filename=str(ROOT/'outputs/figures/04_model_comparison.png')))"),
        ("Feature Engineering", "Business-derived interactions are retained only when CV supports them.", "display(pd.read_csv(ROOT/'outputs/tables/feature_ablation.csv'))"),
        ("Hyperparameter Tuning", "A bounded Optuna search balances rigor with local compute.", "display(pd.read_csv(ROOT/'outputs/tables/optuna_results.csv').sort_values('value', ascending=False).head(10))"),
        ("Validation Audit", "Five random seeds test whether a favorable split drives the result.", "display(pd.read_csv(ROOT/'outputs/tables/multiseed_validation.csv'))"),
        ("Ensemble", "OOF predictions determine blend weights without consulting the leaderboard.", "display(pd.read_csv(ROOT/'outputs/tables/ensemble_results.csv')); display(pd.read_csv(ROOT/'outputs/tables/oof_correlation.csv'))"),
        ("Model Explainability", "SHAP attributes model predictions but does not establish causality.", "display(Image(filename=str(ROOT/'outputs/figures/06_shap_summary.png')))"),
        ("Customer Segmentation", "Rules combine propensity and actionable customer characteristics.", "display(pd.read_csv(ROOT/'outputs/tables/customer_segments.csv'))"),
        ("Business Insights", "Observed rates and model explanations support each conclusion.", "print((ROOT/'reports/business_report.md').read_text(encoding='utf-8')[:3500])"),
        ("Recommendation", "Campaigns should be validated with holdouts before scale-up.", "display(pd.read_csv(ROOT/'outputs/tables/customer_segments.csv').head(4))"),
        ("Kaggle Submission", "The file is checked for schema, order, missingness and probability bounds.", "display(pd.read_csv(ROOT/'outputs/submissions/submission_final.csv').head()); print((ROOT/'outputs/audit/submission_qa.md').read_text(encoding='utf-8')); print((ROOT/'outputs/audit/kaggle_result.json').read_text(encoding='utf-8') if (ROOT/'outputs/audit/kaggle_result.json').exists() else 'Kaggle result pending')"),
        ("Limitations", "Synthetic stated-intent data, bounded tuning and non-causal explanations limit direct deployment.", "print((ROOT/'reports/project_audit.md').read_text(encoding='utf-8'))"),
    ]
    nb = nbformat.v4.new_notebook()
    nb.metadata.kernelspec = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.cells.append(nbformat.v4.new_markdown_cell("# EV Purchase Propensity & Customer Analytics\n\nExecuted portfolio notebook. All figures and metrics are loaded from the reproducible pipeline outputs."))
    nb.cells.append(nbformat.v4.new_code_cell("from pathlib import Path\nimport pandas as pd\nfrom IPython.display import Image, display\nROOT = Path.cwd().resolve().parent if Path.cwd().name == 'notebooks' else Path.cwd().resolve()"))
    for title, description, code in sections:
        nb.cells.append(nbformat.v4.new_markdown_cell(f"## {title}\n\n{description}"))
        nb.cells.append(nbformat.v4.new_code_cell(code))
    path = NOTEBOOK_DIR / "EV_Purchase_Analytics_Final.ipynb"
    NotebookClient(nb, timeout=180, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).execute()
    nbformat.write(nb, path)


def main() -> None:
    start = time.perf_counter()
    ensure_directories()
    train, test, sample = load_data()
    audit = audit_data(train, test)
    create_eda_outputs(train)
    y = train[TARGET].eq("Yes").astype(int)

    x_base = add_features(train, "BASE")
    baseline_rows = []
    for name in ["Dummy", "Logistic Regression"]:
        summary, detail = evaluate_named(name, x_base, y)
        baseline_rows.append(row(name, summary))
        detail.assign(model=name).to_csv(TABLE_DIR / f"folds_{name.lower().replace(' ', '_')}.csv", index=False)
    baseline = pd.DataFrame(baseline_rows)
    baseline.to_csv(TABLE_DIR / "baseline_results.csv", index=False)

    x_v1 = add_features(train, "FE_V1")
    tree_rows = []
    for name in ["Random Forest", "XGBoost", "LightGBM", "CatBoost"]:
        summary, detail = evaluate_named(name, x_v1, y)
        tree_rows.append(row(name, summary))
        pd.DataFrame(tree_rows).to_csv(TABLE_DIR / "model_comparison_partial.csv", index=False)
        detail.assign(model=name).to_csv(TABLE_DIR / f"folds_{name.lower().replace(' ', '_')}.csv", index=False)
        print(f"{name}: {summary['mean_roc_auc']:.6f}", flush=True)
    comparison = pd.DataFrame(tree_rows).sort_values("mean_roc_auc", ascending=False).reset_index(drop=True)
    comparison.to_csv(TABLE_DIR / "model_comparison.csv", index=False)

    tunable = comparison[comparison.model.isin(["CatBoost", "LightGBM", "XGBoost"])].head(2).model.tolist()
    best_params: dict[str, dict] = {}
    histories = []
    for name in tunable:
        params, history = tune_model(name, x_v1, y)
        best_params[name] = params
        histories.append(history)
        print(f"Tuned {name}: {history.value.max():.6f}", flush=True)
    pd.concat(histories, ignore_index=True).to_csv(TABLE_DIR / "optuna_results.csv", index=False)
    (MODEL_DIR / "best_params.json").write_text(json.dumps(best_params, indent=2), encoding="utf-8")

    top_name = tunable[0]
    ablation_rows = []
    for version in ["BASE", "FE_V1", "FE_V2"]:
        x_version = add_features(train, version)
        summary, _ = evaluate_named(top_name, x_version, y, best_params[top_name])
        ablation_rows.append({"feature_version": version, "feature_count": x_version.shape[1], **summary})
    ablation = pd.DataFrame(ablation_rows).sort_values("mean_roc_auc", ascending=False)
    ablation.to_csv(TABLE_DIR / "feature_ablation.csv", index=False)
    feature_version = str(ablation.iloc[0].feature_version)
    x = add_features(train, feature_version)
    xt = add_features(test, feature_version)

    candidates: dict[str, dict[str, object]] = {}
    for name in tunable:
        result = cv_predict_named(name, x, y, xt, best_params[name])
        summary, detail, oof, test_pred, models = result
        candidates[name] = {"summary": summary, "oof": oof, "test": test_pred, "models": models}
        detail.assign(model=name).to_csv(TABLE_DIR / f"final_folds_{name.lower()}.csv", index=False)
        joblib.dump(models, MODEL_DIR / f"{name.lower()}_fold_models.joblib", compress=3)

    names = list(candidates)
    oof_frame = pd.DataFrame({name: candidates[name]["oof"] for name in names})
    oof_frame.corr().to_csv(TABLE_DIR / "oof_correlation.csv")
    ensemble_rows = [{"method": name, "oof_auc": roc_auc_score(y, candidates[name]["oof"]), "weights": name} for name in names]
    simple_oof = np.mean([candidates[n]["oof"] for n in names], axis=0)
    simple_test = np.mean([candidates[n]["test"] for n in names], axis=0)
    ensemble_rows.append({"method": "Simple Average", "oof_auc": roc_auc_score(y, simple_oof), "weights": "equal"})
    ranks_oof = np.mean([pd.Series(candidates[n]["oof"]).rank(pct=True).to_numpy() for n in names], axis=0)
    ranks_test = np.mean([pd.Series(candidates[n]["test"]).rank(pct=True).to_numpy() for n in names], axis=0)
    ensemble_rows.append({"method": "Rank Average", "oof_auc": roc_auc_score(y, ranks_oof), "weights": "equal percentile ranks"})

    if len(names) == 2:
        weights = np.linspace(0, 1, 41)
        scores = [roc_auc_score(y, w * candidates[names[0]]["oof"] + (1 - w) * candidates[names[1]]["oof"]) for w in weights]
        w = float(weights[int(np.argmax(scores))])
        weighted_oof = w * candidates[names[0]]["oof"] + (1 - w) * candidates[names[1]]["oof"]
        weighted_test = w * candidates[names[0]]["test"] + (1 - w) * candidates[names[1]]["test"]
        weight_text = f"{names[0]}={w:.3f}; {names[1]}={1-w:.3f}"
        ensemble_rows.append({"method": "Weighted Blend", "oof_auc": roc_auc_score(y, weighted_oof), "weights": weight_text})
    ensemble = pd.DataFrame(ensemble_rows).sort_values("oof_auc", ascending=False).reset_index(drop=True)
    ensemble.to_csv(TABLE_DIR / "ensemble_results.csv", index=False)
    final_method = str(ensemble.iloc[0].method)
    if final_method == "Weighted Blend":
        final_oof, final_test = weighted_oof, weighted_test
    elif final_method == "Simple Average":
        final_oof, final_test = simple_oof, simple_test
    elif final_method == "Rank Average":
        final_oof, final_test = ranks_oof, ranks_test
    else:
        final_oof, final_test = candidates[final_method]["oof"], candidates[final_method]["test"]
    final_auc = roc_auc_score(y, final_oof)

    stability_name = str(ensemble[ensemble.method.isin(names)].sort_values("oof_auc", ascending=False).iloc[0].method)
    multiseed_rows = []
    for seed in VALIDATION_SEEDS:
        if seed == RANDOM_STATE:
            fold_auc = pd.read_csv(TABLE_DIR / f"final_folds_{stability_name.lower()}.csv")["roc_auc"]
        else:
            summary, detail = evaluate_named(stability_name, x, y, best_params[stability_name], seed=seed)
            fold_auc = detail["roc_auc"]
        multiseed_rows.append({"seed": seed, "mean_auc": fold_auc.mean(), "std_auc": fold_auc.std(ddof=1), "min_auc": fold_auc.min(), "max_auc": fold_auc.max()})
    multiseed = pd.DataFrame(multiseed_rows)
    multiseed.to_csv(TABLE_DIR / "multiseed_validation.csv", index=False)

    single_scores = ensemble[ensemble.method.isin(names)].sort_values("oof_auc", ascending=False)
    explanation_name = stability_name
    explanation_model = build_sklearn_model(explanation_name, x, RANDOM_STATE, best_params[explanation_name])
    explanation_model.fit(x, y)
    joblib.dump(explanation_model, MODEL_DIR / f"{explanation_name.lower()}_final_model.joblib", compress=3)
    importance = explain_tree_pipeline(explanation_model, x)
    pd.DataFrame({ID_COLUMN: train[ID_COLUMN], "actual": y, "oof_prediction": final_oof}).to_csv(PROCESSED_DIR / "train_oof_predictions.csv", index=False)
    pd.DataFrame({ID_COLUMN: test[ID_COLUMN], "prediction": final_test}).to_csv(PROCESSED_DIR / "test_predictions.csv", index=False)
    segments = create_business_outputs(train, test, final_oof, final_test, importance)

    submission = pd.DataFrame({ID_COLUMN: sample[ID_COLUMN], TARGET: final_test})
    if len(submission) != len(sample) or not submission[ID_COLUMN].equals(sample[ID_COLUMN]):
        raise AssertionError("Submission IDs do not match sample submission")
    if submission[TARGET].isna().any() or not np.isfinite(submission[TARGET]).all() or not submission[TARGET].between(0, 1).all():
        raise AssertionError("Invalid submission probabilities")
    submission.to_csv(SUBMISSION_DIR / "submission_final.csv", index=False)
    qa = f"""# Submission QA

- Rows: {len(submission):,} (expected {len(sample):,}) - PASS
- Columns: {submission.columns.tolist()} - PASS
- ID order matches sample submission: {submission[ID_COLUMN].equals(sample[ID_COLUMN])} - PASS
- Duplicate IDs: {submission[ID_COLUMN].duplicated().sum()} - PASS
- Missing probabilities: {submission[TARGET].isna().sum()} - PASS
- Infinite probabilities: {(~np.isfinite(submission[TARGET])).sum()} - PASS
- Probability range: [{submission[TARGET].min():.8f}, {submission[TARGET].max():.8f}] - PASS
"""
    (AUDIT_DIR / "submission_qa.md").write_text(qa, encoding="utf-8")

    segment_rates = pd.read_csv(TABLE_DIR / "purchase_rate_by_segment.csv")
    make_model_charts(comparison, multiseed, ensemble)
    generate_reports(audit, comparison, ablation, multiseed, ensemble, final_method, final_auc, importance, segments, segment_rates, tunable)
    build_notebook()
    print(json.dumps({"final_method": final_method, "final_auc": final_auc, "feature_version": feature_version, "top_features": importance.head(10).feature.tolist(), "elapsed_minutes": (time.perf_counter() - start) / 60}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
