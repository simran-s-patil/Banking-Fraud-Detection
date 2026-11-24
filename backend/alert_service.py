
"""Fraud alert retrieval services."""

from backend.db_connection import get_connection


VALID_REVIEW_STATUSES = {
    "OPEN",
    "UNDER_REVIEW",
    "FALSE_POSITIVE",
    "CONFIRMED_FRAUD",
    "CLOSED",
}


def get_alert_by_id(alert_id):
    """Retrieve one fraud alert by its ID."""

    if (
        not isinstance(alert_id, int)
        or isinstance(alert_id, bool)
        or alert_id <= 0
    ):
        raise ValueError("alert_id must be a positive integer.")

    query = """
        SELECT
            a.AlertID,
            a.TransactionID,
            a.AlertDate,
            a.RiskScoreAtAlert,
            a.AlertReason,
            a.ReviewStatus,
            t.TransactionTimestamp,
            t.Amount,
            t.SenderAccountNumber,
            t.FraudScore,
            t.FraudPrediction
        FROM Fraud_Alert a
        JOIN `Transaction` t
            ON a.TransactionID = t.TransactionID
        WHERE a.AlertID = %s
    """

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, (alert_id,))
        alert = cursor.fetchone()
        cursor.close()

        return alert

    finally:
        connection.close()


def get_alerts(review_status=None, limit=50):
    """Retrieve fraud alerts, optionally filtered by review status."""

    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 500
    ):
        raise ValueError("limit must be an integer between 1 and 500.")

    if (
        review_status is not None
        and review_status not in VALID_REVIEW_STATUSES
    ):
        raise ValueError("Invalid alert review status.")

    query = """
        SELECT
            a.AlertID,
            a.TransactionID,
            a.AlertDate,
            a.RiskScoreAtAlert,
            a.AlertReason,
            a.ReviewStatus,
            t.TransactionTimestamp,
            t.Amount,
            t.SenderAccountNumber,
            t.FraudScore,
            t.FraudPrediction
        FROM Fraud_Alert a
        JOIN `Transaction` t
            ON a.TransactionID = t.TransactionID
    """

    parameters = []

    if review_status is not None:
        query += " WHERE a.ReviewStatus = %s"
        parameters.append(review_status)

    query += """
        ORDER BY a.AlertDate DESC, a.AlertID DESC
        LIMIT %s
    """

    parameters.append(limit)

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, tuple(parameters))
        alerts = cursor.fetchall()
        cursor.close()

        return alerts

    finally:
        connection.close()

from decimal import Decimal, InvalidOperation


def create_alert(transaction_id, risk_score, alert_reason):
    """Create an alert for an already-scored transaction.

    Returns the new AlertID.
    Raises ValueError for invalid input or an unscored transaction.
    """

    if (
        not isinstance(transaction_id, int)
        or isinstance(transaction_id, bool)
        or transaction_id <= 0
    ):
        raise ValueError("transaction_id must be a positive integer.")

    try:
        score = Decimal(str(risk_score))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("risk_score must be a valid number.")

    if not score.is_finite() or not Decimal("0") <= score <= Decimal("1"):
        raise ValueError("risk_score must be between 0 and 1.")

    if not isinstance(alert_reason, str) or not alert_reason.strip():
        raise ValueError("alert_reason must be a non-empty string.")

    if len(alert_reason.strip()) > 255:
        raise ValueError("alert_reason cannot exceed 255 characters.")

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT FraudScore, FraudPrediction
            FROM `Transaction`
            WHERE TransactionID = %s
            FOR UPDATE
            """,
            (transaction_id,),
        )

        transaction = cursor.fetchone()

        if transaction is None:
            raise ValueError("Transaction does not exist.")

        if transaction[0] is None or transaction[1] is None:
            raise ValueError("Transaction has not been scored yet.")

        if Decimal(str(transaction[0])) != score:
            raise ValueError(
                "risk_score does not match the transaction's stored FraudScore."
            )

        cursor.execute(
            """
            SELECT AlertID
            FROM Fraud_Alert
            WHERE TransactionID = %s
            """,
            (transaction_id,),
        )

        existing_alert = cursor.fetchone()

        if existing_alert is not None:
            raise ValueError("An alert already exists for this transaction.")

        cursor.execute(
            """
            INSERT INTO Fraud_Alert (
                TransactionID,
                RiskScoreAtAlert,
                AlertReason
            )
            VALUES (%s, %s, %s)
            """,
            (transaction_id, score, alert_reason.strip()),
        )

        alert_id = cursor.lastrowid
        connection.commit()

        return alert_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

def update_alert_review_status(alert_id, new_status):
    """Update the review status of an existing fraud alert."""

    if (
        not isinstance(alert_id, int)
        or isinstance(alert_id, bool)
        or alert_id <= 0
    ):
        raise ValueError("alert_id must be a positive integer.")

    if not isinstance(new_status, str) or new_status not in VALID_REVIEW_STATUSES:
        raise ValueError("Invalid alert review status.")

    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT ReviewStatus
            FROM Fraud_Alert
            WHERE AlertID = %s
            FOR UPDATE
            """,
            (alert_id,),
        )

        alert = cursor.fetchone()

        if alert is None:
            raise ValueError("Alert does not exist.")

        cursor.execute(
            """
            UPDATE Fraud_Alert
            SET ReviewStatus = %s
            WHERE AlertID = %s
            """,
            (new_status, alert_id),
        )

        connection.commit()

        return {
            "alert_id": alert_id,
            "previous_status": alert[0],
            "new_status": new_status,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()
