from __future__ import annotations

import numpy as np
import pandas as pd

from config import ID_COLUMN, TARGET


BASE_FEATURES = [
    "Age",
    "Annual_Income_USD",
    "Daily_Commute_km",
    "Number_of_Cars_Owned",
    "Charging_Stations_Near_Home",
    "Charging_Stations_Near_Work",
    "Environmental_Concern_Level",
    "Gender",
    "City_Type",
    "Current_Car_Type",
    "Home_Charging_Possible",
    "Subsidy_Available",
    "Range_Anxiety_Level",
]


def add_features(frame: pd.DataFrame, version: str = "FE_V2") -> pd.DataFrame:
    x = frame[BASE_FEATURES].copy()
    if version == "BASE":
        return x

    home = x["Home_Charging_Possible"].eq("Yes").astype(int)
    subsidy = x["Subsidy_Available"].eq("Yes").astype(int)
    anxiety = x["Range_Anxiety_Level"].map({"Low": 1, "Medium": 2, "High": 3}).astype(float)
    stations = x["Charging_Stations_Near_Home"] + x["Charging_Stations_Near_Work"]
    x["Total_Charging_Stations"] = stations
    x["Charging_Access_Score"] = stations + 5 * home
    x["Income_Per_Car"] = x["Annual_Income_USD"] / x["Number_of_Cars_Owned"].clip(lower=1)
    x["Commute_Per_Access_Point"] = x["Daily_Commute_km"] / (1 + stations + 5 * home)
    x["Range_Pressure"] = anxiety * x["Daily_Commute_km"] / (1 + stations + 5 * home)
    if version == "FE_V1":
        return x

    x["Log_Income"] = np.log1p(x["Annual_Income_USD"])
    x["Age_Squared"] = x["Age"] ** 2
    x["Commute_Squared"] = x["Daily_Commute_km"] ** 2
    x["Eco_Charging_Alignment"] = x["Environmental_Concern_Level"] * (stations + 5 * home)
    x["Subsidy_Income_Interaction"] = subsidy * np.log1p(x["Annual_Income_USD"])
    x["Long_Commute_No_Home"] = x["Daily_Commute_km"] * (1 - home)
    x["Eco_Income_Interaction"] = x["Environmental_Concern_Level"] * np.log1p(x["Annual_Income_USD"])
    return x


def split_xy(train: pd.DataFrame, version: str = "FE_V2") -> tuple[pd.DataFrame, pd.Series]:
    return add_features(train, version), train[TARGET].eq("Yes").astype(int)
