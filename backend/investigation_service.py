
"""Investigation management services."""

from datetime import date

from backend.db_connection import get_connection


VALID_OUTCOMES = {
    "PENDING",
    "CONFIRMED_FRAUD",
    "FALSE_POSITIVE",
    "INCONCLUSIVE",
}

VALID_RESOLUTION_STATUSES = {
    "OPEN",
    "IN_PROGRESS",
    "RESOLVED",
}


def create_investigation(alert_id, investigator_name, notes=None):
    """Create an investigation for an existing fraud alert."""

    if (
        not isinstance(alert_id, int)
        or isinstance(alert_id, bool)
        or alert_id <= 0
    ):
        raise ValueError("alert_id must be a positive integer.")

    if not isinstance(investigator_name, str) or not investigator_name.strip():
        raise ValueError("investigator_name must be non-empty.")

    if len(investigator_name.strip()) > 100:
        raise ValueError("investigator_name cannot exceed 100 characters.")

    if notes is not None and not isinstance(notes, str):
        raise ValueError("notes must be text or None.")

    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT AlertID
            FROM Fraud_Alert
            WHERE AlertID = %s
            FOR UPDATE
            """,
            (alert_id,),
        )

        alert = cursor.fetchone()

        if alert is None:
            raise ValueError("Fraud alert does not exist.")

        cursor.execute(
            """
            SELECT InvestigationID
            FROM Investigation
            WHERE AlertID = %s
            """,
            (alert_id,),
        )

        if cursor.fetchone() is not None:
            raise ValueError("An investigation already exists for this alert.")

        cursor.execute(
            """
            INSERT INTO Investigation (
                AlertID,
                InvestigatorName,
                StartDate,
                Notes
            )
            VALUES (%s, %s, %s, %s)
            """,
            (alert_id, investigator_name.strip(), date.today(), notes),
        )

        investigation_id = cursor.lastrowid
        connection.commit()

        return investigation_id

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

def get_investigation_by_id(investigation_id):
    """Retrieve an investigation with its alert and transaction details."""

    if (
        not isinstance(investigation_id, int)
        or isinstance(investigation_id, bool)
        or investigation_id <= 0
    ):
        raise ValueError("investigation_id must be a positive integer.")

    query = """
        SELECT
            i.InvestigationID,
            i.AlertID,
            i.InvestigatorName,
            i.StartDate,
            i.ResolutionDate,
            i.Notes,
            i.Outcome,
            i.ResolutionStatus,
            a.TransactionID,
            a.RiskScoreAtAlert,
            a.AlertReason,
            a.ReviewStatus,
            t.TransactionTimestamp,
            t.Amount,
            t.SenderAccountNumber
        FROM Investigation i
        JOIN Fraud_Alert a
            ON i.AlertID = a.AlertID
        JOIN `Transaction` t
            ON a.TransactionID = t.TransactionID
        WHERE i.InvestigationID = %s
    """

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, (investigation_id,))
        investigation = cursor.fetchone()
        cursor.close()

        return investigation

    finally:
        connection.close()

def update_investigation(
    investigation_id,
    notes=None,
    outcome=None,
    resolution_status=None,
):
    """Update investigation notes, outcome, and resolution status."""

    if (
        not isinstance(investigation_id, int)
        or isinstance(investigation_id, bool)
        or investigation_id <= 0
    ):
        raise ValueError("investigation_id must be a positive integer.")

    if notes is not None and not isinstance(notes, str):
        raise ValueError("notes must be text or None.")

    if outcome is not None and outcome not in VALID_OUTCOMES:
        raise ValueError("Invalid investigation outcome.")

    if (
        resolution_status is not None
        and resolution_status not in VALID_RESOLUTION_STATUSES
    ):
        raise ValueError("Invalid resolution status.")

    if notes is None and outcome is None and resolution_status is None:
        raise ValueError("At least one field must be provided for update.")

    connection = get_connection()
    cursor = None

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT InvestigationID
            FROM Investigation
            WHERE InvestigationID = %s
            FOR UPDATE
            """,
            (investigation_id,),
        )

        if cursor.fetchone() is None:
            raise ValueError("Investigation does not exist.")

        updates = []
        parameters = []

        if notes is not None:
            updates.append("Notes = %s")
            parameters.append(notes)

        if outcome is not None:
            updates.append("Outcome = %s")
            parameters.append(outcome)

        if resolution_status is not None:
            updates.append("ResolutionStatus = %s")
            parameters.append(resolution_status)

        if resolution_status == "RESOLVED":
            if outcome is None:
                raise ValueError(
                    "An outcome must be provided when resolving an investigation."
                )

            updates.append("ResolutionDate = %s")
            parameters.append(date.today())

        query = (
            "UPDATE Investigation SET "
            + ", ".join(updates)
            + " WHERE InvestigationID = %s"
        )
        parameters.append(investigation_id)

        cursor.execute(query, tuple(parameters))
        connection.commit()

        return get_investigation_by_id(investigation_id)

    except Exception:
        connection.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

def get_investigations(resolution_status=None, outcome=None, limit=50):
    """Retrieve investigations with optional filters."""

    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 500
    ):
        raise ValueError("limit must be an integer between 1 and 500.")

    if (
        resolution_status is not None
        and resolution_status not in VALID_RESOLUTION_STATUSES
    ):
        raise ValueError("Invalid resolution status.")

    if outcome is not None and outcome not in VALID_OUTCOMES:
        raise ValueError("Invalid investigation outcome.")

    query = """
        SELECT
            i.InvestigationID,
            i.AlertID,
            i.InvestigatorName,
            i.StartDate,
            i.ResolutionDate,
            i.Notes,
            i.Outcome,
            i.ResolutionStatus,
            a.TransactionID,
            a.RiskScoreAtAlert,
            a.AlertReason,
            a.ReviewStatus
        FROM Investigation i
        JOIN Fraud_Alert a
            ON i.AlertID = a.AlertID
    """

    conditions = []
    parameters = []

    if resolution_status is not None:
        conditions.append("i.ResolutionStatus = %s")
        parameters.append(resolution_status)

    if outcome is not None:
        conditions.append("i.Outcome = %s")
        parameters.append(outcome)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += """
        ORDER BY i.StartDate DESC, i.InvestigationID DESC
        LIMIT %s
    """

    parameters.append(limit)

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, tuple(parameters))
        investigations = cursor.fetchall()
        cursor.close()

        return investigations

    finally:
        connection.close()
