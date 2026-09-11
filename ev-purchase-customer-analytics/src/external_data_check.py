from __future__ import annotations

import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from config import DATA_DIR, ROOT, TABLE_DIR, TARGET


def encode(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "income": frame["Annual_Income_USD"],
            "environmental_concern": frame["Environmental_Concern_Level"],
            "subsidy": frame["Subsidy_Available"].map({"No": 0, "Yes": 1}),
            "range_anxiety": frame["Range_Anxiety_Level"].map({"Low": 0, "Medium": 1, "High": 2}),
        }
    )


def main() -> None:
    source = ROOT / "data" / "external" / "EV_Adoption_and_Range_Anxiety_Dataset.csv"
    original = pd.read_csv(source)
    competition = pd.read_csv(DATA_DIR / "train.csv")
    model = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        LogisticRegression(C=10, max_iter=1000, random_state=42),
    )
    model.fit(encode(original), original[TARGET].eq("Yes").astype(int))
    prediction = model.predict_proba(encode(competition))[:, 1]
    result = pd.DataFrame(
        [
            {
                "experiment": "Original-data four-feature logistic transfer",
                "training_rows": len(original),
                "evaluation_rows": len(competition),
                "competition_train_auc": roc_auc_score(competition[TARGET].eq("Yes"), prediction),
                "decision": "Rejected: weaker than competition-trained baselines",
            }
        ]
    )
    result.to_csv(TABLE_DIR / "external_data_experiment.csv", index=False)
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
