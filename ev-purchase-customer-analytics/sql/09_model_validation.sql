-- name: model_vs_actual
SELECT p.prediction_decile,
       COUNT(*) AS customers,
       ROUND(AVG(p.predicted_probability), 8) AS average_prediction,
       ROUND(AVG(p.actual_target), 8) AS actual_positive_rate,
       ROUND(AVG(p.predicted_probability) - AVG(p.actual_target), 8) AS calibration_gap
FROM ev_model_predictions p
WHERE p.source_set = 'train'
GROUP BY p.prediction_decile
ORDER BY p.prediction_decile;

-- name: model_validation
SELECT experiment_group, model_name, model_version, validation_type, seed, fold,
       ROUND(roc_auc, 8) AS roc_auc,
       ROUND(std_roc_auc, 8) AS std_roc_auc,
       ROUND(accuracy, 8) AS accuracy,
       ROUND(f1_score, 8) AS f1_score,
       ROUND(log_loss, 8) AS log_loss,
       ROUND(fit_seconds, 3) AS fit_seconds,
       parameters
FROM ev_model_metrics
ORDER BY roc_auc DESC, experiment_group, model_name, seed, fold;
