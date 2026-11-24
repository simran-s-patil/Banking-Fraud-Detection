# Phase 2 Implementation Report: Model Explainability & Production Prediction Interface

**Project:** Banking Transaction and Fraud Detection System  
**Role:** Person 2 – Machine Learning Developer  
**Status:** Phase 2 Complete  
**Date:** 2026-11-24  

---

## 1. Executive Summary

Phase 2 establishes the production-grade, explainable machine learning prediction interface for the Banking Transaction and Fraud Detection System. 

All Phase 2 objectives have been completed:
1. **Model & Encoder Compatibility:** Formally verified the provenance and integrity of `random_forest_full_disposable_33070.joblib` and `merchant_risk_encoder_disposable_33070.json`.
2. **Centralized Risk & Metadata:** Implemented `ml/config.py` decoupling operational risk bands (`LOW`, `MEDIUM`, `HIGH`) from the decision threshold (`0.2100`), with immutable version metadata (`rf_v1.0`).
3. **SHAP Explainability Engine:** Built `ml/model_explainer.py` using `shap.TreeExplainer` on the 300-tree ensemble, providing exact mathematical attribution for the positive fraud class with both global summary plots and individual transaction attribution.
4. **Production Prediction API:** Implemented `ml/predict.py` supporting `predict_transaction()` and `predict_batch()`, returning strictly typed payloads conforming to Person 1's backend contract.
5. **Quality Assurance:** Added 20 new tests across 3 modules (`test_risk_classification.py`, `test_model_explainer.py`, `test_prediction_interface.py`). The full test suite of **44 tests passes in 5.62 seconds**, with zero modifications to Person 1's database or backend files.

---

## 2. Deliverables Summary

| Deliverable | Path | Status |
|---|---|---|
| **Inference Audit** | `docs/PHASE_2_INFERENCE_AUDIT.md` | Complete |
| **Model Explainability Spec** | `docs/MODEL_EXPLAINABILITY.md` | Complete |
| **Backend Integration Guide** | `docs/ML_BACKEND_INTEGRATION.md` | Complete |
| **Centralized Config & Versioning** | `ml/config.py` | Complete |
| **Explainability Engine** | `ml/model_explainer.py` | Complete |
| **Prediction & Batch API** | `ml/predict.py` | Complete |
| **Global SHAP Visualizations** | `ml/reports/figures/shap_feature_importance_bar.png`<br>`ml/reports/figures/shap_summary_beeswarm.png` | Complete |
| **Unit & Integration Tests** | `tests/test_risk_classification.py`<br>`tests/test_model_explainer.py`<br>`tests/test_prediction_interface.py` | 44/44 Passing |

---

## 3. Verified Prediction Outputs

### 3.1 Legitimate Transaction Scoring
```json
{
  "transaction_id": 1,
  "fraud_probability": 0.0333,
  "prediction": "LEGITIMATE",
  "model_version": "rf_v1.0",
  "risk_status": "LOW",
  "merchant_risk_rate": 0.0306,
  "explanation": {
    "top_reasons": [
      {
        "feature": "is_night",
        "contribution": 0.0946,
        "direction": "INCREASES_RISK"
      },
      {
        "feature": "sender_account_age_days",
        "contribution": -0.0769,
        "direction": "DECREASES_RISK"
      },
      {
        "feature": "amount",
        "contribution": -0.0741,
        "direction": "DECREASES_RISK"
      },
      {
        "feature": "amount_log",
        "contribution": -0.0731,
        "direction": "DECREASES_RISK"
      },
      {
        "feature": "hour_of_day",
        "contribution": 0.0729,
        "direction": "INCREASES_RISK"
      }
    ],
    "base_value": 0.5,
    "fraud_probability": 0.0333
  }
}
```

### 3.2 Fraudulent Transaction Scoring
```json
{
  "transaction_id": 17,
  "fraud_probability": 0.6267,
  "prediction": "FRAUDULENT",
  "model_version": "rf_v1.0",
  "risk_status": "HIGH",
  "merchant_risk_rate": 0.0385,
  "explanation": {
    "top_reasons": [
      {
        "feature": "amount",
        "contribution": 0.1674,
        "direction": "INCREASES_RISK"
      },
      {
        "feature": "amount_log",
        "contribution": 0.155,
        "direction": "INCREASES_RISK"
      },
      {
        "feature": "merchant_risk_rate",
        "contribution": -0.0563,
        "direction": "DECREASES_RISK"
      },
      {
        "feature": "hour_of_day",
        "contribution": -0.0321,
        "direction": "DECREASES_RISK"
      },
      {
        "feature": "is_new_merchant_for_customer",
        "contribution": 0.0309,
        "direction": "INCREASES_RISK"
      }
    ],
    "base_value": 0.5,
    "fraud_probability": 0.6267
  }
}
```

---

## 4. Test Execution Evidence

Full test execution output from `python -m pytest tests/ -v`:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: E:\BTech CS with AI\5th sem\DBMS\Banking-Fraud-Detection
plugins: anyio-4.13.0
collected 44 items

tests/test_data_validation.py::test_valid_transaction_batch PASSED       [  2%]
tests/test_data_validation.py::test_detect_missing_mandatory_fields PASSED [  4%]
tests/test_data_validation.py::test_detect_invalid_amount_zero_or_negative PASSED [  6%]
tests/test_data_validation.py::test_detect_duplicate_transaction_id PASSED [  9%]
tests/test_data_validation.py::test_detect_invalid_transaction_type PASSED [ 11%]
tests/test_features.py::test_build_features_output_columns PASSED        [ 13%]
tests/test_features.py::test_amount_transformations PASSED               [ 15%]
tests/test_features.py::test_calendar_and_temporal_features PASSED       [ 18%]
tests/test_features.py::test_sender_account_age PASSED                   [ 20%]
tests/test_features.py::test_p2p_channel_invariants PASSED               [ 22%]
tests/test_features.py::test_cnp_channel_invariants_and_device_changes PASSED [ 25%]
tests/test_features.py::test_velocity_rolling_prior_window PASSED        [ 27%]
tests/test_merchant_risk.py::test_merchant_risk_encoder_fit PASSED       [ 29%]
tests/test_merchant_risk.py::test_training_leave_one_out_transformation PASSED [ 31%]
tests/test_merchant_risk.py::test_inference_transform_without_labels PASSED [ 34%]
tests/test_merchant_risk.py::test_encoder_serialization_roundtrip PASSED [ 36%]
tests/test_model.py::test_model_loading_and_type PASSED                  [ 38%]
tests/test_model.py::test_sidecar_consistency PASSED                     [ 40%]
tests/test_model.py::test_model_predict_proba_range_and_shape PASSED     [ 43%]
tests/test_model.py::test_model_inference_determinism PASSED             [ 45%]
tests/test_model.py::test_classification_threshold_application PASSED    [ 47%]
tests/test_model_explainer.py::test_explainer_initialization PASSED      [ 50%]
tests/test_model_explainer.py::test_positive_class_index PASSED          [ 52%]
tests/test_model_explainer.py::test_single_transaction_explanation_schema PASSED [ 54%]
tests/test_model_explainer.py::test_custom_top_k PASSED                  [ 56%]
tests/test_model_explainer.py::test_missing_features_raises_error PASSED [ 59%]
tests/test_model_explainer.py::test_multi_row_dataframe_raises_error PASSED [ 61%]
tests/test_prediction_interface.py::test_predict_transaction_contract_fields PASSED [ 63%]
tests/test_prediction_interface.py::test_predict_transaction_series_and_df PASSED [ 65%]
tests/test_prediction_interface.py::test_predict_transaction_with_explanation PASSED [ 68%]
tests/test_prediction_interface.py::test_predict_transaction_invalid_inputs PASSED [ 70%]
tests/test_prediction_interface.py::test_predict_batch_multi_rows PASSED [ 72%]
tests/test_prediction_interface.py::test_predict_batch_empty PASSED      [ 75%]
tests/test_prediction_interface.py::test_predict_batch_error_handling PASSED [ 77%]
tests/test_prediction_interface.py::test_artifact_integrity_missing_files PASSED [ 79%]
tests/test_prediction_interface.py::test_real_dataset_integration PASSED [ 81%]
tests/test_preprocessing.py::test_build_preprocessor_structure PASSED    [ 84%]
tests/test_preprocessing.py::test_preprocessor_fit_transform PASSED      [ 86%]
tests/test_preprocessing.py::test_handle_unknown_and_missing_categories PASSED [ 88%]
tests/test_risk_classification.py::test_classify_risk_exact_boundaries PASSED [ 90%]
tests/test_risk_classification.py::test_classify_risk_out_of_bounds PASSED [ 93%]
tests/test_risk_classification.py::test_classify_risk_invalid_types PASSED [ 95%]
tests/test_risk_classification.py::test_classify_prediction_boundaries PASSED [ 97%]
tests/test_risk_classification.py::test_custom_threshold_override PASSED [100%]

============================= 44 passed in 5.62s ==============================
```

---

## 5. Scope & Boundary Adherence

- **Person 1 Backend & Database Isolation:** No database scripts (`database/*`) or data generation scripts (`data_generation/*`) were altered. All changes reside exclusively in `ml/`, `docs/`, and `tests/`.
- **No Direct MySQL Connections in Tests:** All 44 unit and integration tests run offline using cached fixtures and synthetic test records.
- **Strict Prohibition Against Model Workarounds:** The saved Random Forest pipeline and merchant encoder were loaded and evaluated as-is without retraining or weight modification.

---

## 6. Known Limitations & Operational Recommendations for Person 1

1. **Sender Transaction History Context:**  
   Single real-time transaction scoring depends on preceding transactions from the sender (over the prior 24 hours) to calculate velocity, rolling amounts, and device switches. Person 1's backend extractor should query the sender's preceding transactions when invoking `predict_transaction(..., historical_context=...)`.
2. **Batch Explainability Throughput:**  
   Because TreeExplainer traverses 300 decision trees, individual SHAP calculations require ~20–50 ms per transaction. Batch scoring should run with `explain=False` by default for high throughput, reserving explanations for flagged `HIGH` risk alerts.
