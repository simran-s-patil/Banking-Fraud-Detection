"""Main Streamlit Application Entry Point for ApexGuard Fraud Detection Dashboard."""
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from streamlit_app.api_client import BackendAPIClient
from streamlit_app.components.alerts import render_alerts
from streamlit_app.components.customer_view import render_customer_view
from streamlit_app.components.fraud_analysis import render_fraud_analysis
from streamlit_app.components.overview import render_overview
from streamlit_app.components.sidebar import render_sidebar
from streamlit_app.components.transaction_view import render_transaction_view
from streamlit_app.config import (
    APP_ICON,
    APP_TITLE,
    BACKEND_BASE_URL,
    CLASSIFICATION_THRESHOLD,
    RISK_LOW_LIMIT,
    RISK_MEDIUM_LIMIT,
)

# Page configuration
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Financial Dashboard Styling
st.markdown(
    """
    <style>
    /* Clean financial dashboard typography and card styling */
    .stMetric {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 12px 16px;
        border-radius: 8px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
    div[data-testid="metric-container"] > label {
        font-size: 0.82rem;
        font-weight: 600;
        color: #64748b;
    }
    div[data-testid="metric-container"] > div {
        font-size: 1.4rem;
        font-weight: 700;
        color: #0f172a;
    }
    /* Headers */
    h1, h2, h3 {
        color: #1e293b;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    /* Tables */
    .stDataFrame {
        border: 1px solid #e2e8f0;
        border-radius: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_system_status(client: BackendAPIClient) -> None:
    """Render system diagnostics, model metadata, and backend contract information."""
    st.markdown("## ⚙️ System & Backend Integration Status")
    st.markdown("Operational environment configuration, model versioning, and integration diagnostics.")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### Machine Learning Model Configuration")
        from ml.config import ModelMetadata
        meta = ModelMetadata()
        st.write(f"• **Model Version:** `{meta.model_version}`")
        st.write(f"• **Model Algorithm:** `{meta.model_type}` (300 Trees)")
        st.write(f"• **Decision Threshold:** `{meta.classification_threshold:.4f}`")
        st.write(f"• **Feature Schema Version:** `{meta.feature_schema_version}` (30 features)")
        st.write(f"• **Model Artifact:** `{Path(meta.model_artifact_path).name}`")
        st.write(f"• **Merchant Risk Encoder:** `{Path(meta.merchant_encoder_artifact_path).name}`")

        st.markdown("#### Operational Risk Bands")
        st.write(f"• **LOW:** `[0.00, {RISK_LOW_LIMIT:.2f})` — Cleared automatically")
        st.write(f"• **MEDIUM:** `[{RISK_LOW_LIMIT:.2f}, {RISK_MEDIUM_LIMIT:.2f})` — Heightened monitoring")
        st.write(f"• **HIGH:** `[{RISK_MEDIUM_LIMIT:.2f}, 1.00]` — Fraud alert generated")

    with c2:
        st.markdown("### Person 1 Backend HTTP Connection")
        st.write(f"• **Backend Base URL:** `{BACKEND_BASE_URL}`")
        health = client.check_health()
        if health.success and health.data:
            st.success("Connected to Backend API service.", icon="✅")
            st.json(health.data)
        else:
            st.warning("Backend API service is currently unreachable / pending.", icon="⚠️")
            st.write(f"• **Connection Error:** {health.error}")

        st.markdown("#### Integration Contract Documentation")
        st.info(
            "Complete HTTP API contract specification is documented at:  \n"
            "`docs/PHASE_3_API_INTEGRATION_CONTRACT.md`",
            icon="📄",
        )


def main():
    """Application controller."""
    client = BackendAPIClient(base_url=BACKEND_BASE_URL)
    selected_page = render_sidebar(client)

    if selected_page == "Overview":
        render_overview(client)
    elif selected_page == "Customer Analysis":
        render_customer_view(client)
    elif selected_page == "Transaction Analysis":
        render_transaction_view(client)
    elif selected_page == "Fraud Explainability (SHAP)":
        render_fraud_analysis(client)
    elif selected_page == "Fraud Alerts & Investigations":
        render_alerts(client)
    elif selected_page == "System & API Contract":
        render_system_status(client)


if __name__ == "__main__":
    main()
