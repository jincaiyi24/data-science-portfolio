from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from titanic_core import RANDOM_SEEDS, basic_features, find_data


def add_union_group(combined: pd.DataFrame) -> pd.DataFrame:
    out = combined.copy().reset_index(drop=True)
    parent = list(range(len(out)))

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
        for indices in out.groupby(column).groups.values():
            indices = list(indices)
            if len(indices) > 1:
                for index in indices[1:]:
                    union(indices[0], index)
    out["UnionGroup"] = [f"G{find(index)}" for index in range(len(out))]
    return out


def reference_mask(frame: pd.DataFrame, mode: str) -> pd.Series:
    if mode == "female_master":
        return frame["Sex"].eq("female") | frame["Title"].eq("Master")
    if mode == "female_child12":
        return frame["Sex"].eq("female") | frame["Age"].lt(12)
    if mode == "female_child16":
        return frame["Sex"].eq("female") | frame["Age"].lt(16)
    return pd.Series(True, index=frame.index)


def group_evidence(source: pd.DataFrame, y: pd.Series, target: pd.DataFrame, keys: tuple[str, ...], mode: str):
    mask = reference_mask(source, mode)
    source_ref, y_ref = source.loc[mask], y.loc[mask]
    rates, counts = [], []
    for key in keys:
        stats = pd.DataFrame({"key": source_ref[key], "y": y_ref.to_numpy()}).groupby("key")["y"].agg(["mean", "count"])
        rates.append(target[key].map(stats["mean"]).to_numpy())
        counts.append(target[key].map(stats["count"]).fillna(0).to_numpy())
    return np.column_stack(rates), np.column_stack(counts)


def predict_rule(source, y, target, config):
    base, keys, ref_mode, support, low_cut, high_cut, low_target, male_high = config
    if base == "gender":
        prediction = target["Sex"].eq("female").astype(int).to_numpy()
    elif base == "female_master":
        prediction = (target["Sex"].eq("female") | target["Title"].eq("Master")).astype(int).to_numpy()
    else:
        prediction = (target["Sex"].eq("female") | target["Age"].lt(12)).astype(int).to_numpy()

    rates, counts = group_evidence(source, y, target, keys, ref_mode)
    low = np.any((counts >= support) & (rates <= low_cut), axis=1)
    if low_target == "female":
        eligible_low = target["Sex"].eq("female").to_numpy()
    elif low_target == "female_master":
        eligible_low = (target["Sex"].eq("female") | target["Title"].eq("Master")).to_numpy()
    else:
        eligible_low = (target["Sex"].eq("female") | target["Age"].lt(16)).to_numpy()
    prediction[eligible_low & low] = 0

    if male_high != "none":
        male_rates, male_counts = group_evidence(source, y, target, keys, "all")
        high = np.any((male_counts >= support) & (male_rates >= high_cut), axis=1)
        if male_high == "master":
            eligible_high = target["Sex"].eq("male") & target["Title"].eq("Master")
        elif male_high == "young":
            eligible_high = target["Sex"].eq("male") & target["Age"].lt(16)
        else:
            eligible_high = target["Sex"].eq("male") & target["Pclass"].le(2)
        prediction[eligible_high.to_numpy() & high] = 1
    return prediction


def main():
    train_path, test_path, _ = find_data(ROOT)
    train, test = pd.read_csv(train_path), pd.read_csv(test_path)
    y = train["Survived"].astype(int).reset_index(drop=True)
    raw_train = basic_features(train.drop(columns="Survived"))
    raw_test = basic_features(test)
    combined = add_union_group(pd.concat([raw_train, raw_test], ignore_index=True))
    x_train, x_test = combined.iloc[: len(train)].copy(), combined.iloc[len(train):].copy().reset_index(drop=True)

    configs = []
    key_options = [("FamilyID",), ("TicketNormalized",), ("FamilyID", "TicketNormalized"), ("UnionGroup",)]
    for values in product(
        ["gender", "female_master", "female_child12"],
        key_options,
        ["female_master", "female_child16"],
        [1, 2],
        [0.0, 0.25],
        [1.0],
        ["female", "female_master"],
        ["none", "master", "young"],
    ):
        configs.append(values)

    rows, predictions = [], {}
    for number, config in enumerate(configs):
        seed_oof, seed_test = [], []
        fold_scores = []
        for seed in RANDOM_SEEDS:
            splitter = StratifiedKFold(5, shuffle=True, random_state=seed)
            oof = np.zeros(len(train), dtype=int)
            test_votes = []
            for fit_index, valid_index in splitter.split(x_train, y):
                fit_x, valid_x, fit_y = x_train.iloc[fit_index], x_train.iloc[valid_index], y.iloc[fit_index]
                valid_prediction = predict_rule(fit_x, fit_y, valid_x, config)
                oof[valid_index] = valid_prediction
                fold_scores.append(accuracy_score(y.iloc[valid_index], valid_prediction))
                test_votes.append(predict_rule(fit_x, fit_y, x_test, config))
            seed_oof.append(oof)
            seed_test.append((np.mean(test_votes, axis=0) >= 0.5).astype(int))
        final_oof = (np.mean(seed_oof, axis=0) >= 0.5).astype(int)
        final_test = (np.mean(seed_test, axis=0) >= 0.5).astype(int)
        accuracy = accuracy_score(y, final_oof)
        key = f"R{number:04d}"
        rows.append({
            "RuleId": key,
            "Base": config[0],
            "Keys": "+".join(config[1]),
            "Reference": config[2],
            "Support": config[3],
            "LowCut": config[4],
            "HighCut": config[5],
            "LowTarget": config[6],
            "MaleHigh": config[7],
            "OOFAccuracy": accuracy,
            "FoldMean": np.mean(fold_scores),
            "FoldStd": np.std(fold_scores),
            "PositivePredictions": int(final_test.sum()),
        })
        predictions[key] = {"oof": final_oof, "test": final_test}

    results = pd.DataFrame(rows).sort_values(["OOFAccuracy", "FoldMean", "FoldStd"], ascending=[False, False, True])
    table_dir = ROOT / "outputs" / "tables"
    submission_dir = ROOT / "outputs" / "submissions"
    table_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(table_dir / "refined_rule_search.csv", index=False)

    existing = pd.read_csv(submission_dir / "submission_04_wcg.csv")["Survived"].to_numpy()
    selected = []
    for _, row in results.iterrows():
        rule_id = row["RuleId"]
        candidate = predictions[rule_id]["test"]
        disagreement_existing = int(np.sum(candidate != existing))
        disagreement_selected = min([int(np.sum(candidate != predictions[other]["test"])) for other in selected], default=999)
        if disagreement_existing >= 3 and disagreement_selected >= 3:
            selected.append(rule_id)
        if len(selected) == 5:
            break

    manifest = []
    for rank, rule_id in enumerate(selected, 1):
        filename = f"submission_refined_rule_{rank:02d}_{rule_id}.csv"
        pd.DataFrame({"PassengerId": test["PassengerId"].astype(int), "Survived": predictions[rule_id]["test"].astype(int)}).to_csv(submission_dir / filename, index=False)
        row = results.loc[results["RuleId"].eq(rule_id)].iloc[0].to_dict()
        row.update({"File": filename, "DiffVsCurrentWCG": int(np.sum(predictions[rule_id]["test"] != existing))})
        manifest.append(row)
    pd.DataFrame(manifest).to_csv(table_dir / "refined_rule_candidates.csv", index=False)
    print(pd.DataFrame(manifest)[["RuleId", "OOFAccuracy", "FoldMean", "FoldStd", "PositivePredictions", "DiffVsCurrentWCG", "File"]].to_string(index=False))


if __name__ == "__main__":
    main()
