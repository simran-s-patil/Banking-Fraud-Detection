
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from backend.db_connection import get_connection, test_connection


app = FastAPI(
    title="Banking Fraud Detection API",
    description="Backend API for the Banking Fraud Detection System",
    version="1.0.0",
)


@app.get("/api/v1/health")
def health_check():
    """Check whether the API and MySQL database are working."""

    try:
        database_status = test_connection()

        return {
            "status": "healthy",
            "database_connected": True,
            "mysql_version": database_status["mysql_version"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "database_connected": False,
                "error": "Database connection failed.",
            },
        )


@app.get("/api/v1/overview/metrics")
def get_overview_metrics():
    """Return system-wide transaction and fraud metrics."""

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                COUNT(*) AS total_transactions,
                SUM(
                    CASE WHEN FraudPrediction = 'FRAUDULENT'
                    THEN 1 ELSE 0 END
                ) AS fraudulent_transactions,
                SUM(
                    CASE WHEN FraudPrediction = 'LEGITIMATE'
                    THEN 1 ELSE 0 END
                ) AS legitimate_transactions,
                SUM(
                    CASE WHEN RiskStatus = 'HIGH'
                    THEN 1 ELSE 0 END
                ) AS high_risk_transactions,
                SUM(
                    CASE WHEN FraudPrediction IS NOT NULL
                    THEN 1 ELSE 0 END
                ) AS scored_transactions
            FROM `Transaction`
        """)

        transaction_metrics = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) AS total_customers
            FROM Customer
        """)

        customer_metrics = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) AS open_alerts
            FROM Fraud_Alert
            WHERE ReviewStatus = 'OPEN'
        """)

        alert_metrics = cursor.fetchone()

        total_transactions = transaction_metrics["total_transactions"]
        fraudulent = transaction_metrics["fraudulent_transactions"] or 0
        legitimate = transaction_metrics["legitimate_transactions"] or 0
        high_risk = transaction_metrics["high_risk_transactions"] or 0
        scored = transaction_metrics["scored_transactions"] or 0

        fraud_rate = (
            round((fraudulent / scored) * 100, 2)
            if scored > 0 else 0.0
        )

        return {
            "total_transactions": total_transactions,
            "total_customers": customer_metrics["total_customers"],
            "fraudulent_transactions": fraudulent,
            "legitimate_transactions": legitimate,
            "fraud_rate": fraud_rate,
            "high_risk_transactions": high_risk,
            "open_alerts": alert_metrics["open_alerts"],
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not retrieve overview metrics: {error}",
        ) from error

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()
