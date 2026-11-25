"""Transaction Detail and Scoring Inspection Component."""
from pathlib import Path

import pandas as pd
import streamlit as st

from streamlit_app.api_client import BackendAPIClient
from streamlit_app.components.charts import plot_shap_contributions
from streamlit_app.utils.formatting import (
    format_currency,
    format_probability,
    format_timestamp,
    get_prediction_badge_html,
    get_risk_badge_html,
)
from streamlit_app.utils.validation import validate_transaction_id


def render_transaction_view(client: BackendAPIClient) -> None:
    """Render single transaction inspection and scoring details."""
    st.markdown("## 💳 Transaction Inspection & Scoring")
    st.markdown("Inspect transaction metadata, device telemetry, fraud probability, and model decisions.")

    col_in1, col_in2 = st.columns([3, 1])
    with col_in1:
        txn_input = st.text_input("Enter Transaction ID to Inspect", value="17", placeholder="e.g. 17")
    with col_in2:
        st.button("Inspect Transaction", use_container_width=True)

    is_valid, txn_id, err_msg = validate_transaction_id(txn_input)
    if not is_valid:
        st.error(f"❌ {err_msg}")
        return

    st.markdown("---")

    # Fetch from backend
    txn_resp = client.get_transaction_detail(txn_id)
    txn_data = None

    if txn_resp.success and txn_resp.data:
        txn_data = txn_resp.data
    elif txn_resp.is_offline or txn_resp.status_code == 404:
        # Load from local cache for demonstration
        local_cache_path = Path(__file__).resolve().parents[2] / "ml" / "data" / "raw_features.csv"
        if local_cache_path.exists():
            st.warning(
                f"⚠️ **Backend API pending.** Loading Transaction #{txn_id} from local dataset cache.",
                icon="⚠️",
            )
            raw_cache = pd.read_csv(local_cache_path, parse_dates=["TransactionTimestamp", "SenderAccountCreatedAt"])
            matching = raw_cache[raw_cache["TransactionID"] == txn_id]
            if matching.empty:
                txn_id = int(raw_cache["TransactionID"].iloc[0])
                matching = raw_cache[raw_cache["TransactionID"] == txn_id]

            row = matching.iloc[0].to_dict()
            # Predict using Phase 2 inference interface
            from ml.predict import predict_transaction
            score_res = predict_transaction(matching, explain=True)

            txn_data = {
                "transaction_id": txn_id,
                "customer_id": int(row.get("SenderCustomerID", 501)),
                "sender_account_number": int(row.get("SenderAccountNumber", 100000000001)),
                "sender_account_type": str(row.get("SenderAccountType", "Savings")),
                "receiver_account_number": row.get("ReceiverAccountNumber"),
                "receiver_upi_id": row.get("ReceiverUPIID"),
                "merchant_id": row.get("MerchantID"),
                "merchant_category": row.get("MerchantCategory"),
                "amount": float(row.get("Amount", 0.0)),
                "transaction_type": str(row.get("TransactionTypeName", "P2P_UPI")),
                "timestamp": str(row.get("TransactionTimestamp", "")),
                "device_id": row.get("DeviceID"),
                "ip_address": row.get("IPAddress"),
                "location": row.get("Location"),
                "card_reference_token": row.get("CardReferenceToken"),
                "fraud_probability": score_res["fraud_probability"],
                "prediction": score_res["prediction"],
                "risk_status": score_res["risk_status"],
                "model_version": score_res["model_version"],
                "merchant_risk_rate": score_res["merchant_risk_rate"],
                "explanation": score_res.get("explanation"),
            }

    if not txn_data:
        st.error(f"Transaction #{txn_id} not found.")
        return

    # Header Card with Score & Status
    score_col1, score_col2, score_col3, score_col4 = st.columns(4)
    score_col1.metric("Transaction ID", f"#{txn_data['transaction_id']}")
    score_col2.metric("Amount", format_currency(txn_data.get("amount")))
    score_col3.metric("Fraud Probability", format_probability(txn_data.get("fraud_probability")))
    score_col4.metric("Model Version", txn_data.get("model_version", "rf_v1.0"))

    # Badges
    b_col1, b_col2, b_col3 = st.columns(3)
    with b_col1:
        st.markdown(f"**Risk Status:** {get_risk_badge_html(txn_data.get('risk_status'))}", unsafe_allow_html=True)
    with b_col2:
        st.markdown(f"**Prediction:** {get_prediction_badge_html(txn_data.get('prediction'))}", unsafe_allow_html=True)
    with b_col3:
        m_rate = txn_data.get("merchant_risk_rate")
        st.markdown(f"**Merchant Risk Rate:** `{m_rate:.4f}`" if m_rate is not None else "**Merchant Risk Rate:** `N/A`")

    st.markdown("---")

    # Transaction Details Tabs
    t_tab1, t_tab2, t_tab3 = st.tabs(["📋 Transaction Metadata", "📱 Telemetry & Security", "🔍 Risk Attribution"])

    with t_tab1:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Sender & Account Details")
            st.write(f"• **Customer ID:** {txn_data.get('customer_id', 'N/A')}")
            st.write(f"• **Sender Account:** `{txn_data.get('sender_account_number', 'N/A')}`")
            st.write(f"• **Account Type:** {txn_data.get('sender_account_type', 'Savings')}")
            st.write(f"• **Timestamp:** {format_timestamp(txn_data.get('timestamp'))}")
        with c2:
            st.markdown("#### Receiver & Counterparty Details")
            st.write(f"• **Channel:** {txn_data.get('transaction_type', 'N/A')}")
            st.write(f"• **Receiver Account:** `{txn_data.get('receiver_account_number') or 'None'}`")
            st.write(f"• **Receiver UPI ID:** `{txn_data.get('receiver_upi_id') or 'None'}`")
            st.write(f"• **Merchant ID / Category:** `{txn_data.get('merchant_id') or 'N/A'}` ({txn_data.get('merchant_category') or 'N/A'})")

    with t_tab2:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Device & Network Fingerprint")
            st.write(f"• **Device ID:** `{txn_data.get('device_id') or 'None (P2P)'}`")
            st.write(f"• **IP Address:** `{txn_data.get('ip_address') or 'None (P2P)'}`")
            st.write(f"• **Reported Location:** {txn_data.get('location') or 'None (P2P)'}")
        with c2:
            st.markdown("#### Payment Security & Tokenization")
            st.write(f"• **Card Token Reference:** `{txn_data.get('card_reference_token') or 'None'}`")
            st.info("PCI-DSS / RBI Compliance: Real PANs and CVVs are never stored or transmitted.")

    with t_tab3:
        explanation = txn_data.get("explanation")
        if explanation and "top_reasons" in explanation:
            reasons = explanation["top_reasons"]
            st.plotly_chart(plot_shap_contributions(reasons, title=f"Risk Attributions for Txn #{txn_id}"), use_container_width=True)

            # Table of reasons
            st.markdown("##### Detailed Feature Attributions")
            r_df = pd.DataFrame(reasons)
            st.dataframe(r_df, hide_index=True, use_container_width=True)
        else:
            st.info("No SHAP explanation payload attached. Click below to score with explanation.", icon="ℹ️")
            if st.button("Generate SHAP Explanation"):
                st.rerun()
