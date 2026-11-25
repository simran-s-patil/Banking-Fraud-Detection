"""Sidebar Navigation and System Status Component."""
import streamlit as st

from streamlit_app.api_client import BackendAPIClient
from streamlit_app.config import APP_ICON, APP_SUBTITLE, APP_TITLE, BACKEND_BASE_URL


def render_sidebar(client: BackendAPIClient) -> str:
    """Render the sidebar branding, connection status, and navigation menu."""
    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding: 10px 0 15px 0;">
                <h2 style="margin: 0; font-size: 1.5rem; color: #1e3a8a;">{APP_ICON} ApexGuard</h2>
                <p style="margin: 3px 0 0 0; font-size: 0.8rem; color: #64748b;">{APP_SUBTITLE}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # Health & Connectivity Indicator
        health_resp = client.check_health()
        if health_resp.success and health_resp.data and health_resp.data.get("status") == "healthy":
            st.success(f"🟢 **Backend Online**  \n`{BACKEND_BASE_URL}`", icon="✅")
        else:
            st.warning(
                f"🟡 **Backend Disconnected / Pending**  \n"
                f"Target: `{BACKEND_BASE_URL}`  \n"
                f"<small>Person 1 HTTP API offline. Local ML fallback active.</small>",
                icon="⚠️",
            )

        st.markdown("---")
        st.markdown("### Navigation")

        page = st.radio(
            "Go to",
            options=[
                "Overview",
                "Customer Analysis",
                "Transaction Analysis",
                "Fraud Explainability (SHAP)",
                "Fraud Alerts & Investigations",
                "System & API Contract",
            ],
            index=0,
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.markdown(
            """
            <div style="font-size: 0.75rem; color: #94a3b8; line-height: 1.4;">
                <b>Role:</b> Person 2 (ML & Frontend)<br>
                <b>Model:</b> Random Forest (rf_v1.0)<br>
                <b>Threshold:</b> 0.2100<br>
                <b>Database:</b> MySQL 8.x (Restricted)
            </div>
            """,
            unsafe_allow_html=True,
        )

        return page
