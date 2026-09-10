from pathlib import Path
import re

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs" / "submissions"

train = pd.read_csv(RAW / "train.csv")
test = pd.read_csv(RAW / "test.csv")
combined = pd.concat([train, test.assign(Survived=np.nan)], ignore_index=True, sort=False)

title = combined["Name"].str.extract(r",\s*([^.]+)\.", expand=False).str.strip()
man_titles = {"Capt", "Don", "Major", "Col", "Rev", "Dr", "Sir", "Mr", "Jonkheer"}
woman_titles = {"Dona", "the Countess", "Mme", "Mlle", "Ms", "Miss", "Lady", "Mrs"}
combined["Role"] = np.select(
    [title.isin(man_titles), title.isin(woman_titles), title.eq("Master")],
    ["man", "woman", "boy"],
    default="woman",
)

combined["WCGSurname"] = combined["Name"].str.split(",", n=1).str[0].str.strip()
combined.loc[combined["Role"].eq("man"), "WCGSurname"] = "noGroup"
surname_frequency = combined["WCGSurname"].value_counts()
combined.loc[combined["WCGSurname"].map(surname_frequency).le(1), "WCGSurname"] = "noGroup"

# For an otherwise-single woman or boy, use the surname already established by a shared ticket.
for index in combined.index[combined["Role"].ne("man") & combined["WCGSurname"].eq("noGroup")]:
    ticket_group = combined.index[combined["Ticket"].eq(combined.at[index, "Ticket"])]
    if len(ticket_group):
        combined.at[index, "WCGSurname"] = combined.at[ticket_group[0], "WCGSurname"]
combined["WCGSurname"] = combined["WCGSurname"].fillna("noGroup")

train_part = combined.iloc[: len(train)].copy()
test_part = combined.iloc[len(train):].copy()
group_survival = train_part.groupby("WCGSurname")["Survived"].mean()
test_part["GroupSurvival"] = test_part["WCGSurname"].map(group_survival)

prediction = np.zeros(len(test_part), dtype=int)
prediction[test_part["Role"].eq("woman").to_numpy()] = 1
prediction[(test_part["Role"].eq("boy") & test_part["GroupSurvival"].eq(1)).to_numpy()] = 1
prediction[(test_part["Role"].eq("woman") & test_part["GroupSurvival"].eq(0)).to_numpy()] = 0

submission = pd.DataFrame({
    "PassengerId": test["PassengerId"].astype(int),
    "Survived": prediction.astype(int),
})
assert submission.shape == (418, 2)
assert submission["PassengerId"].equals(test["PassengerId"])
assert set(submission["Survived"].unique()) <= {0, 1}
OUT.mkdir(parents=True, exist_ok=True)
path = OUT / "submission_10_name_wcg_exact.csv"
submission.to_csv(path, index=False)
print(path)
print("positive_predictions=", int(submission["Survived"].sum()))
print("changes_vs_gender=", int((submission["Survived"].to_numpy() != test["Sex"].eq("female").astype(int).to_numpy()).sum()))
