clear all
set more off
* Run this file from the supplementary-controls/stata directory.
use "paper2_stata_validation_sample.dta", clear
egen firm_id = group(corp_code)
tempname handle
postfile `handle' str40 model str40 term double coefficient std_error p_value N firms years r2_within using "paper2_stata_results.dta", replace

local base AssetTurnover_w FirmSize_w Leverage_w ROA_AvgAssets_w SalesGrowth_w Liquidity_w OperatingMargin_w FirmAgeLog_w LossDummy NegativeEquityDummy LogTotalSentences FiscalYearStockReturn_w FiscalYearDailyVolatility_w

quietly reghdfe FutureAssetTurnover_h2 BMI_component_z `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M00_BASELINE_REPRODUCED") ("BMI_component_z") (_b[BMI_component_z]) (_se[BMI_component_z]) (2*ttail(e(df_r),abs(_b[BMI_component_z]/_se[BMI_component_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

quietly reghdfe FutureAssetTurnover_h2 BMI_component_z IntangibleAssetRatio_w PPE_Ratio_w OperatingCashFlowRatio_w CapexIntensity_w `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M06_HIGH_COVERAGE") ("BMI_component_z") (_b[BMI_component_z]) (_se[BMI_component_z]) (2*ttail(e(df_r),abs(_b[BMI_component_z]/_se[BMI_component_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

quietly reghdfe FutureAssetTurnover_h2 BMI_component_z RAndDIntensity_OpenDART_w IntangibleAssetRatio_w PPE_Ratio_w OperatingCashFlowRatio_w CapexIntensity_w `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M07_ALL_EXTENDED") ("BMI_component_z") (_b[BMI_component_z]) (_se[BMI_component_z]) (2*ttail(e(df_r),abs(_b[BMI_component_z]/_se[BMI_component_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

quietly reghdfe FutureAssetTurnover_h2 BMI_component_z NonBMI_share_z `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M09_BMI_AND_NONBMI") ("BMI_component_z") (_b[BMI_component_z]) (_se[BMI_component_z]) (2*ttail(e(df_r),abs(_b[BMI_component_z]/_se[BMI_component_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))
post `handle' ("M09_BMI_AND_NONBMI") ("NonBMI_share_z") (_b[NonBMI_share_z]) (_se[NonBMI_share_z]) (2*ttail(e(df_r),abs(_b[NonBMI_share_z]/_se[NonBMI_share_z]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

quietly reghdfe FutureAssetTurnover_h2 BMIDisclosureAny `base', absorb(firm_id year) vce(cluster firm_id)
post `handle' ("M10_ANY_BMI") ("BMIDisclosureAny") (_b[BMIDisclosureAny]) (_se[BMIDisclosureAny]) (2*ttail(e(df_r),abs(_b[BMIDisclosureAny]/_se[BMIDisclosureAny]))) (e(N)) (e(N_clust)) (.) (e(r2_within))

postclose `handle'
use "paper2_stata_results.dta", clear
export delimited using "paper2_stata_results.csv", replace
exit, clear
