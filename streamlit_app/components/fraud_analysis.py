"""Fraud Explainability & SHAP Attribution Component."""
from pathlib import Path

import pandas as pd
import streamlit as st

from streamlit_app.api_client import BackendAPIClient
from streamlit_app.components.charts import plot_shap_contributions
from streamlit_app.config import GLOBAL_BAR_PLOT_PATH, GLOBAL_BEESWARM_PLOT_PATH
from streamlit_app.utils.formatting import (
    format_currency,
    format_probability,
    get_prediction_badge_html,
    get_risk_badge_html,
)
from streamlit_app.utils.validation import validate_transaction_id

FEATURE_HUMAN_LABELS = {
    "amount": "Transaction amount",
    "amount_log": "Log-scaled amount magnitude",
    "amount_zscore_sender": "Amount deviation from sender's historical average",
    "hour_of_day": "Transaction hour",
    "is_night": "Late-night transaction hour (12 AM - 6 AM)",
    "is_festival_day": "National/festival shopping holiday",
    "sender_account_age_days": "Account maturity / age",
    "has_sender_history": "Established sender account transaction history",
    "sender_txn_count_10m": "Rapid velocity burst in prior 10 minutes",
    "sender_txn_count_60m": "Transaction velocity in prior 60 minutes",
    "sender_txn_count_1440m": "Daily 24-hour transaction frequency",
    "sender_amount_sum_60m": "Cumulative amount transferred in prior 60 minutes",
    "is_new_receiver": "First-time payment to an unknown receiver",
    "sender_fanout_60m": "Fan-out to multiple distinct receivers in 60 minutes",
    "sender_fanout_1440m": "Fan-out to multiple distinct receivers in 24 hours",
    "is_high_risk_category": "High-risk merchant category (gaming, digital goods, jewellery)",
    "is_new_merchant_for_customer": "First purchase with an unfamiliar merchant",
    "has_device_id": "Device identifier present",
    "has_ip_address": "IP address telemetry present",
    "has_location": "Geographic location telemetry present",
    "has_card_token": "Card tokenization record present",
    "is_merchant_missing": "Missing merchant entity record",
    "device_changed_for_account": "Unfamiliar device change for account",
    "location_changed_for_account": "Geographic location deviation for account",
    "has_device_history": "Established device profile history",
    "merchant_risk_rate": "Historical merchant fraud rate",
    "sender_account_type": "Sender account classification",
    "receiver_shape": "Receiver payment routing shape",
    "merchant_category": "Merchant commercial category",
}


def generate_natural_language_explanation(top_reasons: list[dict], prob: float) -> str:
    """Generate dynamic, human-readable explanation from top SHAP reasons."""
    if not top_reasons:
        return "No specific feature attributions were available for this prediction."

    increasing = [r for r in top_reasons if r.get("direction") == "INCREASES_RISK" or r.get("contribution", 0) > 0]
    decreasing = [r for r in top_reasons if r.get("direction") == "DECREASES_RISK" or r.get("contribution", 0) < 0]

    inc_phrases = [FEATURE_HUMAN_LABELS.get(r["feature"], r["feature"].replace("_", " ")) for r in increasing[:3]]
    dec_phrases = [FEATURE_HUMAN_LABELS.get(r["feature"], r["feature"].replace("_", " ")) for r in decreasing[:2]]

    lines = []
    if prob >= 0.21:
        if inc_phrases:
            lines.append(f"**Primary Risk Drivers:** The model classified this transaction as **high risk** primarily driven by **{', '.join(inc_phrases)}**.")
        if dec_phrases:
            lines.append(f"**Mitigating Factors:** Counterbalancing protective signals included **{', '.join(dec_phrases)}**, but were insufficient to lower the score below threshold.")
    else:
        if dec_phrases:
            lines.append(f"**Legitimate Posture:** The model scored this transaction as **low risk / legitimate** supported by established factors such as **{', '.join(dec_phrases)}**.")
        if inc_phrases:
            lines.append(f"**Observed Anomalies:** Minor risk factors noted: **{', '.join(inc_phrases)}**.")

    lines.append("\n*Note: SHAP values represent statistical feature credit assignment within the Random Forest model and do not constitute legal causality.*")
    return "\n\n".join(lines)


def render_fraud_analysis(client: BackendAPIClient) -> None:
    """Render the explainable AI & SHAP attribution dashboard."""
    st.markdown("## 🔍 Fraud Explainability (SHAP)")
    st.markdown("Transparent feature-attribution and audit explanations for machine learning predictions.")

    tab_local, tab_global = st.tabs(["🎯 Individual Transaction Explanation", "🌐 Global Model Explainability"])

    with tab_local:
        col1, col2 = st.columns([3, 1])
        with col1:
            txn_input = st.text_input("Enter Transaction ID to Explain", value="17", key="exp_txn_id")
        with col2:
            st.button("Explain Transaction", use_container_width=True, key="btn_explain")

        is_valid, txn_id, err_msg = validate_transaction_id(txn_input)
        if not is_valid:
            st.error(f"❌ {err_msg}")
            return

        st.markdown("---")

        # Load transaction and compute explanation
        local_cache_path = Path(__file__).resolve().parents[2] / "ml" / "data" / "raw_features.csv"
        score_res = None

        if local_cache_path.exists():
            raw_cache = pd.read_csv(local_cache_path, parse_dates=["TransactionTimestamp", "SenderAccountCreatedAt"])
            matching = raw_cache[raw_cache["TransactionID"] == txn_id]
            if matching.empty:
                txn_id = int(raw_cache["TransactionID"].iloc[0])
                matching = raw_cache[raw_cache["TransactionID"] == txn_id]

            from ml.predict import predict_transaction
            score_res = predict_transaction(matching, explain=True)

        if not score_res:
            st.error(f"Transaction #{txn_id} could not be loaded or scored.")
            return

        # 1. Summary Cards
        prob = score_res["fraud_probability"]
        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        s_col1.metric("Transaction ID", f"#{txn_id}")
        s_col2.metric("Fraud Probability", format_probability(prob))
        s_col3.metric("Decision", score_res["prediction"])
        s_col4.metric("Risk Status", score_res["risk_status"])

        # 2. Dynamic Explanation Narrative
        explanation = score_res.get("explanation", {})
        top_reasons = explanation.get("top_reasons", [])

        st.markdown("### Decision Narrative")
        narrative = generate_natural_language_explanation(top_reasons, prob)
        if prob >= 0.21:
            st.error(narrative)
        else:
            st.success(narrative)

        # 3. Horizontal SHAP Contribution Plot
        st.markdown("### Local Feature Contributions (SHAP Values)")
        st.plotly_chart(
            plot_shap_contributions(top_reasons, title=f"Directional Feature Contributions (Txn #{txn_id})"),
            use_container_width=True,
        )

        # 4. Table breakdown
        st.markdown("### Top Contributing Features")
        reasons_data = []
        for r in top_reasons:
            reasons_data.append({
                "Feature Name": r["feature"],
                "Description": FEATURE_HUMAN_LABELS.get(r["feature"], r["feature"]),
                "SHAP Contribution (Probability Impact)": f"{r['contribution']:+.4f}",
                "Direction": "🔴 Increases Fraud Risk" if r["direction"] == "INCREASES_RISK" else "🟢 Decreases Fraud Risk",
            })
        st.dataframe(pd.DataFrame(reasons_data), hide_index=True, use_container_width=True)

    with tab_global:
        st.markdown("### Global Random Forest Model Explainability")
        st.markdown("Attributions derived from $N=400$ sampled validation transactions across the 300-tree ensemble.")

        g_col1, g_col2 = st.columns(2)

        with g_col1:
            st.markdown("#### Mean |SHAP| Global Feature Importance")
            if GLOBAL_BAR_PLOT_PATH.exists():
                st.image(str(GLOBAL_BAR_PLOT_PATH), caption="Ranking of Top 20 Global Model Drivers")
            else:
                st.info("Global bar plot artifact pending generation.")

        with g_col2:
            st.markdown("#### SHAP Summary (Beeswarm) Plot")
            if GLOBAL_BEESWARM_PLOT_PATH.exists():
                st.image(str(GLOBAL_BEESWARM_PLOT_PATH), caption="Feature Value Distribution vs Directional Risk Impact")
            else:
                st.info("Global beeswarm plot artifact pending generation.")
