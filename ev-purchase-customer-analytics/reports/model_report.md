# Model Report

## Validation design

- Primary metric: ROC-AUC.
- Splitter: 5-fold shuffled StratifiedKFold, random state 42.
- Preprocessing is fitted inside each fold. CatBoost receives native low-cardinality categorical fields.
- Secondary metrics: accuracy, precision, recall, F1 and log loss.

## Results

The strongest initial tree model was **LightGBM** at 0.941736 +/- 0.000909. Optuna was run for 12 trials on each of LightGBM, XGBoost using a fixed stratified sample of 180,000 rows and 3-fold CV. Full-data validation remained 5-fold.

Business feature engineering was evaluated as BASE, FE_V1 and FE_V2. The selected deployable version was **BASE**, and five-seed XGBoost bagging reached 0.941993. A separate competition track added digit, frequency and fold-safe target-encoding features. The final Kaggle method was **Advanced + Base Blend**, with OOF ROC-AUC **0.945713**.

Across five CV seeds, the top model mean ROC-AUC ranged from 0.941884 to 0.941916, with an average of 0.941899. This audit is reported separately from the single-seed model-selection result.

Kaggle verification: **Public ROC-AUC 0.94589; rank 458/1,509 (top 30.4%)**.

## Why these models

Logistic regression tests whether mostly linear additive effects are sufficient. Random Forest supplies a bagged nonlinear baseline. XGBoost and LightGBM learn boosted decision rules efficiently; CatBoost additionally handles categorical variables natively. The ensemble is retained only when its OOF AUC exceeds the best component. Synthetic-artifact features are kept out of the business interpretation track because their predictive value may not transfer to real customers.

## Important limitations

Optuna used a stratified subsample and 12 trials per model to keep the search proportionate to local compute. These results are evidence for a good configuration, not proof of a global optimum. Kaggle public score is an external check and must not replace local validation.

An independently trained four-feature logistic model on the public 10,000-row source dataset transferred at 0.937619 AUC on the competition train set, so external labels were rejected rather than blended. The accepted competition gain comes from competition-train cross-validation, not copied predictions.
