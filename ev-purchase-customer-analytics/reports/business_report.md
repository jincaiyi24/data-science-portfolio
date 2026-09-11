# Business Report

## Executive finding

The analysis covers 668,665 labelled customers. The observed EV-purchase-intent rate is 17.46%. Business segmentation uses the interpretable base-feature model (OOF ROC-AUC 0.941993); the separate competition model reaches 0.945713. Both measure ranking quality, not causal impact or guaranteed conversion.

## Answers to the business questions

1. **Highest-propensity customers.** `High Potential` has the highest OOF predicted propensity (66.98%) and represents 20.00% of labelled customers.
2. **Income.** Purchase rate moves from 31.31% in the lowest income quintile to 20.86% in the highest; the relationship is descriptive, not causal.
3. **Subsidy.** Observed purchase rates are 27.47% with subsidy availability and 0.58% without it.
4. **Environmental concern.** Its model contribution is ranked #1 among the displayed SHAP drivers.
5. **Range anxiety.** Purchase rates are 18.90% for low, 4.17% for medium, and 0.14% for high anxiety.
6. **Home charging.** Purchase rates are 19.58% with home charging and 12.71% without it.
7. **City type.** Urban, suburban and rural rates are 16.11%, 18.09%, and 19.34%.
8. **Commute.** The lowest and highest commute quintiles have purchase rates of 17.07% and 14.68%.
9. **Interactions.** Feature ablation tests charging access, range pressure, income-per-car and motivation/infrastructure interactions; their value is judged by CV change rather than narrative plausibility.
10. **Priority audiences.** Start with High Potential; use different treatment for Infrastructure-Constrained, Eco-Motivated and Price-Sensitive groups rather than one generic campaign.

## Recommended actions

1. **Finding -> Evidence -> Interpretation -> Action:** High-propensity customers are concentrated in the top scored segment -> OOF mean 66.98% -> the model can prioritize outreach -> pilot a ranked campaign and measure incremental conversion with a holdout group.
2. **Finding -> Evidence -> Interpretation -> Action:** Home charging status separates observed intent (19.58% vs 12.71%) -> infrastructure is associated with readiness -> offer installation partnerships to otherwise promising customers.
3. **Finding -> Evidence -> Interpretation -> Action:** Subsidy availability separates observed intent (27.47% vs 0.58%) -> financial support is associated with propensity -> surface eligibility and total-cost information in targeted messaging.
4. **Finding -> Evidence -> Interpretation -> Action:** Range-anxiety groups differ -> anxiety is a useful barrier signal -> tailor range, charging-network and trip-planning communication, then validate impact experimentally.

## Limits

The dataset is synthetic and the target is stated intent, not a recorded purchase. SHAP and segment comparisons explain model associations; they do not establish causality. Deployment would require calibration, fresh-data monitoring and randomized campaign tests.
