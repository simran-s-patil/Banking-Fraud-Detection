"""Fraud Alerts and Investigation Queue Component."""
import streamlit as st

from streamlit_app.api_client import BackendAPIClient
from streamlit_app.utils.formatting import format_currency, format_probability, format_timestamp


def render_alerts(client: BackendAPIClient) -> None:
    """Render the fraud alert queue and investigation review interface."""
    st.markdown("## 🚨 Fraud Alerts & Investigations")
    st.markdown(r"Analyst review queue for transactions classified as HIGH risk ($\ge 0.2100$).")

    # Filter controls
    f_col1, f_col2 = st.columns([2, 1])
    with f_col1:
        status_filter = st.selectbox("Filter by Review Status", ["ALL", "OPEN", "UNDER_REVIEW", "RESOLVED"], index=0)
    with f_col2:
        if st.button("Refresh Alert Queue", use_container_width=True):
            st.rerun()

    # Query alerts from backend
    alerts_resp = client.get_alerts(status=status_filter)

    if alerts_resp.success and alerts_resp.data and "alerts" in alerts_resp.data:
        alerts = alerts_resp.data["alerts"]
        if not alerts:
            st.info("No active fraud alerts matching the selected filter status.", icon="✅")
            return

        st.markdown(f"### Active Alerts ({len(alerts)} records)")
        for alert in alerts:
            with st.expander(f"⚠️ Alert #{alert.get('alert_id')} — Txn #{alert.get('transaction_id')} (Status: {alert.get('review_status', 'OPEN')})"):
                c1, c2 = st.columns(2)
                with c1:
                    st.write(f"• **Created At:** {format_timestamp(alert.get('created_at'))}")
                    st.write(f"• **Fraud Probability:** {format_probability(alert.get('fraud_probability'))}")
                    st.write(f"• **Notes:** {alert.get('notes', 'None')}")
                with c2:
                    st.write(f"• **Assigned Investigator:** {alert.get('assigned_to', 'Unassigned')}")
                    new_status = st.selectbox(
                        "Update Status",
                        ["OPEN", "UNDER_REVIEW", "RESOLVED"],
                        index=["OPEN", "UNDER_REVIEW", "RESOLVED"].index(alert.get("review_status", "OPEN")),
                        key=f"status_{alert.get('alert_id')}",
                    )
                    notes_update = st.text_input("Investigation Notes", value="", key=f"notes_{alert.get('alert_id')}")
                    if st.button("Submit Update", key=f"btn_{alert.get('alert_id')}"):
                        update_payload = {"review_status": new_status, "notes": notes_update}
                        up_resp = client.update_alert_investigation(alert.get("alert_id"), update_payload)
                        if up_resp.success:
                            st.success("Investigation record updated successfully.")
                            st.rerun()
                        else:
                            st.error(f"Failed to update investigation: {up_resp.error}")
    else:
        # Clear, honest pending state — NEVER show fake alerts or fabricated records
        st.info(
            "ℹ️ **Fraud Alert Queue API Pending Implementation (Person 1)**  \n\n"
            "The backend endpoints for alert queries and investigation updates are not yet deployed:  \n"
            "• `GET /api/v1/alerts`  \n"
            "• `PUT /api/v1/alerts/{alert_id}/investigation`  \n\n"
            "Per project safety guidelines, no synthetic or fake alert data is fabricated in the UI. "
            "Once Person 1 completes Phase 4 backend write-back and alert APIs, this queue will automatically populate.",
            icon="ℹ️",
        )

        st.markdown("---")
        st.markdown("### Required Backend API Contract (for Person 1)")
        st.code(
            """# Expected response from GET /api/v1/alerts
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
""",
            language="json",
        )
