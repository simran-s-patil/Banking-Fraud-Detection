"""Overview Dashboard Component: System-Wide KPIs, Charts, and Recent Transactions."""
from pathlib import Path

import pandas as pd
import streamlit as st

from streamlit_app.api_client import BackendAPIClient
from streamlit_app.components.charts import (
    plot_amount_distribution,
    plot_risk_distribution,
    plot_transaction_volume,
)
from streamlit_app.utils.formatting import (
    format_currency,
    format_probability,
    get_prediction_badge_html,
    get_risk_badge_html,
)


def render_overview(client: BackendAPIClient) -> None:
    """Render the main system-wide overview dashboard."""
    st.markdown("## 📊 Dashboard Overview")
    st.markdown("System-wide transaction monitoring and operational fraud risk posture.")

    # 1. KPI Cards
    st.markdown("### System-Wide Metrics")
    metrics_resp = client.get_overview_metrics()

    if metrics_resp.success and metrics_resp.data:
        m = metrics_resp.data
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Total Transactions", f"{m.get('total_transactions', 0):,}")
        col2.metric("Total Customers", f"{m.get('total_customers', 0):,}")
        col3.metric("Fraudulent Txns", f"{m.get('fraudulent_transactions', 0):,}")
        col4.metric("Legitimate Txns", f"{m.get('legitimate_transactions', 0):,}")
        fraud_rate = m.get("fraud_rate")
        col5.metric("Fraud Rate", format_probability(fraud_rate) if fraud_rate is not None else "N/A")
        col6.metric("High-Risk Alerts", f"{m.get('high_risk_transactions', 0):,}")
    else:
        st.info(
            "ℹ️ **System-wide backend metrics currently unavailable.**  \n"
            "Person 1's `/api/v1/overview/metrics` endpoint is pending deployment. Metrics are not fabricated.",
            icon="ℹ️",
        )
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.metric("Total Transactions", "Unavailable")
        col2.metric("Total Customers", "Unavailable")
        col3.metric("Fraudulent Txns", "Unavailable")
        col4.metric("Legitimate Txns", "Unavailable")
        col5.metric("Fraud Rate", "Unavailable")
        col6.metric("High-Risk Alerts", "Unavailable")

    st.markdown("---")

    # 2. Activity & Filters
    st.markdown("### Transaction Activity & Real-Time Monitoring")

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        txn_type_filter = st.selectbox("Transaction Type", ["ALL", "P2P_UPI", "CNP_ECOM"], index=0)
    with filter_col2:
        risk_filter = st.selectbox("Risk Status", ["ALL", "LOW", "MEDIUM", "HIGH"], index=0)
    with filter_col3:
        pred_filter = st.selectbox("Prediction", ["ALL", "LEGITIMATE", "FRAUDULENT"], index=0)

    # Fetch transactions from backend
    txn_resp = client.get_transactions(
        limit=100,
        transaction_type=txn_type_filter,
        risk_status=risk_filter,
        prediction=pred_filter,
    )

    transactions = []
    if txn_resp.success and txn_resp.data and "transactions" in txn_resp.data:
        transactions = txn_resp.data["transactions"]
    elif txn_resp.is_offline or txn_resp.status_code == 404:
        # Check if local dataset cache is available for offline demo testing
        local_cache_path = Path(__file__).resolve().parents[2] / "ml" / "data" / "raw_features.csv"
        if local_cache_path.exists():
            st.warning(
                "⚠️ **Backend API is offline or pending.** Showing local cached demonstration transactions "
                "from `ml/data/raw_features.csv` for interface testing.",
                icon="⚠️",
            )
            raw_cache = pd.read_csv(local_cache_path, nrows=100)
            for _, r in raw_cache.iterrows():
                is_fraud = int(r.get("IsFraud", 0))
                transactions.append({
                    "transaction_id": int(r["TransactionID"]),
                    "customer_id": int(r.get("SenderCustomerID", 501)),
                    "sender_account_number": int(r["SenderAccountNumber"]),
                    "amount": float(r["Amount"]),
                    "transaction_type": str(r["TransactionTypeName"]),
                    "timestamp": str(r["TransactionTimestamp"]),
                    "fraud_probability": 0.6267 if is_fraud else 0.0333,
                    "prediction": "FRAUDULENT" if is_fraud else "LEGITIMATE",
                    "risk_status": "HIGH" if is_fraud else "LOW",
                })

            # Apply local UI filters
            if txn_type_filter != "ALL":
                transactions = [t for t in transactions if t["transaction_type"] == txn_type_filter]
            if risk_filter != "ALL":
                transactions = [t for t in transactions if t["risk_status"] == risk_filter]
            if pred_filter != "ALL":
                transactions = [t for t in transactions if t["prediction"] == pred_filter]

    if not transactions:
        st.info("No transactions found matching the selected filter criteria.", icon="ℹ️")
        return

    df_txns = pd.DataFrame(transactions)

    # 3. Visualizations
    chart_col1, chart_col2 = st.columns([1, 1])

    with chart_col1:
        st.plotly_chart(plot_transaction_volume(df_txns), use_container_width=True)

    with chart_col2:
        risk_counts = df_txns["risk_status"].value_counts().to_dict()
        st.plotly_chart(plot_risk_distribution(risk_counts), use_container_width=True)

    # Amount distribution
    if "amount" in df_txns.columns:
        st.plotly_chart(plot_amount_distribution(df_txns["amount"].tolist()), use_container_width=True)

    # 4. Recent Transactions Table
    st.markdown(f"### Recent Transactions ({len(df_txns)} records displayed)")

    # Prepare display table
    display_df = df_txns[[
        "transaction_id", "customer_id", "amount", "transaction_type",
        "timestamp", "fraud_probability", "risk_status", "prediction"
    ]].copy()

    display_df["amount"] = display_df["amount"].apply(format_currency)
    display_df["fraud_probability"] = display_df["fraud_probability"].apply(format_probability)

    st.dataframe(
        display_df,
        column_config={
            "transaction_id": st.column_config.NumberColumn("Txn ID", format="%d"),
            "customer_id": st.column_config.NumberColumn("Customer ID", format="%d"),
            "amount": "Amount",
            "transaction_type": "Channel / Type",
            "timestamp": "Timestamp",
            "fraud_probability": "Fraud Prob",
            "risk_status": "Risk Status",
            "prediction": "ML Prediction",
        },
        use_container_width=True,
        hide_index=True,
    )
