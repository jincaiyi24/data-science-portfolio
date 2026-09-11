# Publication and Data Boundary

The competition is still active. The competition code was shared first through the public Kaggle Notebook below, and this GitHub package is the data-safe portfolio mirror prepared afterward.

- Kaggle code release: https://www.kaggle.com/code/kimzaiyi1/ev-purchase-propensity-reproducible-xgboost-cv
- Verified Kaggle version: 3
- Kaggle execution status: complete

Any future competition-related code change should be synchronized to Kaggle before the corresponding GitHub update.

## Deliberately Excluded

- Official train, test, and sample-submission files
- External row-level datasets
- Customer-level profiles, segments, and propensities
- OOF and test predictions
- Kaggle submission files
- Trained model files and serialized parameters
- Downloaded leaderboard tables and archives
- Third-party reference notebooks
- Local credentials, caches, and absolute paths

## Included

- Original project source code and SQL scripts
- A notebook with all saved outputs and execution counts removed
- Aggregate validation, feature-importance, and segment tables
- Project reports and presentation-ready figures
- Reproducibility instructions and an automated publication-safety check

## Update Checklist

- Recheck the competition's current sharing and data-license rules.
- Synchronize competition-related code with Kaggle first.
- Run `python tests/verify_public_package.py .` from the package root.
- Review `git status` and `git diff --cached` before the first push.
- Confirm that no ignored file was ever committed; `.gitignore` does not remove Git history.
