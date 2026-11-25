# Phase 3 Implementation Report: Streamlit Frontend & Backend–ML Integration

**Project:** Banking Transaction and Fraud Detection System  
**Role:** Person 2 – Machine Learning & Frontend Developer  
**Status:** **Phase 3 Complete**  
**Date:** 2026-11-24  

---

## 1. Executive Summary

Phase 3 delivers the production-ready Streamlit frontend dashboard (`streamlit_app/`) and establishes the formal HTTP REST API integration contract with Person 1's backend.

### Key Accomplishments
1. **Zero Database Couplings:** The frontend strictly adheres to architectural boundaries: it never connects directly to MySQL, nor does it execute SQL statements or duplicate database business logic.
2. **Resilient HTTP API Client:** Implemented `streamlit_app/api_client.py` with typed response structures (`APIResponse`), graceful error handling for timeouts/network outages, and clean degraded states.
3. **Transparent Status & No Fabricated Data:** When Person 1's backend endpoints are offline or pending, the frontend clearly displays "Backend Integration Pending" notices and "Unavailable" metric placeholders rather than fabricating fake system metrics.
4. **Interactive SHAP Explainability:** Built individual transaction attribution charts (Plotly horizontal bar), natural language explanation generator, and global model feature importance displays.
5. **Quality Assurance:** Added 13 new unit and integration tests across `tests/test_api_client.py` and `tests/test_frontend.py`. The complete test suite of **57 tests passes in 16.32s**.
6. **Person 1 File Boundaries:** Zero modifications were made to `database/` or `data_generation/`.

---

## 2. Implemented Dashboard Architecture

```text
streamlit_app/
├── app.py                     # Main application entry point & layout controller
├── config.py                  # Environment config, backend URLs, and risk thresholds
├── api_client.py              # Resilient HTTP REST API client with error handling
├── requirements.txt           # Frontend Python dependencies
├── components/
│   ├── sidebar.py             # Branding, navigation menu & backend connection indicator
│   ├── overview.py            # System-wide KPI cards, activity charts, recent transactions table
│   ├── customer_view.py       # Multi-account customer search, spending metrics & history
│   ├── transaction_view.py    # Transaction telemetry, metadata, and scoring inspection
│   ├── fraud_analysis.py      # Individual SHAP attribution, narrative generation & global plots
│   ├── alerts.py              # Fraud alert review queue and investigation updates
│   └── charts.py              # Reusable Plotly chart generators
└── utils/
    ├── formatting.py          # Currency (₹), percentage, and colored HTML badge formatters
    └── validation.py          # Input validators for customer and transaction IDs
```

---

## 3. Implemented Dashboard Pages

### 3.1 📊 Dashboard Overview
- **System-Wide KPI Cards:** Displays Total Transactions, Total Customers, Fraudulent Transactions, Legitimate Transactions, System Fraud Rate, and High-Risk Transactions.
- **Transaction Activity Visualizations:** Plotly bar chart of transaction volume over time and donut chart of Risk Status distribution (`LOW`, `MEDIUM`, `HIGH`).
- **Recent Transactions Table:** Searchable, filterable table with currency formatting and status badges.
- **Pending Backend State:** Displays "Unavailable" metrics when backend is pending rather than misleading user statistics.

### 3.2 👤 Customer Analysis
- **Multi-Account View:** Handles customers with multiple accounts (`account_count >= 1`).
- **Profile & Lifetime Spend:** Customer metrics across all linked accounts.
- **Customer Transaction History:** Paginated table and activity breakdown per account.

### 3.3 💳 Transaction Inspection
- **Telemetry & Metadata:** Displays sender, receiver, merchant, device ID, IP address, and location.
- **Scoring Breakdown:** Shows Fraud Probability, Model Version (`rf_v1.0`), Decision (`LEGITIMATE` / `FRAUDULENT`), and Risk Status (`LOW`, `MEDIUM`, `HIGH`).
- **PCI-DSS Compliance:** Card references are tokenized; no real PANs/CVVs are displayed or stored.

### 3.4 🔍 Fraud Explainability (SHAP)
- **Local Explanations:** Directional feature attribution showing features that increase risk (red) vs mitigate risk (green).
- **Dynamic Natural Language Narrative:** Synthesizes human-readable explanations from top SHAP drivers without hardcoding.
- **Global Model Explainability:** Embeds global feature importance bar chart and beeswarm plot from Phase 2.

### 3.5 🚨 Fraud Alerts & Investigations
- **Alert Queue:** Review interface for transactions with $\text{Probability} \ge 0.2100$.
- **Pending Notification:** Clearly indicates that alert write-back and investigation update endpoints are pending Person 1's backend deployment.

### 3.6 ⚙️ System & Backend Status
- Diagnostic page displaying model metadata, operational thresholds, backend health check responses, and API contract specifications.

---

## 4. API Endpoints Status Matrix

Documented in [`docs/PHASE_3_API_INTEGRATION_CONTRACT.md`](file:///e:/BTech%20CS%20with%20AI/5th%20sem/DBMS/Banking-Fraud-Detection/docs/PHASE_3_API_INTEGRATION_CONTRACT.md):

| Endpoint | Method | Frontend Client Method | Current Status |
|---|---|---|---|
| `/api/v1/health` | `GET` | `client.check_health()` | **Pending Person 1** |
| `/api/v1/overview/metrics` | `GET` | `client.get_overview_metrics()` | **Pending Person 1** |
| `/api/v1/transactions` | `GET` | `client.get_transactions()` | **Pending Person 1** |
| `/api/v1/transactions/{id}` | `GET` | `client.get_transaction_detail()` | **Pending Person 1** |
| `/api/v1/customers` | `GET` | `client.search_customers()` | **Pending Person 1** |
| `/api/v1/customers/{id}` | `GET` | `client.get_customer_detail()` | **Pending Person 1** |
| `/api/v1/customers/{id}/transactions` | `GET` | `client.get_customer_transactions()` | **Pending Person 1** |
| `/api/v1/predict` | `POST` | `client.predict_transaction()` | **Pending Person 1 (Local fallback active)** |
| `/api/v1/alerts` | `GET` | `client.get_alerts()` | **Pending Person 1** |
| `/api/v1/alerts/{id}/investigation` | `PUT` | `client.update_alert_investigation()` | **Pending Person 1** |

---

## 5. Test Suite Verification

Full test suite execution (`python -m pytest tests/ -v`):

```text
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
rootdir: E:\BTech CS with AI\5th sem\DBMS\Banking-Fraud-Detection
plugins: anyio-4.13.0
collected 57 items

tests/test_api_client.py::test_api_client_success_response PASSED        [  1%]
tests/test_api_client.py::test_api_client_connection_error PASSED        [  3%]
tests/test_api_client.py::test_api_client_timeout PASSED                 [  5%]
tests/test_api_client.py::test_api_client_http_error PASSED              [  7%]
tests/test_api_client.py::test_api_client_invalid_json PASSED            [  8%]
tests/test_api_client.py::test_api_client_predict_fallback_to_local PASSED [ 10%]
tests/test_data_validation.py::test_valid_transaction_batch PASSED       [ 12%]
tests/test_data_validation.py::test_detect_missing_mandatory_fields PASSED [ 14%]
tests/test_data_validation.py::test_detect_invalid_amount_zero_or_negative PASSED [ 15%]
tests/test_data_validation.py::test_detect_duplicate_transaction_id PASSED [ 17%]
tests/test_data_validation.py::test_detect_invalid_transaction_type PASSED [ 19%]
tests/test_features.py::test_build_features_output_columns PASSED        [ 21%]
tests/test_features.py::test_amount_transformations PASSED               [ 22%]
tests/test_features.py::test_calendar_and_temporal_features PASSED       [ 24%]
tests/test_features.py::test_sender_account_age PASSED                   [ 26%]
tests/test_features.py::test_p2p_channel_invariants PASSED               [ 28%]
tests/test_features.py::test_cnp_channel_invariants_and_device_changes PASSED [ 29%]
tests/test_features.py::test_velocity_rolling_prior_window PASSED        [ 31%]
tests/test_frontend.py::test_formatting_currency PASSED                  [ 33%]
tests/test_frontend.py::test_formatting_probability PASSED               [ 35%]
tests/test_frontend.py::test_formatting_badges PASSED                    [ 36%]
tests/test_validation_customer_id PASSED                                 [ 38%]
tests/test_validation_transaction_id PASSED                              [ 40%]
tests/test_chart_generation PASSED                                       [ 42%]
tests/test_natural_language_explanation_generation PASSED                 [ 43%]
tests/test_merchant_risk.py::test_merchant_risk_encoder_fit PASSED       [ 45%]
tests/test_merchant_risk.py::test_training_leave_one_out_transformation PASSED [ 47%]
tests/test_merchant_risk.py::test_inference_transform_without_labels PASSED [ 49%]
tests/test_merchant_risk.py::test_encoder_serialization_roundtrip PASSED [ 50%]
tests/test_model.py::test_model_loading_and_type PASSED                  [ 52%]
tests/test_model.py::test_sidecar_consistency PASSED                     [ 54%]
tests/test_model.py::test_model_predict_proba_range_and_shape PASSED     [ 56%]
tests/test_model.py::test_model_inference_determinism PASSED             [ 57%]
tests/test_model.py::test_classification_threshold_application PASSED    [ 59%]
tests/test_model_explainer.py::test_explainer_initialization PASSED      [ 61%]
tests/test_model_explainer.py::test_positive_class_index PASSED          [ 63%]
tests/test_model_explainer.py::test_single_transaction_explanation_schema PASSED [ 64%]
tests/test_model_explainer.py::test_custom_top_k PASSED                  [ 66%]
tests/test_model_explainer.py::test_missing_features_raises_error PASSED [ 68%]
tests/test_model_explainer.py::test_multi_row_dataframe_raises_error PASSED [ 70%]
tests/test_prediction_interface.py::test_predict_transaction_contract_fields PASSED [ 71%]
tests/test_prediction_interface.py::test_predict_transaction_series_and_df PASSED [ 73%]
tests/test_prediction_interface.py::test_predict_transaction_with_explanation PASSED [ 75%]
tests/test_prediction_interface.py::test_predict_transaction_invalid_inputs PASSED [ 77%]
tests/test_prediction_interface.py::test_predict_batch_multi_rows PASSED [ 78%]
tests/test_prediction_interface.py::test_predict_batch_empty PASSED      [ 80%]
tests/test_prediction_interface.py::test_predict_batch_error_handling PASSED [ 82%]
tests/test_prediction_interface.py::test_artifact_integrity_missing_files PASSED [ 84%]
tests/test_prediction_interface.py::test_real_dataset_integration PASSED [ 85%]
tests/test_preprocessing.py::test_build_preprocessor_structure PASSED    [ 87%]
tests/test_preprocessing.py::test_preprocessor_fit_transform PASSED      [ 89%]
tests/test_preprocessing.py::test_handle_unknown_and_missing_categories PASSED [ 91%]
tests/test_risk_classification.py::test_classify_risk_exact_boundaries PASSED [ 92%]
tests/test_risk_classification.py::test_classify_risk_out_of_bounds PASSED [ 94%]
tests/test_risk_classification.py::test_classify_risk_invalid_types PASSED [ 96%]
tests/test_risk_classification.py::test_classify_prediction_boundaries PASSED [ 98%]
tests/test_risk_classification.py::test_custom_threshold_override PASSED [100%]

============================= 57 passed in 16.32s =============================
```

---

## 6. How to Run Frontend & Backend

### 6.1 Frontend Execution
```bash
# Optional: customize backend host if not default http://127.0.0.1:8000
export BACKEND_BASE_URL="http://127.0.0.1:8000"

# Launch Streamlit Dashboard
python -m streamlit run streamlit_app/app.py --server.port 8501
```

### 6.2 Proposed Person 1 Backend Execution (Once Implemented)
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 7. Next Steps for Person 1 & Person 2

### Next Steps for Person 1 (Backend Developer):
1. Implement the REST API server according to [`docs/PHASE_3_API_INTEGRATION_CONTRACT.md`](file:///e:/BTech%20CS%20with%20AI/5th%20sem/DBMS/Banking-Fraud-Detection/docs/PHASE_3_API_INTEGRATION_CONTRACT.md).
2. Wire up database extraction queries for `/api/v1/overview/metrics`, `/api/v1/transactions`, and `/api/v1/customers`.
3. Import `ml.predict.predict_transaction` to generate fraud scores and write back predictions to `Transaction` and `Fraud_Alert` tables.

### Next Steps for Person 2 (ML & Frontend Developer):
- Stand by for Person 1 to expose endpoints.
- Conduct live end-to-end integration validation once the backend API service is started.
