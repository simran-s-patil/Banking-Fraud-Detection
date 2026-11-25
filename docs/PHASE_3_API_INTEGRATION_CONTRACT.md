# Phase 3 API Integration Contract: Frontend $\longleftrightarrow$ Backend

**Project:** Banking Transaction and Fraud Detection System  
**Roles:** Person 2 (Frontend & ML Developer) $\longleftrightarrow$ Person 1 (Backend & Database Developer)  
**Status:** Formal Specification  
**Date:** 2026-11-24  

---

## 1. Executive Purpose & Architectural Principles

This document establishes the formal **HTTP REST API Integration Contract** between the Streamlit frontend (`streamlit_app/`) developed by Person 2 and the Backend API services to be implemented by Person 1.

### Architectural Rules
1. **No Direct Database Connections:** The Streamlit frontend **never** connects directly to MySQL. All data retrieval, queries, customer lookups, transaction logs, and fraud alerts pass through Person 1's backend HTTP APIs.
2. **Decoupled Business Logic:** Business rules (e.g. database transactions, investigation workflows, alert generation) remain strictly on Person 1's backend.
3. **ML Integration via Phase 2 Interface:** Person 1's backend imports `ml/predict.py` directly for internal scoring and write-back, or invokes scoring via the prediction endpoints specified herein.
4. **Resilient Frontend Degraded Mode:** When Person 1's backend is not yet started or an endpoint is pending, the frontend displays clear, actionable "Backend Integration Pending" notices instead of crashing or fabricating synthetic/fake data.

---

## 2. API Endpoint Matrix

| Method | Endpoint | Description | Status |
|---|---|---|---|
| `GET` | `/api/v1/health` | Service health & database connectivity check | **PENDING PERSON 1** |
| `GET` | `/api/v1/overview/metrics` | System-wide statistics for KPI cards | **PENDING PERSON 1** |
| `GET` | `/api/v1/transactions` | Paginated transaction activity & filtering | **PENDING PERSON 1** |
| `GET` | `/api/v1/transactions/{transaction_id}` | Detailed transaction inspection record | **PENDING PERSON 1** |
| `GET` | `/api/v1/customers` | Customer search by ID or name | **PENDING PERSON 1** |
| `GET` | `/api/v1/customers/{customer_id}` | Customer profile, accounts, and summary stats | **PENDING PERSON 1** |
| `GET` | `/api/v1/customers/{customer_id}/transactions` | Complete transaction history across all accounts | **PENDING PERSON 1** |
| `POST` | `/api/v1/predict` | Score an incoming transaction & optional SHAP | **PENDING PERSON 1** |
| `GET` | `/api/v1/alerts` | Active fraud alert queue and review statuses | **PENDING PERSON 1** |
| `PUT` | `/api/v1/alerts/{alert_id}/investigation` | Update investigation status and review notes | **PENDING PERSON 1** |

---

## 3. Detailed Endpoint Specifications

### 3.1 Health Check
- **Endpoint:** `GET /api/v1/health`
- **Purpose:** Verifies backend API readiness and MySQL database connection.
- **Request Parameters:** None.
- **Success Response (`200 OK`):**
  ```json
  {
    "status": "healthy",
    "database_connected": true,
    "model_version": "rf_v1.0",
    "timestamp": "2026-11-24T22:30:00Z"
  }
  ```
- **Error Response (`503 Service Unavailable`):**
  ```json
  {
    "status": "unhealthy",
    "database_connected": false,
    "error": "Unable to connect to MySQL database."
  }
  ```

---

### 3.2 System Overview & KPI Metrics
- **Endpoint:** `GET /api/v1/overview/metrics`
- **Purpose:** Supplies system-wide totals for top-level dashboard metrics cards.
- **Request Parameters:** None.
- **Success Response (`200 OK`):**
  ```json
  {
    "total_transactions": 20000,
    "total_customers": 500,
    "fraudulent_transactions": 600,
    "legitimate_transactions": 19400,
    "fraud_rate": 0.0300,
    "high_risk_transactions": 600,
    "open_alerts": 42
  }
  ```
- **Important Rule:** These metrics are strictly system-wide. The frontend must never replace these with filtered customer subsets.

---

### 3.3 Transaction Search & Filtering
- **Endpoint:** `GET /api/v1/transactions`
- **Purpose:** Populates the Recent Transactions table and activity volume charts.
- **Query Parameters:**
  - `limit` (int, default `50`): Max rows returned.
  - `offset` (int, default `0`): Pagination offset.
  - `risk_status` (string, optional): `'LOW'`, `'MEDIUM'`, `'HIGH'`.
  - `prediction` (string, optional): `'LEGITIMATE'`, `'FRAUDULENT'`.
  - `transaction_type` (string, optional): `'P2P_UPI'`, `'CNP_ECOM'`.
  - `start_date` (string, optional): ISO format (`YYYY-MM-DD`).
  - `end_date` (string, optional): ISO format (`YYYY-MM-DD`).
- **Success Response (`200 OK`):**
  ```json
  {
    "total_count": 20000,
    "page": 1,
    "limit": 50,
    "transactions": [
      {
        "transaction_id": 10001,
        "customer_id": 501,
        "sender_account_number": 100000000001,
        "amount": 2500.00,
        "transaction_type": "P2P_UPI",
        "timestamp": "2025-03-01T10:15:00",
        "fraud_probability": 0.0333,
        "prediction": "LEGITIMATE",
        "risk_status": "LOW"
      }
    ]
  }
  ```

---

### 3.4 Transaction Detail Inspection
- **Endpoint:** `GET /api/v1/transactions/{transaction_id}`
- **Purpose:** Full data payload for single transaction analysis.
- **Success Response (`200 OK`):**
  ```json
  {
    "transaction_id": 10001,
    "customer_id": 501,
    "customer_name": "Aarav Sharma",
    "sender_account_number": 100000000001,
    "sender_account_type": "Savings",
    "receiver_account_number": 100000000042,
    "receiver_upi_id": null,
    "merchant_id": null,
    "merchant_category": null,
    "amount": 2500.00,
    "transaction_type": "P2P_UPI",
    "timestamp": "2025-03-01T10:15:00",
    "device_id": "dev_a1b2c3d4",
    "ip_address": "192.0.2.15",
    "location": "Bengaluru",
    "card_reference_token": null,
    "fraud_probability": 0.0333,
    "prediction": "LEGITIMATE",
    "risk_status": "LOW",
    "model_version": "rf_v1.0",
    "merchant_risk_rate": 0.0306,
    "alert_id": null
  }
  ```
- **Error Response (`404 Not Found`):**
  ```json
  {
    "error": "Transaction with ID 10001 not found."
  }
  ```

---

### 3.5 Customer Search & Profile
- **Endpoint:** `GET /api/v1/customers`
- **Query Parameters:** `q` (string, customer ID or name query).
- **Success Response (`200 OK`):**
  ```json
  {
    "customers": [
      {
        "customer_id": 501,
        "name": "Aarav Sharma",
        "email": "aarav.sharma@example.com",
        "phone": "000001234567",
        "account_count": 2
      }
    ]
  }
  ```

---

### 3.6 Customer Transaction History
- **Endpoint:** `GET /api/v1/customers/{customer_id}/transactions`
- **Purpose:** Returns all historical transactions across all accounts of the customer.
- **Success Response (`200 OK`):**
  ```json
  {
    "customer_id": 501,
    "customer_name": "Aarav Sharma",
    "total_transactions": 35,
    "total_amount": 142500.00,
    "fraud_transaction_count": 1,
    "transactions": [
      {
        "transaction_id": 10001,
        "account_number": 100000000001,
        "amount": 2500.00,
        "transaction_type": "P2P_UPI",
        "timestamp": "2025-03-01T10:15:00",
        "fraud_probability": 0.0333,
        "prediction": "LEGITIMATE",
        "risk_status": "LOW"
      }
    ]
  }
  ```

---

### 3.7 Transaction Scoring & Prediction
- **Endpoint:** `POST /api/v1/predict`
- **Purpose:** Invokes ML scoring (and optional SHAP explainability) on an incoming transaction.
- **Request Body:**
  ```json
  {
    "transaction": {
      "TransactionID": 10001,
      "TransactionTimestamp": "2025-03-01 10:15:00",
      "Amount": 45000.00,
      "SenderAccountNumber": 100000000001,
      "SenderAccountType": "Savings",
      "SenderAccountCreatedAt": "2024-01-01 00:00:00",
      "TransactionTypeName": "P2P_UPI"
    },
    "explain": true
  }
  ```
- **Success Response (`200 OK`):**
  ```json
  {
    "transaction_id": 10001,
    "fraud_probability": 0.8700,
    "prediction": "FRAUDULENT",
    "model_version": "rf_v1.0",
    "risk_status": "HIGH",
    "merchant_risk_rate": 0.0306,
    "explanation": {
      "top_reasons": [
        {
          "feature": "amount",
          "contribution": 0.1674,
          "direction": "INCREASES_RISK"
        }
      ],
      "base_value": 0.5000,
      "fraud_probability": 0.8700
    }
  }
  ```

---

### 3.8 Fraud Alerts Queue & Investigation Updates
- **Endpoint:** `GET /api/v1/alerts`
- **Query Parameters:** `status` (`'OPEN'`, `'UNDER_REVIEW'`, `'RESOLVED'`).
- **Success Response (`200 OK`):**
  ```json
  {
    "alerts": [
      {
        "alert_id": 101,
        "transaction_id": 10017,
        "created_at": "2025-03-02T14:20:00",
        "fraud_probability": 0.6267,
        "review_status": "OPEN",
        "investigation_id": 42,
        "assigned_to": "Investigator-1",
        "notes": "Triggered by high amount and night transaction"
      }
    ]
  }
  ```
- **Endpoint:** `PUT /api/v1/alerts/{alert_id}/investigation`
- **Request Body:**
  ```json
  {
    "review_status": "RESOLVED",
    "investigation_outcome": "CONFIRMED_FRAUD",
    "notes": "Verified unauthorized device access."
  }
  ```
- **Success Response (`200 OK`):**
  ```json
  {
    "alert_id": 101,
    "review_status": "RESOLVED",
    "updated_at": "2026-11-24T22:30:00Z"
  }
  ```

---

## 4. Frontend Configuration & Execution

The Streamlit frontend will read the backend URL from the environment:
```bash
# Default backend URL if unspecified:
export BACKEND_BASE_URL="http://127.0.0.1:8000"
```
To run the Streamlit application:
```bash
streamlit run streamlit_app/app.py --server.port 8501
```
