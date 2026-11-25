"""Customer Analysis Page Component."""
from pathlib import Path

import pandas as pd
import streamlit as st

from streamlit_app.api_client import BackendAPIClient
from streamlit_app.components.charts import (
    plot_amount_distribution,
    plot_risk_distribution,
    plot_transaction_volume,
)
from streamlit_app.utils.formatting import format_currency, format_probability
from streamlit_app.utils.validation import validate_customer_id


def render_customer_view(client: BackendAPIClient) -> None:
    """Render customer profile, multi-account view, and transaction history."""
    st.markdown("## 👤 Customer Analysis")
    st.markdown("Search and inspect account histories and behavioral risk across multiple accounts.")

    search_col1, search_col2 = st.columns([3, 1])
    with search_col1:
        cust_input = st.text_input("Enter Customer ID", value="501", placeholder="e.g. 501")
    with search_col2:
        search_clicked = st.button("Search Customer", use_container_width=True)

    is_valid, customer_id, err_msg = validate_customer_id(cust_input)
    if not is_valid:
        st.error(f"❌ {err_msg}")
        return

    st.markdown("---")

    # Fetch customer profile & history from backend API
    detail_resp = client.get_customer_detail(customer_id)
    history_resp = client.get_customer_transactions(customer_id)

    customer_data = None
    txns = []

    if detail_resp.success and detail_resp.data:
        customer_data = detail_resp.data
    if history_resp.success and history_resp.data:
        txns = history_resp.data.get("transactions", [])

    # Graceful fallback for demonstration when backend is pending
    if (not customer_data or not txns) and (detail_resp.is_offline or detail_resp.status_code == 404):
        local_cache_path = Path(__file__).resolve().parents[2] / "ml" / "data" / "raw_features.csv"
        if local_cache_path.exists():
            st.warning(
                f"⚠️ **Backend API pending.** Showing demonstration profile for Customer #{customer_id} "
                f"from local dataset cache.",
                icon="⚠️",
            )
            raw_cache = pd.read_csv(local_cache_path)
            matching = raw_cache[raw_cache["SenderCustomerID"] == customer_id]
            if matching.empty:
                # If exact ID not in sample, pick first available
                customer_id = int(raw_cache["SenderCustomerID"].iloc[0])
                matching = raw_cache[raw_cache["SenderCustomerID"] == customer_id]

            accounts = matching["SenderAccountNumber"].unique().tolist()
            total_amt = float(matching["Amount"].sum())
            fraud_count = int(matching["IsFraud"].sum())

            customer_data = {
                "customer_id": customer_id,
                "name": f"Customer #{customer_id}",
                "email": f"customer_{customer_id}@example.com",
                "phone": f"+91-00000{customer_id:05d}",
                "account_count": len(accounts),
                "accounts": [{"account_number": acc, "type": "Savings", "status": "ACTIVE"} for acc in accounts],
                "total_transactions": len(matching),
                "total_amount": total_amt,
                "fraud_transactions": fraud_count,
            }

            for _, r in matching.iterrows():
                is_fraud = int(r.get("IsFraud", 0))
                txns.append({
                    "transaction_id": int(r["TransactionID"]),
                    "account_number": int(r["SenderAccountNumber"]),
                    "amount": float(r["Amount"]),
                    "transaction_type": str(r["TransactionTypeName"]),
                    "timestamp": str(r["TransactionTimestamp"]),
                    "fraud_probability": 0.6267 if is_fraud else 0.0333,
                    "prediction": "FRAUDULENT" if is_fraud else "LEGITIMATE",
                    "risk_status": "HIGH" if is_fraud else "LOW",
                })

    if not customer_data:
        st.error(f"Customer #{customer_id} not found or backend API is unreachable.")
        return

    # Profile Header
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    p_col1.metric("Customer Name", customer_data.get("name", f"Customer #{customer_id}"))
    p_col2.metric("Total Accounts", customer_data.get("account_count", 1))
    p_col3.metric("Lifetime Transactions", customer_data.get("total_transactions", len(txns)))
    p_col4.metric("Total Spend", format_currency(customer_data.get("total_amount", 0.0)))

    # Accounts List
    accounts = customer_data.get("accounts", [])
    if accounts:
        st.markdown("#### Linked Bank Accounts")
        acc_text = " • ".join([f"**Account #{acc.get('account_number')}** ({acc.get('type', 'Savings')})" for acc in accounts])
        st.markdown(acc_text)

    st.markdown("---")

    # Transaction History
    st.markdown(f"### Transaction History ({len(txns)} transactions across all accounts)")
    if not txns:
        st.info("No transaction records found for this customer.", icon="ℹ️")
        return

    df_txns = pd.DataFrame(txns)

    # Activity charts
    c_col1, c_col2 = st.columns(2)
    with c_col1:
        st.plotly_chart(plot_transaction_volume(df_txns), use_container_width=True)
    with c_col2:
        risk_counts = df_txns["risk_status"].value_counts().to_dict()
        st.plotly_chart(plot_risk_distribution(risk_counts), use_container_width=True)

    # Table
    display_df = df_txns[[
        "transaction_id", "account_number", "amount", "transaction_type",
        "timestamp", "fraud_probability", "risk_status", "prediction"
    ]].copy()
    display_df["amount"] = display_df["amount"].apply(format_currency)
    display_df["fraud_probability"] = display_df["fraud_probability"].apply(format_probability)

    st.dataframe(
        display_df,
        column_config={
            "transaction_id": st.column_config.NumberColumn("Txn ID", format="%d"),
            "account_number": st.column_config.NumberColumn("Account No", format="%d"),
            "amount": "Amount",
            "transaction_type": "Channel",
            "timestamp": "Timestamp",
            "fraud_probability": "Fraud Prob",
            "risk_status": "Risk Status",
            "prediction": "Prediction",
        },
        use_container_width=True,
        hide_index=True,
    )
