from __future__ import annotations

import json
import math
import sys
import warnings
from datetime import datetime
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import (
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold, cross_val_predict
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from titanic_core import (  # noqa: E402
    FEATURE_SETS,
    PRIMARY_SEED,
    RANDOM_SEEDS,
    FeatureBuilder,
    add_group_features,
    audit_data,
    basic_features,
    build_fold_data,
    evaluate_on_folds,
    feature_columns,
    find_data,
    full_training_matrices,
    make_preprocessor,
    save_json,
    score_metrics,
)

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

OUTPUT = PROJECT_ROOT / "outputs"
TABLES = OUTPUT / "tables"
FIGURES = OUTPUT / "figures"
MODELS = OUTPUT / "models"
SUBMISSIONS = OUTPUT / "submissions"
for directory in [OUTPUT, TABLES, FIGURES, MODELS, SUBMISSIONS]:
    directory.mkdir(parents=True, exist_ok=True)


def model_factory(name: str, params: dict | None = None):
    params = dict(params or {})
    if name == "LogisticRegression":
        defaults = {"C": 0.5, "max_iter": 3000, "random_state": PRIMARY_SEED}
        return LogisticRegression(**(defaults | params))
    if name == "SVC":
        defaults = {"C": 2.0, "gamma": "scale", "probability": True, "random_state": PRIMARY_SEED}
        return SVC(**(defaults | params))
    if name == "KNN":
        defaults = {"n_neighbors": 13, "weights": "distance", "p": 2}
        return KNeighborsClassifier(**(defaults | params))
    if name == "RandomForest":
        defaults = {"n_estimators": 500, "max_depth": 6, "min_samples_leaf": 2, "max_features": "sqrt", "random_state": PRIMARY_SEED, "n_jobs": -1}
        return RandomForestClassifier(**(defaults | params))
    if name == "ExtraTrees":
        defaults = {"n_estimators": 500, "max_depth": 8, "min_samples_leaf": 2, "max_features": 0.8, "random_state": PRIMARY_SEED, "n_jobs": -1}
        return ExtraTreesClassifier(**(defaults | params))
    if name == "GradientBoosting":
        defaults = {"n_estimators": 160, "learning_rate": 0.03, "max_depth": 3, "min_samples_leaf": 3, "subsample": 0.9, "random_state": PRIMARY_SEED}
        return GradientBoostingClassifier(**(defaults | params))
    if name == "HistGradientBoosting":
        defaults = {"max_iter": 180, "learning_rate": 0.05, "max_leaf_nodes": 15, "l2_regularization": 2.0, "random_state": PRIMARY_SEED}
        return HistGradientBoostingClassifier(**(defaults | params))
    if name == "XGBoost":
        from xgboost import XGBClassifier

        defaults = {"n_estimators": 350, "learning_rate": 0.025, "max_depth": 3, "min_child_weight": 3, "subsample": 0.85, "colsample_bytree": 0.85, "reg_alpha": 0.05, "reg_lambda": 2.0, "eval_metric": "logloss", "random_state": PRIMARY_SEED, "n_jobs": -1}
        return XGBClassifier(**(defaults | params))
    if name == "LightGBM":
        from lightgbm import LGBMClassifier

        defaults = {"n_estimators": 300, "learning_rate": 0.025, "num_leaves": 15, "max_depth": 5, "min_child_samples": 20, "subsample": 0.85, "colsample_bytree": 0.85, "reg_alpha": 0.05, "reg_lambda": 2.0, "random_state": PRIMARY_SEED, "n_jobs": -1, "verbosity": -1}
        return LGBMClassifier(**(defaults | params))
    if name == "CatBoost":
        from catboost import CatBoostClassifier

        defaults = {"iterations": 400, "learning_rate": 0.03, "depth": 5, "l2_leaf_reg": 5.0, "loss_function": "Logloss", "random_seed": PRIMARY_SEED, "verbose": False, "allow_writing_files": False, "thread_count": -1}
        return CatBoostClassifier(**(defaults | params))
    raise KeyError(name)


SCALED_MODELS = {"LogisticRegression", "SVC", "KNN"}
MODEL_NAMES = [
    "LogisticRegression", "SVC", "KNN", "RandomForest", "ExtraTrees",
    "GradientBoosting", "HistGradientBoosting", "XGBoost", "LightGBM", "CatBoost",
]


def make_data_audit(train: pd.DataFrame, test: pd.DataFrame, sample: pd.DataFrame | None, paths: tuple[Path, Path, Path | None]) -> None:
    audit = audit_data(train, test, sample)
    audit["source_paths"] = [str(path) if path else None for path in paths]
    audit["metric"] = "Accuracy"
    audit["target"] = "Survived"
    save_json(audit, TABLES / "data_audit.json")

    rows = []
    for dataset_name, frame in [("train", train), ("test", test)]:
        for column in frame.columns:
            rows.append({
                "Dataset": dataset_name,
                "Column": column,
                "Dtype": str(frame[column].dtype),
                "Missing": int(frame[column].isna().sum()),
                "MissingRate": frame[column].isna().mean(),
                "Unique": frame[column].nunique(dropna=True),
            })
    pd.DataFrame(rows).to_csv(TABLES / "data_profile.csv", index=False)

    drift_rows = []
    for column in ["Pclass", "Sex", "Age", "SibSp", "Parch", "Fare", "Embarked"]:
        if pd.api.types.is_numeric_dtype(train[column]):
            pooled = pd.concat([train[column], test[column]]).std()
            distance = abs(train[column].mean() - test[column].mean()) / pooled if pooled else 0
            method = "standardized_mean_difference"
        else:
            levels = sorted(set(train[column].dropna()) | set(test[column].dropna()))
            train_share = train[column].value_counts(normalize=True).reindex(levels, fill_value=0)
            test_share = test[column].value_counts(normalize=True).reindex(levels, fill_value=0)
            distance = 0.5 * abs(train_share - test_share).sum()
            method = "total_variation_distance"
        drift_rows.append({"Feature": column, "Method": method, "Distance": distance})
    pd.DataFrame(drift_rows).to_csv(TABLES / "train_test_distribution_check.csv", index=False)


def cache_key(feature_set: str, seed: int, age_strategy: str, child_age: int, combined: bool) -> tuple:
    return feature_set, seed, age_strategy, child_age, combined


def main() -> None:
    train_path, test_path, sample_path = find_data(PROJECT_ROOT)
    train, test = pd.read_csv(train_path), pd.read_csv(test_path)
    sample = pd.read_csv(sample_path) if sample_path else None
    make_data_audit(train, test, sample, (train_path, test_path, sample_path))
    y = train["Survived"].astype(int).to_numpy()

    fold_cache: dict[tuple, list] = {}
    experiment_log: list[dict] = []
    experiment_results: list[dict] = []
    prediction_store: dict[str, dict[str, np.ndarray]] = {}

    def get_folds(feature_set: str, seed: int, age_strategy: str = "smart", child_age: int = 16, combined: bool = True):
        key = cache_key(feature_set, seed, age_strategy, child_age, combined)
        if key not in fold_cache:
            fold_cache[key] = build_fold_data(train, test, feature_set, seed, age_strategy, child_age, combined)
        return fold_cache[key]

    def evaluate(
        experiment: str,
        name: str,
        feature_set: str,
        seeds: list[int],
        params: dict | None = None,
        age_strategy: str = "smart",
        child_age: int = 16,
        combined: bool = True,
        store: bool = False,
    ) -> dict:
        all_oof, all_test, all_folds = [], [], []
        for seed in seeds:
            folds = get_folds(feature_set, seed, age_strategy, child_age, combined)
            oof, test_probability, fold_metrics, _ = evaluate_on_folds(
                lambda: model_factory(name, params), folds, len(train), len(test), name in SCALED_MODELS
            )
            all_oof.append(oof)
            all_test.append(test_probability)
            for fold in fold_metrics:
                experiment_log.append({
                    "Timestamp": datetime.now().isoformat(timespec="seconds"),
                    "Experiment": experiment,
                    "FeatureSet": feature_set,
                    "Model": name,
                    "Parameters": json.dumps(params or {}, sort_keys=True),
                    "Seed": seed,
                    **fold,
                })
                all_folds.append(fold["Accuracy"])
        oof_probability = np.mean(all_oof, axis=0)
        test_probability = np.mean(all_test, axis=0)
        metrics = score_metrics(y, oof_probability)
        result = {
            "Experiment": experiment,
            "Model": name,
            "FeatureSet": feature_set,
            "Parameters": json.dumps(params or {}, sort_keys=True),
            "CVMean": float(np.mean(all_folds)),
            "CVStd": float(np.std(all_folds)),
            "CVMin": float(np.min(all_folds)),
            "CVMax": float(np.max(all_folds)),
            "OOFAccuracy": metrics["Accuracy"],
            "Precision": metrics["Precision"],
            "Recall": metrics["Recall"],
            "F1": metrics["F1"],
            "AUC": metrics["AUC"],
            "Threshold": 0.5,
            "Notes": f"seeds={seeds}; age={age_strategy}; child<{child_age}; combined_frequency={combined}",
        }
        experiment_results.append(result)
        if store:
            prediction_store[experiment] = {"oof": oof_probability, "test": test_probability}
        return result

    gender_probability = train["Sex"].eq("female").astype(float).to_numpy()
    gender_test = test["Sex"].eq("female").astype(float).to_numpy()
    gender_metrics = score_metrics(y, gender_probability)
    experiment_results.append({
        "Experiment": "B0_GenderRule", "Model": "GenderRule", "FeatureSet": "Sex only", "Parameters": "{}",
        "CVMean": gender_metrics["Accuracy"], "CVStd": 0.0, "CVMin": gender_metrics["Accuracy"], "CVMax": gender_metrics["Accuracy"],
        "OOFAccuracy": gender_metrics["Accuracy"], "Precision": gender_metrics["Precision"], "Recall": gender_metrics["Recall"],
        "F1": gender_metrics["F1"], "AUC": gender_metrics["AUC"], "Threshold": 0.5, "Notes": "female=1, male=0",
    })
    prediction_store["B0_GenderRule"] = {"oof": gender_probability, "test": gender_test}
    evaluate("B1_Logistic", "LogisticRegression", "E0_Basic", [PRIMARY_SEED], store=True)
    evaluate("B2_RandomForest", "RandomForest", "E0_Basic", [PRIMARY_SEED], store=True)

    ablation_rows = []
    previous = None
    for feature_set in FEATURE_SETS:
        result = evaluate(f"Ablation_{feature_set}", "LogisticRegression", feature_set, [PRIMARY_SEED])
        ablation_rows.append({
            "Experiment": feature_set,
            "FeaturesAdded": FEATURE_SETS[feature_set][-1],
            "NumFeatures": len(feature_columns(feature_set)),
            "CVMean": result["CVMean"],
            "CVStd": result["CVStd"],
            "OOFAccuracy": result["OOFAccuracy"],
            "DeltaVsPrevious": 0.0 if previous is None else result["OOFAccuracy"] - previous,
        })
        previous = result["OOFAccuracy"]
    pd.DataFrame(ablation_rows).to_csv(TABLES / "feature_ablation.csv", index=False)

    preprocessing_rows = []
    for age_strategy in ["median", "pclass_sex", "title_pclass", "smart"]:
        result = evaluate(f"Age_{age_strategy}", "GradientBoosting", "E7_Interactions", [PRIMARY_SEED], age_strategy=age_strategy)
        preprocessing_rows.append({"Experiment": f"Age_{age_strategy}", "OOFAccuracy": result["OOFAccuracy"], "CVMean": result["CVMean"], "CVStd": result["CVStd"]})
    for child_age in [14, 16, 18]:
        result = evaluate(f"ChildAge_{child_age}", "GradientBoosting", "E7_Interactions", [PRIMARY_SEED], child_age=child_age)
        preprocessing_rows.append({"Experiment": f"ChildAge_{child_age}", "OOFAccuracy": result["OOFAccuracy"], "CVMean": result["CVMean"], "CVStd": result["CVStd"]})
    for combined in [False, True]:
        result = evaluate(f"TicketFrequency_{'combined' if combined else 'train'}", "GradientBoosting", "E7_Interactions", [PRIMARY_SEED], combined=combined)
        preprocessing_rows.append({"Experiment": f"TicketFrequency_{'combined' if combined else 'train'}", "OOFAccuracy": result["OOFAccuracy"], "CVMean": result["CVMean"], "CVStd": result["CVStd"]})
    pd.DataFrame(preprocessing_rows).to_csv(TABLES / "preprocessing_experiments.csv", index=False)

    pool_rows = []
    for name in MODEL_NAMES:
        result = evaluate(f"Pool_{name}", name, "E10_Group", [PRIMARY_SEED], store=True)
        pool_rows.append(result)
        print(f"{name:22s} OOF={result['OOFAccuracy']:.5f} CV={result['CVMean']:.5f}")
    pool = pd.DataFrame(pool_rows).sort_values(["OOFAccuracy", "CVMean"], ascending=False)
    pool.to_csv(TABLES / "model_pool.csv", index=False)

    top_models = [name for name in pool["Model"] if name in {"CatBoost", "XGBoost", "LightGBM", "ExtraTrees", "RandomForest", "SVC"}][:4]
    tuned_params: dict[str, dict] = {}
    try:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        tune_folds = get_folds("E10_Group", PRIMARY_SEED)

        def suggest(trial, name: str) -> dict:
            if name == "CatBoost":
                return {"iterations": trial.suggest_int("iterations", 250, 650), "depth": trial.suggest_int("depth", 4, 7), "learning_rate": trial.suggest_float("learning_rate", 0.015, 0.08, log=True), "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 2, 12, log=True)}
            if name == "XGBoost":
                return {"n_estimators": trial.suggest_int("n_estimators", 180, 600), "max_depth": trial.suggest_int("max_depth", 2, 5), "learning_rate": trial.suggest_float("learning_rate", 0.015, 0.09, log=True), "min_child_weight": trial.suggest_int("min_child_weight", 1, 8), "subsample": trial.suggest_float("subsample", 0.7, 1.0), "colsample_bytree": trial.suggest_float("colsample_bytree", 0.65, 1.0), "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 8, log=True)}
            if name == "LightGBM":
                return {"n_estimators": trial.suggest_int("n_estimators", 180, 600), "num_leaves": trial.suggest_int("num_leaves", 7, 31), "max_depth": trial.suggest_int("max_depth", 3, 7), "learning_rate": trial.suggest_float("learning_rate", 0.015, 0.08, log=True), "min_child_samples": trial.suggest_int("min_child_samples", 12, 45), "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 8, log=True)}
            if name in {"ExtraTrees", "RandomForest"}:
                return {"n_estimators": trial.suggest_int("n_estimators", 300, 800), "max_depth": trial.suggest_int("max_depth", 4, 12), "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 6), "max_features": trial.suggest_float("max_features", 0.35, 1.0)}
            return {"C": trial.suggest_float("C", 0.4, 8, log=True), "gamma": trial.suggest_float("gamma", 0.002, 0.12, log=True)}

        for name in top_models:
            trials_path = TABLES / f"optuna_trials_{name}.csv"
            if trials_path.exists():
                completed_trials = pd.read_csv(trials_path)
                completed_trials = completed_trials.loc[completed_trials["state"].eq("COMPLETE")]
                if len(completed_trials) >= 50:
                    best_trial = completed_trials.loc[completed_trials["value"].idxmax()]
                    integer_params = {"iterations", "depth", "n_estimators", "max_depth", "min_child_weight", "num_leaves", "min_child_samples", "min_samples_leaf"}
                    tuned_params[name] = {
                        column.removeprefix("params_"): int(best_trial[column]) if column.removeprefix("params_") in integer_params else float(best_trial[column])
                        for column in completed_trials.columns
                        if column.startswith("params_") and pd.notna(best_trial[column])
                    }
                    continue

            def objective(trial):
                params = suggest(trial, name)
                _, _, metrics, _ = evaluate_on_folds(lambda: model_factory(name, params), tune_folds, len(train), len(test), name in SCALED_MODELS)
                scores = [row["Accuracy"] for row in metrics]
                return float(np.mean(scores) - 0.15 * np.std(scores))

            study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=PRIMARY_SEED))
            study.optimize(objective, n_trials=50, show_progress_bar=False)
            tuned_params[name] = study.best_params
            study.trials_dataframe().to_csv(TABLES / f"optuna_trials_{name}.csv", index=False)
    except Exception as error:
        save_json({"error": repr(error), "fallback": "default parameters"}, TABLES / "optuna_error.json")
        tuned_params = {name: {} for name in top_models}
    save_json(tuned_params, TABLES / "best_params.json")

    finalists = []
    for name in top_models:
        result = evaluate(f"Finalist_{name}", name, "E10_Group", RANDOM_SEEDS, params=tuned_params.get(name), store=True)
        finalists.append(result)
        print(f"FINAL {name:17s} OOF={result['OOFAccuracy']:.5f} multi-seed={result['CVMean']:.5f}±{result['CVStd']:.5f}")
    finalists_frame = pd.DataFrame(finalists).sort_values(["OOFAccuracy", "CVMean"], ascending=False)
    finalists_frame.to_csv(TABLES / "multi_seed_finalists.csv", index=False)
    group_stress_test(train, test, finalists_frame.iloc[0]["Model"], tuned_params.get(finalists_frame.iloc[0]["Model"], {}))

    candidate_names = finalists_frame["Experiment"].head(3).tolist()
    oof_matrix = np.column_stack([prediction_store[name]["oof"] for name in candidate_names])
    test_matrix = np.column_stack([prediction_store[name]["test"] for name in candidate_names])
    oof_predictions = pd.DataFrame({"PassengerId": train["PassengerId"], "Survived": y})
    for index, name in enumerate(candidate_names):
        oof_predictions[f"{name}_prob"] = oof_matrix[:, index]
    oof_predictions.to_csv(TABLES / "oof_predictions.csv", index=False)
    pd.DataFrame(oof_matrix, columns=candidate_names).corr().to_csv(TABLES / "oof_model_correlation.csv")

    weight_rows = []
    best_ensemble = None
    for w1 in np.arange(0, 1.001, 0.05):
        for w2 in np.arange(0, 1.001 - w1, 0.05):
            w3 = round(1.0 - w1 - w2, 10)
            if w3 < 0:
                continue
            weights = np.array([w1, w2, w3])
            probability = oof_matrix @ weights
            threshold_scores = [(threshold, accuracy_score(y, probability >= threshold)) for threshold in np.arange(0.35, 0.651, 0.005)]
            threshold, accuracy = max(threshold_scores, key=lambda item: (item[1], -abs(item[0] - 0.5)))
            row = {"Model1": candidate_names[0], "Model2": candidate_names[1], "Model3": candidate_names[2], "W1": w1, "W2": w2, "W3": w3, "Threshold": threshold, "OOFAccuracy": accuracy}
            weight_rows.append(row)
            if best_ensemble is None or (accuracy, -abs(threshold - 0.5)) > (best_ensemble["OOFAccuracy"], -abs(best_ensemble["Threshold"] - 0.5)):
                best_ensemble = row
    pd.DataFrame(weight_rows).sort_values("OOFAccuracy", ascending=False).to_csv(TABLES / "ensemble_weights.csv", index=False)
    weights = np.array([best_ensemble["W1"], best_ensemble["W2"], best_ensemble["W3"]])
    ensemble_oof, ensemble_test = oof_matrix @ weights, test_matrix @ weights
    ensemble_threshold = float(best_ensemble["Threshold"])

    hard_oof = (np.mean(oof_matrix >= 0.5, axis=1) >= 0.5).astype(int)
    hard_test = (np.mean(test_matrix >= 0.5, axis=1) >= 0.5).astype(int)
    soft_oof, soft_test = oof_matrix.mean(axis=1), test_matrix.mean(axis=1)
    soft_threshold = max(np.arange(0.35, 0.651, 0.005), key=lambda t: accuracy_score(y, soft_oof >= t))
    pd.DataFrame([
        {"Ensemble": "HardVoting", "OOFAccuracy": accuracy_score(y, hard_oof), "Threshold": 0.5},
        {"Ensemble": "SoftVoting", "OOFAccuracy": accuracy_score(y, soft_oof >= soft_threshold), "Threshold": soft_threshold},
        {"Ensemble": "WeightedSoftVoting", "OOFAccuracy": accuracy_score(y, ensemble_oof >= ensemble_threshold), "Threshold": ensemble_threshold},
    ]).to_csv(TABLES / "ensemble_comparison.csv", index=False)

    threshold_rows = [{"Threshold": threshold, "Accuracy": accuracy_score(y, ensemble_oof >= threshold)} for threshold in np.arange(0.3, 0.701, 0.005)]
    pd.DataFrame(threshold_rows).to_csv(TABLES / "threshold_search.csv", index=False)

    meta = LogisticRegression(C=0.2, max_iter=2000, random_state=PRIMARY_SEED)
    meta_cv = StratifiedKFold(5, shuffle=True, random_state=PRIMARY_SEED)
    stacking_oof = cross_val_predict(meta, oof_matrix, y, cv=meta_cv, method="predict_proba")[:, 1]
    meta.fit(oof_matrix, y)
    stacking_test = meta.predict_proba(test_matrix)[:, 1]
    stack_threshold = max(np.arange(0.35, 0.651, 0.005), key=lambda t: accuracy_score(y, stacking_oof >= t))

    wcg_results = build_wcg_candidates(train, test)
    for name, values in wcg_results.items():
        metrics = score_metrics(y, values["oof"].astype(float))
        values["accuracy"] = metrics["Accuracy"]
    wcg_name = max(wcg_results, key=lambda name: wcg_results[name]["accuracy"])
    wcg_oof, wcg_test = wcg_results[wcg_name]["oof"], wcg_results[wcg_name]["test"]
    pd.DataFrame([{"Rule": name, "OOFAccuracy": value["accuracy"], "ChangedVsGender": int(np.sum(value["oof"] != gender_probability))} for name, value in wcg_results.items()]).to_csv(TABLES / "wcg_rules.csv", index=False)

    hybrid_candidates = []
    for strength in [0.25, 0.5, 0.75, 1.0]:
        hybrid_oof = ensemble_oof * (1 - strength) + wcg_oof * strength
        hybrid_test = ensemble_test * (1 - strength) + wcg_test * strength
        threshold = max(np.arange(0.35, 0.651, 0.005), key=lambda t: accuracy_score(y, hybrid_oof >= t))
        hybrid_candidates.append({"Strength": strength, "Threshold": threshold, "OOFAccuracy": accuracy_score(y, hybrid_oof >= threshold), "oof": hybrid_oof, "test": hybrid_test})
    best_hybrid = max(hybrid_candidates, key=lambda row: (row["OOFAccuracy"], -abs(row["Threshold"] - 0.5)))
    pd.DataFrame([{k: v for k, v in row.items() if k not in {"oof", "test"}} for row in hybrid_candidates]).to_csv(TABLES / "hybrid_results.csv", index=False)

    best_single_name = finalists_frame.iloc[0]["Experiment"]
    best_single_probability = prediction_store[best_single_name]
    best_single_threshold = max(np.arange(0.35, 0.651, 0.005), key=lambda t: accuracy_score(y, best_single_probability["oof"] >= t))
    submissions = {
        "submission_01_best_single.csv": (best_single_probability["test"] >= best_single_threshold).astype(int),
        "submission_02_weighted_ensemble.csv": (ensemble_test >= ensemble_threshold).astype(int),
        "submission_03_stacking.csv": (stacking_test >= stack_threshold).astype(int),
        "submission_04_wcg.csv": wcg_test.astype(int),
        "submission_05_hybrid.csv": (best_hybrid["test"] >= best_hybrid["Threshold"]).astype(int),
    }
    for filename, prediction in submissions.items():
        pd.DataFrame({"PassengerId": test["PassengerId"].astype(int), "Survived": prediction.astype(int)}).to_csv(SUBMISSIONS / filename, index=False)

    comparison = pd.DataFrame({"PassengerId": test["PassengerId"], "Name": test["Name"], "Sex": test["Sex"], "Age": test["Age"], "Pclass": test["Pclass"], "Ticket": test["Ticket"]})
    for filename, prediction in submissions.items():
        comparison[filename.removesuffix(".csv")] = prediction
    comparison["DistinctPredictions"] = comparison[[c for c in comparison if c.startswith("submission_")]].nunique(axis=1)
    comparison.loc[comparison["DistinctPredictions"].gt(1)].to_csv(TABLES / "submission_comparison.csv", index=False)
    submission_columns = [c for c in comparison if c.startswith("submission_")]
    disagreement = pd.DataFrame(index=submission_columns, columns=submission_columns, dtype=int)
    for left in submission_columns:
        for right in submission_columns:
            disagreement.loc[left, right] = int((comparison[left] != comparison[right]).sum())
    disagreement.to_csv(TABLES / "submission_disagreement.csv")

    add_ensemble_results(experiment_results, y, hard_oof.astype(float), 0.5, soft_oof, soft_threshold, ensemble_oof, ensemble_threshold, stacking_oof, stack_threshold, wcg_name, wcg_oof, best_hybrid)
    results_frame = pd.DataFrame(experiment_results).sort_values(["OOFAccuracy", "CVMean"], ascending=False).reset_index(drop=True)
    results_frame.insert(0, "Rank", np.arange(1, len(results_frame) + 1))
    results_frame.to_csv(TABLES / "experiment_results.csv", index=False)
    pd.DataFrame(experiment_log).to_csv(TABLES / "experiment_log.csv", index=False)

    create_figures(train, test, results_frame, pd.DataFrame(ablation_rows), pd.DataFrame(threshold_rows), oof_predictions, disagreement, ensemble_oof, ensemble_threshold, best_single_name)
    create_importance(train, test, best_single_name, tuned_params, get_folds)
    sanity = sanity_check(train, test, submissions, train_path, test_path)
    save_json(sanity, TABLES / "automatic_sanity_check.json")
    write_report(train, results_frame, finalists_frame, best_single_name, candidate_names, best_ensemble, ensemble_oof, ensemble_threshold, stacking_oof, stack_threshold, wcg_name, wcg_results, best_hybrid, submissions)
    create_summary_notebook()
    print("RUN_ALL_COMPLETE")


def build_wcg_candidates(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    raw_x = train.drop(columns="Survived").reset_index(drop=True)
    y = train["Survived"].astype(int).reset_index(drop=True)
    test_x = test.reset_index(drop=True)
    source_all = pd.concat([raw_x, test_x], ignore_index=True)
    configs = {
        "WCG_1_conservative": (2, 0.20, 0.80, False),
        "WCG_2_balanced": (1, 0.25, 0.75, False),
        "WCG_3_with_boys": (1, 0.25, 0.75, True),
    }
    storage = {name: {"oof_parts": [], "test_parts": []} for name in configs}
    for seed in RANDOM_SEEDS:
        splitter = StratifiedKFold(5, shuffle=True, random_state=seed)
        seed_oof = {name: np.zeros(len(train), dtype=int) for name in configs}
        seed_test = {name: np.zeros((len(test), 5), dtype=int) for name in configs}
        for fold_number, (fit_index, valid_index) in enumerate(splitter.split(raw_x, y)):
            fit_x, valid_x, fit_y = raw_x.iloc[fit_index], raw_x.iloc[valid_index], y.iloc[fit_index]
            builder = FeatureBuilder(source_all, "smart", 16, True).fit(fit_x)
            fit_eng, valid_eng, test_eng = builder.transform(fit_x), builder.transform(valid_x), builder.transform(test_x)
            valid_group = add_group_features(fit_eng, fit_y, valid_eng, False)
            test_group = add_group_features(fit_eng, fit_y, test_eng, False)
            for name, (support, low, high, boys) in configs.items():
                seed_oof[name][valid_index] = apply_wcg_rule(valid_group, support, low, high, boys)
                seed_test[name][:, fold_number] = apply_wcg_rule(test_group, support, low, high, boys)
        for name in configs:
            storage[name]["oof_parts"].append(seed_oof[name])
            storage[name]["test_parts"].append((seed_test[name].mean(axis=1) >= 0.5).astype(int))
    return {
        name: {
            "oof": (np.mean(value["oof_parts"], axis=0) >= 0.5).astype(int),
            "test": (np.mean(value["test_parts"], axis=0) >= 0.5).astype(int),
        }
        for name, value in storage.items()
    }


def apply_wcg_rule(frame: pd.DataFrame, support: int, low: float, high: float, boys: bool) -> np.ndarray:
    prediction = frame["Sex"].eq("female").astype(int).to_numpy()
    low_evidence = (
        ((frame["WCGFamilyCount"] >= support) & (frame["WCGFamilyRate"] <= low))
        | ((frame["WCGTicketCount"] >= support) & (frame["WCGTicketRate"] <= low))
    )
    female_or_child = frame["Sex"].eq("female") | frame["IsChild"].eq(1)
    prediction[(female_or_child & low_evidence).to_numpy()] = 0
    if boys:
        high_evidence = (
            ((frame["WCGFamilyCount"] >= support) & (frame["WCGFamilyRate"] >= high))
            | ((frame["WCGTicketCount"] >= support) & (frame["WCGTicketRate"] >= high))
        )
        boy = frame["Sex"].eq("male") & (frame["IsChild"].eq(1) | frame["IsMaster"].eq(1))
        prediction[(boy & high_evidence).to_numpy()] = 1
    return prediction


def group_stress_test(train: pd.DataFrame, test: pd.DataFrame, model_name: str, params: dict) -> None:
    raw_x = train.drop(columns="Survived").reset_index(drop=True)
    y = train["Survived"].astype(int).reset_index(drop=True)
    test_x = test.reset_index(drop=True)
    base = basic_features(raw_x)
    parent = list(range(len(base)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for column in ["FamilyID", "TicketNormalized"]:
        for indices in base.groupby(column).groups.values():
            indices = list(indices)
            if len(indices) > 1:
                for index in indices[1:]:
                    union(indices[0], index)
    groups = np.array([find(index) for index in range(len(base))])
    source_all = pd.concat([raw_x, test_x], ignore_index=True)
    splitter = StratifiedGroupKFold(5, shuffle=True, random_state=PRIMARY_SEED)
    rows = []
    for fold_number, (fit_index, valid_index) in enumerate(splitter.split(raw_x, y, groups), 1):
        fit_x, valid_x = raw_x.iloc[fit_index], raw_x.iloc[valid_index]
        fit_y, valid_y = y.iloc[fit_index], y.iloc[valid_index]
        builder = FeatureBuilder(source_all, "smart", 16, True).fit(fit_x)
        fit_eng, valid_eng = builder.transform(fit_x), builder.transform(valid_x)
        fit_eng = add_group_features(fit_eng, fit_y, fit_eng, True)
        valid_eng = add_group_features(fit_eng, fit_y, valid_eng, False)
        columns = feature_columns("E10_Group")
        preprocessor = make_preprocessor(fit_eng, columns)
        fit_matrix = preprocessor.fit_transform(fit_eng[columns])
        valid_matrix = preprocessor.transform(valid_eng[columns])
        model = model_factory(model_name, params)
        if model_name in SCALED_MODELS:
            model = Pipeline([("scale", StandardScaler()), ("model", model)])
        model.fit(fit_matrix, fit_y)
        probability = model.predict_proba(valid_matrix)[:, 1]
        rows.append({
            "Fold": fold_number,
            "Accuracy": accuracy_score(valid_y, probability >= 0.5),
            "ValidationSamples": len(valid_y),
            "ValidationGroups": len(np.unique(groups[valid_index])),
        })
    frame = pd.DataFrame(rows)
    frame.loc[len(frame)] = {
        "Fold": "Mean",
        "Accuracy": frame["Accuracy"].mean(),
        "ValidationSamples": frame["ValidationSamples"].sum(),
        "ValidationGroups": frame["ValidationGroups"].sum(),
    }
    frame.to_csv(TABLES / "group_aware_stress_test.csv", index=False)


def add_ensemble_results(results, y, hard_oof, hard_threshold, soft_oof, soft_threshold, ensemble_oof, ensemble_threshold, stacking_oof, stack_threshold, wcg_name, wcg_oof, best_hybrid):
    candidates = [
        ("HardVoting", hard_oof, hard_threshold, "Majority vote"),
        ("SoftVoting", soft_oof, soft_threshold, "Equal probability average"),
        ("WeightedEnsemble", ensemble_oof, ensemble_threshold, "WeightedSoftVoting"),
        ("Stacking", stacking_oof, stack_threshold, "OOF Logistic meta learner"),
        (wcg_name, wcg_oof.astype(float), 0.5, "Fold-safe woman-child group rule"),
        ("ML_WCG_Hybrid", best_hybrid["oof"], best_hybrid["Threshold"], f"WCG strength={best_hybrid['Strength']}"),
    ]
    for experiment, probability, threshold, note in candidates:
        metrics = score_metrics(y, probability, threshold)
        results.append({
            "Experiment": experiment, "Model": experiment, "FeatureSet": "Final", "Parameters": "{}",
            "CVMean": metrics["Accuracy"], "CVStd": np.nan, "CVMin": np.nan, "CVMax": np.nan,
            "OOFAccuracy": metrics["Accuracy"], "Precision": metrics["Precision"], "Recall": metrics["Recall"],
            "F1": metrics["F1"], "AUC": metrics["AUC"], "Threshold": threshold, "Notes": note,
        })


def create_figures(train, test, results, ablation, threshold, oof_predictions, disagreement, ensemble_oof, ensemble_threshold, best_single_name):
    sns.set_theme(style="whitegrid", context="notebook")
    engineered = basic_features(train)
    engineered["Survived"] = train["Survived"].to_numpy()
    charts = [
        ("01_survival_distribution.png", lambda ax: sns.countplot(data=train, x="Survived", ax=ax, color="#377a98"), "Survival Distribution"),
        ("02_survival_by_sex.png", lambda ax: sns.barplot(data=train, x="Sex", y="Survived", ax=ax, color="#d28742"), "Survival Rate by Sex"),
        ("03_survival_by_pclass.png", lambda ax: sns.barplot(data=train, x="Pclass", y="Survived", ax=ax, color="#4f8a5b"), "Survival Rate by Passenger Class"),
        ("04_survival_by_title.png", lambda ax: sns.barplot(data=engineered, x="Title", y="Survived", ax=ax, color="#377a98"), "Survival Rate by Title"),
        ("05_survival_by_family_size.png", lambda ax: sns.barplot(data=engineered, x="FamilySize", y="Survived", ax=ax, color="#4f8a5b"), "Survival Rate by Family Size"),
        ("06_survival_by_ticket_group.png", lambda ax: sns.barplot(x=engineered["Ticket"].map(pd.concat([train["Ticket"], test["Ticket"]]).value_counts()).clip(upper=8), y=engineered["Survived"], ax=ax, color="#d28742"), "Survival Rate by Ticket Group Size"),
        ("07_survival_by_deck.png", lambda ax: sns.barplot(data=engineered, x="Deck", y="Survived", ax=ax, color="#377a98"), "Survival Rate by Deck"),
        ("08_age_distribution.png", lambda ax: sns.histplot(data=train, x="Age", hue="Survived", bins=25, element="step", ax=ax), "Age Distribution by Outcome"),
        ("09_fare_distribution.png", lambda ax: sns.histplot(np.log1p(train["Fare"]), bins=30, ax=ax, color="#4f8a5b"), "Log Fare Distribution"),
    ]
    for filename, plotter, title in charts:
        fig, ax = plt.subplots(figsize=(8, 4.8))
        plotter(ax)
        ax.set_title(title)
        plt.tight_layout()
        plt.savefig(FIGURES / filename, dpi=160)
        plt.close()

    pool = results[results["Experiment"].str.startswith("Pool_")].sort_values("OOFAccuracy")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(pool["Model"], pool["OOFAccuracy"], color="#377a98")
    ax.set(title="Model OOF Accuracy Comparison", xlabel="Accuracy")
    ax.set_xlim(max(0.7, pool["OOFAccuracy"].min() - 0.02), min(0.9, pool["OOFAccuracy"].max() + 0.02))
    plt.tight_layout(); plt.savefig(FIGURES / "12_model_cv_comparison.png", dpi=160); plt.close()

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(ablation["Experiment"], ablation["OOFAccuracy"], marker="o", color="#4f8a5b")
    ax.set(title="Feature Ablation Path", ylabel="OOF Accuracy"); ax.tick_params(axis="x", rotation=35)
    plt.tight_layout(); plt.savefig(FIGURES / "13_feature_ablation_curve.png", dpi=160); plt.close()

    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.plot(threshold["Threshold"], threshold["Accuracy"], color="#d28742")
    ax.axvline(ensemble_threshold, color="#333333", linestyle="--")
    ax.set(title="Threshold vs OOF Accuracy", xlabel="Threshold", ylabel="Accuracy")
    plt.tight_layout(); plt.savefig(FIGURES / "14_threshold_accuracy.png", dpi=160); plt.close()

    probability_columns = [column for column in oof_predictions if column.endswith("_prob")]
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(oof_predictions[probability_columns].corr(), annot=True, fmt=".2f", cmap="vlag", center=0, ax=ax)
    ax.set_title("OOF Probability Correlation")
    plt.tight_layout(); plt.savefig(FIGURES / "15_oof_correlation.png", dpi=160); plt.close()

    fig, ax = plt.subplots(figsize=(5.5, 5))
    ConfusionMatrixDisplay(confusion_matrix(train["Survived"], ensemble_oof >= ensemble_threshold)).plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title("Weighted Ensemble OOF Confusion Matrix")
    plt.tight_layout(); plt.savefig(FIGURES / "16_confusion_matrix.png", dpi=160); plt.close()

    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(disagreement.astype(int), annot=True, fmt="d", cmap="YlOrRd", ax=ax)
    ax.set_title("Submission Disagreement Counts")
    plt.tight_layout(); plt.savefig(FIGURES / "17_submission_disagreement.png", dpi=160); plt.close()


def create_importance(train, test, best_single_name, tuned_params, get_folds):
    model_name = best_single_name.removeprefix("Finalist_")
    folds = get_folds("E10_Group", PRIMARY_SEED)
    fold = folds[0]
    model = model_factory(model_name, tuned_params.get(model_name))
    if model_name in SCALED_MODELS:
        model = Pipeline([("scale", StandardScaler()), ("model", model)])
    model.fit(fold.train_matrix, fold.y_train)
    estimator = model.named_steps["model"] if isinstance(model, Pipeline) else model
    if hasattr(estimator, "feature_importances_"):
        importance = estimator.feature_importances_
    elif hasattr(estimator, "coef_"):
        importance = np.abs(estimator.coef_[0])
    else:
        importance = np.zeros(len(fold.feature_names))
    importance_frame = pd.DataFrame({"Feature": fold.feature_names, "Importance": importance}).sort_values("Importance", ascending=False).head(25)
    importance_frame.to_csv(TABLES / "feature_importance.csv", index=False)
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(importance_frame["Feature"][::-1], importance_frame["Importance"][::-1], color="#377a98")
    ax.set_title(f"Feature Importance: {model_name}")
    plt.tight_layout(); plt.savefig(FIGURES / "10_feature_importance.png", dpi=160); plt.close()

    permutation = permutation_importance(model, fold.valid_matrix, fold.y_valid, n_repeats=12, random_state=PRIMARY_SEED, scoring="accuracy", n_jobs=-1)
    permutation_frame = pd.DataFrame({"Feature": fold.feature_names, "Importance": permutation.importances_mean, "Std": permutation.importances_std}).sort_values("Importance", ascending=False).head(25)
    permutation_frame.to_csv(TABLES / "permutation_importance.csv", index=False)
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(permutation_frame["Feature"][::-1], permutation_frame["Importance"][::-1], xerr=permutation_frame["Std"][::-1], color="#4f8a5b")
    ax.set_title(f"Permutation Importance: {model_name}")
    plt.tight_layout(); plt.savefig(FIGURES / "11_permutation_importance.png", dpi=160); plt.close()


def sanity_check(train, test, submissions, train_path, test_path):
    checks = {
        "Survived_not_in_test_features": "Survived" not in test.columns,
        "PassengerId_unique_train": train["PassengerId"].is_unique,
        "PassengerId_unique_test": test["PassengerId"].is_unique,
        "raw_train_unchanged_rows": len(pd.read_csv(train_path)) == 891,
        "raw_test_unchanged_rows": len(pd.read_csv(test_path)) == 418,
    }
    for filename in submissions:
        frame = pd.read_csv(SUBMISSIONS / filename)
        checks[f"{filename}_columns"] = frame.columns.tolist() == ["PassengerId", "Survived"]
        checks[f"{filename}_rows"] = len(frame) == len(test)
        checks[f"{filename}_ids"] = frame["PassengerId"].equals(test["PassengerId"])
        checks[f"{filename}_binary"] = set(frame["Survived"].unique()) <= {0, 1}
        checks[f"{filename}_integer"] = pd.api.types.is_integer_dtype(frame["Survived"])
        checks[f"{filename}_no_missing"] = not frame.isna().any().any()
    checks["all_passed"] = bool(all(checks.values()))
    if not checks["all_passed"]:
        raise AssertionError({key: value for key, value in checks.items() if not value})
    return checks


def write_report(train, results, finalists, best_single_name, candidate_names, best_ensemble, ensemble_oof, ensemble_threshold, stacking_oof, stack_threshold, wcg_name, wcg_results, best_hybrid, submissions):
    baseline = results.loc[results["Experiment"].eq("B0_GenderRule")].iloc[0]
    best_single = finalists.iloc[0]
    report = f"""# Titanic 最终竞赛报告

## 结论

本项目只使用 Kaggle 官方 `train.csv` 与 `test.csv`，没有查询或使用测试集真实生还标签。训练集所有目标型家庭/票号特征均在验证折之外计算；填补、独热编码和缩放也在折内拟合。

- 性别规则基线 Accuracy：{baseline['OOFAccuracy']:.5f}
- 最佳单模型：{best_single_name}，OOF Accuracy {best_single['OOFAccuracy']:.5f}
- 最佳单模型多种子 CV：{best_single['CVMean']:.5f} ± {best_single['CVStd']:.5f}
- 加权融合 OOF Accuracy：{accuracy_score(train['Survived'], ensemble_oof >= ensemble_threshold):.5f}
- 加权融合阈值：{ensemble_threshold:.3f}
- Stacking OOF Accuracy：{accuracy_score(train['Survived'], stacking_oof >= stack_threshold):.5f}
- 最佳 WCG 规则：{wcg_name}，OOF Accuracy {wcg_results[wcg_name]['accuracy']:.5f}
- ML + WCG Hybrid：OOF Accuracy {best_hybrid['OOFAccuracy']:.5f}，规则权重 {best_hybrid['Strength']:.2f}

## 有效信息

实验重点不是堆模型，而是把 `Sex`、`Pclass`、`Title`、家庭规模、共同票号、客舱甲板与同行组生还信息表达清楚。`feature_ablation.csv` 记录每组特征的增量，`model_pool.csv` 和 `multi_seed_finalists.csv` 记录模型筛选过程。

同行生还率没有直接用完整训练标签回填自身。每个验证折只读取其训练子集的标签；最终测试映射才使用完整训练集。这样既利用 Titanic 的同行结构，又避免验证泄漏。

## 模型选择

候选融合模型：{', '.join(candidate_names)}。

加权融合权重：{best_ensemble['W1']:.2f} / {best_ensemble['W2']:.2f} / {best_ensemble['W3']:.2f}。权重来自 OOF 网格搜索，不是主观指定。阈值同样在 OOF 概率上搜索，并以靠近 0.5 作为同分时的稳定性偏好。

## 提交顺序

FIRST KAGGLE SUBMISSION:
outputs/submissions/submission_02_weighted_ensemble.csv

SECOND KAGGLE SUBMISSION:
outputs/submissions/submission_01_best_single.csv

THIRD KAGGLE SUBMISSION:
outputs/submissions/submission_04_wcg.csv

如果 Hybrid 的公开分数明显低于本地验证，优先提交 weighted ensemble；若两者差异仍大，再检查排行榜样本波动和 group correction 的适用边界，不应根据单次榜单盲目改 PassengerId。

## 产物

- `outputs/tables/experiment_results.csv`：全部实验排名
- `outputs/tables/experiment_log.csv`：逐折日志
- `outputs/tables/feature_ablation.csv`：特征消融
- `outputs/tables/best_params.json`：调参结果
- `outputs/tables/oof_predictions.csv`：OOF 概率
- `outputs/tables/submission_comparison.csv`：提交差异乘客
- `outputs/figures/`：17 张分析与验证图

BEST SINGLE MODEL:
{best_single_name}

BEST FEATURE SET:
E10_Group

BEST OOF ACCURACY:
{results.iloc[0]['OOFAccuracy']:.5f} ({results.iloc[0]['Experiment']})

BEST MULTI-SEED CV:
{best_single['CVMean']:.5f} ± {best_single['CVStd']:.5f}

BEST ENSEMBLE:
Weighted ensemble of {', '.join(candidate_names)}

BEST THRESHOLD:
{ensemble_threshold:.3f}

BEST WCG/HYBRID:
{wcg_name}; Hybrid strength={best_hybrid['Strength']:.2f}
"""
    (OUTPUT / "FINAL_REPORT.md").write_text(report, encoding="utf-8")


def create_summary_notebook():
    try:
        import nbformat as nbf
        from nbclient import NotebookClient

        cells = [
            nbf.v4.new_markdown_cell("# Titanic Competition Results\n\n可复现结果索引。完整训练入口为项目根目录的 `run_all.py`。"),
            nbf.v4.new_code_cell("from pathlib import Path\nimport pandas as pd\nfrom IPython.display import display, Image\nROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()"),
            nbf.v4.new_markdown_cell("## Experiment ranking"),
            nbf.v4.new_code_cell("results = pd.read_csv(ROOT/'outputs'/'tables'/'experiment_results.csv')\nresults.head(15)"),
            nbf.v4.new_markdown_cell("## Feature ablation"),
            nbf.v4.new_code_cell("pd.read_csv(ROOT/'outputs'/'tables'/'feature_ablation.csv')"),
            nbf.v4.new_code_cell("display(Image(filename=str(ROOT/'outputs'/'figures'/'12_model_cv_comparison.png')))\ndisplay(Image(filename=str(ROOT/'outputs'/'figures'/'13_feature_ablation_curve.png')))"),
            nbf.v4.new_markdown_cell("## Final submission candidates"),
            nbf.v4.new_code_cell("pd.read_csv(ROOT/'outputs'/'tables'/'submission_disagreement.csv')"),
        ]
        notebook = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}})
        path = PROJECT_ROOT / "notebooks" / "final_competition_results.ipynb"
        path.parent.mkdir(parents=True, exist_ok=True)
        nbf.write(notebook, path)
        NotebookClient(notebook, timeout=180, kernel_name="python3", resources={"metadata": {"path": str(PROJECT_ROOT)}}).execute()
        nbf.write(notebook, path)
    except Exception as error:
        save_json({"error": repr(error)}, TABLES / "notebook_generation_error.json")


if __name__ == "__main__":
    main()
