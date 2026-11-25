"""HTTP REST API Client for Person 1 Backend Services.

Provides typed, resilient communication with the backend API:
- Automatic error handling for network outages, timeouts, and HTTP errors.
- Never connects directly to MySQL.
- Avoids caching volatile data (alerts, investigations).
- Supports local ML inference fallback for demo and offline validation when the backend is offline.
"""
from dataclasses import dataclass
from typing import Any, Literal

import requests

from streamlit_app.config import API_TIMEOUT_SECONDS, BACKEND_BASE_URL


@dataclass
class APIResponse:
    """Standardized API response wrapper."""
    success: bool
    data: Any | None = None
    error: str | None = None
    status_code: int | None = None
    is_offline: bool = False


class BackendAPIClient:
    """Client for communicating with Person 1's backend HTTP endpoints."""

    def __init__(self, base_url: str = BACKEND_BASE_URL, timeout: float = API_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _request(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        endpoint: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> APIResponse:
        """Internal helper to dispatch HTTP request with error catching."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            resp = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.timeout,
            )

            if resp.status_code == 200:
                try:
                    return APIResponse(success=True, data=resp.json(), status_code=200)
                except ValueError:
                    return APIResponse(
                        success=False,
                        error="Backend returned invalid non-JSON response.",
                        status_code=200,
                    )

            # Handle 404 or other HTTP error codes
            try:
                err_data = resp.json()
                msg = err_data.get("error", err_data.get("message", f"HTTP Error {resp.status_code}"))
            except ValueError:
                msg = f"HTTP Error {resp.status_code}: {resp.text[:200]}"

            return APIResponse(success=False, error=msg, status_code=resp.status_code)

        except requests.exceptions.ConnectionError:
            return APIResponse(
                success=False,
                error=f"Cannot connect to backend at {self.base_url}. Service appears offline.",
                is_offline=True,
            )
        except requests.exceptions.Timeout:
            return APIResponse(
                success=False,
                error=f"Backend request timed out after {self.timeout}s.",
                is_offline=True,
            )
        except requests.exceptions.RequestException as e:
            return APIResponse(
                success=False,
                error=f"Network error communicating with backend: {e}",
                is_offline=True,
            )

    def check_health(self) -> APIResponse:
        """Check backend service health and DB connectivity."""
        return self._request("GET", "/api/v1/health")

    def get_overview_metrics(self) -> APIResponse:
        """Retrieve system-wide summary metrics for KPI cards."""
        return self._request("GET", "/api/v1/overview/metrics")

    def get_transactions(
        self,
        limit: int = 50,
        offset: int = 0,
        risk_status: str | None = None,
        prediction: str | None = None,
        transaction_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> APIResponse:
        """Retrieve paginated transactions with optional filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if risk_status and risk_status != "ALL":
            params["risk_status"] = risk_status
        if prediction and prediction != "ALL":
            params["prediction"] = prediction
        if transaction_type and transaction_type != "ALL":
            params["transaction_type"] = transaction_type
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        return self._request("GET", "/api/v1/transactions", params=params)

    def get_transaction_detail(self, transaction_id: int) -> APIResponse:
        """Retrieve complete inspection record for a specific transaction."""
        return self._request("GET", f"/api/v1/transactions/{transaction_id}")

    def search_customers(self, query: str = "") -> APIResponse:
        """Search customers by query string or ID."""
        params = {"q": query} if query else {}
        return self._request("GET", "/api/v1/customers", params=params)

    def get_customer_detail(self, customer_id: int) -> APIResponse:
        """Retrieve customer profile and account details."""
        return self._request("GET", f"/api/v1/customers/{customer_id}")

    def get_customer_transactions(self, customer_id: int) -> APIResponse:
        """Retrieve customer transaction history across all accounts."""
        return self._request("GET", f"/api/v1/customers/{customer_id}/transactions")

    def predict_transaction(self, transaction_data: dict, explain: bool = True) -> APIResponse:
        """Send transaction to backend for fraud scoring."""
        payload = {"transaction": transaction_data, "explain": explain}
        resp = self._request("POST", "/api/v1/predict", json_data=payload)

        # If backend is offline or endpoint 404, fallback to local Phase 2 ML engine
        if not resp.success and (resp.is_offline or resp.status_code == 404):
            try:
                from ml.predict import predict_transaction as local_predict
                local_res = local_predict(transaction_data, explain=explain)
                return APIResponse(
                    success=True,
                    data=local_res,
                    status_code=200,
                    error="Scored via local ML engine (Backend API offline/pending)",
                )
            except Exception as ml_err:
                return APIResponse(
                    success=False,
                    error=f"Backend offline and local scoring failed: {ml_err}",
                    is_offline=True,
                )

        return resp

    def get_alerts(self, status: str | None = None) -> APIResponse:
        """Retrieve active fraud alerts queue."""
        params = {"status": status} if status and status != "ALL" else {}
        return self._request("GET", "/api/v1/alerts", params=params)

    def update_alert_investigation(self, alert_id: int, payload: dict) -> APIResponse:
        """Submit investigation resolution update to backend."""
        return self._request("PUT", f"/api/v1/alerts/{alert_id}/investigation", json_data=payload)
