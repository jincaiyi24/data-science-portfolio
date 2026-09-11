from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pandas as pd

from config import AUDIT_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture one team's public leaderboard result.")
    parser.add_argument("--account", required=True, help="Exact Kaggle team or account name")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    leaderboard = pd.read_csv(AUDIT_DIR / "current_leaderboard" / "leaderboard.csv")
    matches = leaderboard.loc[leaderboard["TeamName"].eq(args.account)]
    if matches.empty:
        raise SystemExit(f"Account not found in leaderboard: {args.account}")
    row = matches.iloc[0]
    result = {
        "account": args.account,
        "public_score": float(row["Score"]),
        "rank": int(row["Rank"]),
        "teams": int(len(leaderboard)),
        "top_percent": 100 * int(row["Rank"]) / len(leaderboard),
        "leaderboard_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified from downloaded Kaggle public leaderboard",
    }
    (AUDIT_DIR / "kaggle_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
