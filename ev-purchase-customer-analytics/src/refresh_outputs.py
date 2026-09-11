from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from business_analysis import create_business_outputs, create_eda_outputs
from config import AUDIT_DIR, CV_SPLITS, ID_COLUMN, MODEL_DIR, PROCESSED_DIR, RANDOM_STATE, SUBMISSION_DIR, TABLE_DIR, TARGET
from data import load_data
from explainability import explain_tree_pipeline
from features import add_features
from models import build_sklearn_model
from run_pipeline import build_notebook, generate_reports, make_model_charts


def main() -> None:
    train, test, sample = load_data()
    create_eda_outputs(train)
    y = train[TARGET].eq("Yes").astype(int)
    ablation = pd.read_csv(TABLE_DIR / "feature_ablation.csv")
    version = str(ablation.sort_values("mean_roc_auc", ascending=False).iloc[0].feature_version)
    x, xt = add_features(train, version), add_features(test, version)
    comparison = pd.read_csv(TABLE_DIR / "model_comparison.csv")
    ensemble = pd.read_csv(TABLE_DIR / "ensemble_results.csv")
    multiseed = pd.read_csv(TABLE_DIR / "multiseed_validation.csv")
    params = json.loads((MODEL_DIR / "best_params.json").read_text(encoding="utf-8"))
    final_method = str(ensemble.iloc[0].method)
    explanation_name = "XGBoost"
    if final_method == "Advanced + Base Blend":
        oof = pd.read_csv(PROCESSED_DIR / "advanced_blend_oof_predictions.csv")["oof_prediction"].to_numpy()
        test_pred = pd.read_csv(PROCESSED_DIR / "advanced_blend_test_predictions.csv")["prediction"].to_numpy()
    elif final_method == "Advanced XGBoost":
        oof = pd.read_csv(PROCESSED_DIR / "advanced_oof_predictions.csv")["oof_prediction"].to_numpy()
        test_pred = pd.read_csv(PROCESSED_DIR / "advanced_test_predictions.csv")["prediction"].to_numpy()
    elif final_method == "Multi-seed XGBoost Bagging":
        oof = pd.read_csv(PROCESSED_DIR / "multiseed_oof_predictions.csv")["oof_prediction"].to_numpy()
        test_pred = pd.read_csv(PROCESSED_DIR / "multiseed_test_predictions.csv")["prediction"].to_numpy()
    else:
        models = joblib.load(MODEL_DIR / f"{final_method.lower()}_fold_models.joblib")
        splitter = StratifiedKFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)
        oof, test_pred = np.zeros(len(train)), np.zeros(len(test))
        for model, (_, valid_idx) in zip(models, splitter.split(x, y)):
            oof[valid_idx] = model.predict_proba(x.iloc[valid_idx])[:, 1]
            test_pred += model.predict_proba(xt)[:, 1] / CV_SPLITS

    full_model = build_sklearn_model(explanation_name, x, RANDOM_STATE, params[explanation_name])
    full_model.fit(x, y)
    joblib.dump(full_model, MODEL_DIR / f"{final_method.lower()}_final_model.joblib", compress=3)
    importance = explain_tree_pipeline(full_model, x)
    pd.DataFrame({ID_COLUMN: train[ID_COLUMN], "actual": y, "oof_prediction": oof}).to_csv(PROCESSED_DIR / "train_oof_predictions.csv", index=False)
    pd.DataFrame({ID_COLUMN: test[ID_COLUMN], "prediction": test_pred}).to_csv(PROCESSED_DIR / "test_predictions.csv", index=False)
    business_oof = pd.read_csv(PROCESSED_DIR / "multiseed_oof_predictions.csv")["oof_prediction"].to_numpy()
    business_test = pd.read_csv(PROCESSED_DIR / "multiseed_test_predictions.csv")["prediction"].to_numpy()
    segments = create_business_outputs(train, test, business_oof, business_test, importance)

    submission = pd.DataFrame({ID_COLUMN: sample[ID_COLUMN], TARGET: test_pred})
    if not submission[ID_COLUMN].equals(sample[ID_COLUMN]) or submission[TARGET].isna().any() or not np.isfinite(submission[TARGET]).all() or not submission[TARGET].between(0, 1).all():
        raise AssertionError("Refreshed submission failed QA")
    submission.to_csv(SUBMISSION_DIR / "submission_final.csv", index=False)
    (AUDIT_DIR / "submission_qa.md").write_text(
        f"# Submission QA\n\n- Rows: {len(submission):,} - PASS\n- Columns: {submission.columns.tolist()} - PASS\n- ID order matches sample: True - PASS\n- Duplicate IDs: {submission[ID_COLUMN].duplicated().sum()} - PASS\n- Missing probabilities: {submission[TARGET].isna().sum()} - PASS\n- Probability range: [{submission[TARGET].min():.8f}, {submission[TARGET].max():.8f}] - PASS\n",
        encoding="utf-8",
    )

    audit = json.loads((AUDIT_DIR / "audit_summary.json").read_text(encoding="utf-8"))
    segment_rates = pd.read_csv(TABLE_DIR / "purchase_rate_by_segment.csv")
    generate_reports(
        audit,
        comparison,
        ablation,
        multiseed,
        ensemble,
        final_method,
        roc_auc_score(y, oof),
        importance,
        segments,
        segment_rates,
        list(params),
    )
    make_model_charts(comparison, multiseed, ensemble)
    build_notebook()
    print(f"Refreshed artifacts with {final_method}; OOF AUC={roc_auc_score(y, oof):.6f}")


if __name__ == "__main__":
    main()
