
"""Transaction retrieval services for the banking fraud backend."""

from backend.db_connection import get_connection


def get_transaction_by_id(transaction_id):
    """Retrieve one transaction using its ID."""

    query = """
        SELECT
            TransactionID,
            TransactionTimestamp,
            Amount,
            Status,
            SenderAccountNumber,
            ReceiverAccountNumber,
            ReceiverUPIID,
            TransactionTypeID,
            MerchantID,
            FraudScore,
            FraudPrediction,
            RiskStatus
        FROM Transaction
        WHERE TransactionID = %s
    """

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, (transaction_id,))
        transaction = cursor.fetchone()
        cursor.close()

        return transaction

    finally:
        connection.close()


def get_recent_transactions(limit=20):
    """Retrieve the most recent transactions."""

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 500:
        raise ValueError("Limit must be an integer between 1 and 500.")

    query = """
        SELECT
            TransactionID,
            TransactionTimestamp,
            Amount,
            Status,
            SenderAccountNumber,
            ReceiverAccountNumber,
            TransactionTypeID,
            MerchantID,
            FraudScore,
            FraudPrediction,
            RiskStatus
        FROM Transaction
        ORDER BY TransactionTimestamp DESC, TransactionID DESC
        LIMIT %s
    """

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, (limit,))
        transactions = cursor.fetchall()
        cursor.close()

        return transactions

    finally:
        connection.close()

def get_customer_transaction_history(transaction_ids):
    """Retrieve target transactions and all earlier transactions
    belonging to their sender customers.

    Returns:
        {
            "history": [...],
            "raw_transactions": [...]
        }

    History rows are never included in raw_transactions.
    This function only reads from MySQL.
    """

    if not isinstance(transaction_ids, (list, tuple)):
        raise ValueError("transaction_ids must be a list or tuple.")

    if not transaction_ids:
        raise ValueError("transaction_ids cannot be empty.")

    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        for value in transaction_ids
    ):
        raise ValueError("Every transaction ID must be a positive integer.")

    if len(set(transaction_ids)) != len(transaction_ids):
        raise ValueError("Duplicate transaction IDs are not allowed.")

    placeholders = ", ".join(["%s"] * len(transaction_ids))

    base_query = """
        SELECT
            t.TransactionID,
            t.TransactionTimestamp,
            t.Amount,
            tt.TypeName AS TransactionTypeName,
            t.SenderAccountNumber,
            a.CustomerID AS SenderCustomerID,
            at.TypeName AS SenderAccountType,
            a.CreatedAt AS SenderAccountCreatedAt,
            t.ReceiverAccountNumber,
            t.ReceiverUPIID,
            t.MerchantID,
            m.Category AS MerchantCategory,
            t.DeviceID,
            t.IPAddress,
            t.Location,
            t.CardReferenceToken
        FROM `Transaction` t
        JOIN Account a
            ON t.SenderAccountNumber = a.AccountNumber
        JOIN AccountType at
            ON a.AccountTypeID = at.AccountTypeID
        JOIN TransactionType tt
            ON t.TransactionTypeID = tt.TransactionTypeID
        LEFT JOIN Merchant m
            ON t.MerchantID = m.MerchantID
    """

    connection = get_connection()

    try:
        cursor = connection.cursor(dictionary=True)

        # Retrieve the target transactions.
        target_query = (
            base_query
            + f" WHERE t.TransactionID IN ({placeholders})"
            + " ORDER BY t.TransactionTimestamp, t.TransactionID"
        )

        cursor.execute(target_query, tuple(transaction_ids))
        raw_transactions = cursor.fetchall()

        if len(raw_transactions) != len(transaction_ids):
            found_ids = {
                row["TransactionID"] for row in raw_transactions
            }
            missing_ids = set(transaction_ids) - found_ids

            raise ValueError(
                f"Transaction IDs not found: {sorted(missing_ids)}"
            )

        # Identify the sender customers and the earliest target time
        # for each customer.
        customer_start_times = {}

        for row in raw_transactions:
            customer_id = row["SenderCustomerID"]
            timestamp = row["TransactionTimestamp"]

            if (
                customer_id not in customer_start_times
                or timestamp < customer_start_times[customer_id]
            ):
                customer_start_times[customer_id] = timestamp

        # Retrieve every earlier transaction for those customers,
        # including transactions through their other accounts.
        history_conditions = []
        history_parameters = []

        for customer_id, start_time in customer_start_times.items():
            history_conditions.append(
                """
                (
                    a.CustomerID = %s
                    AND (
                        t.TransactionTimestamp < %s
                        OR (
                            t.TransactionTimestamp = %s
                            AND t.TransactionID < %s
                        )
                    )
                )
                """
            )

            # Tie-breaking by TransactionID preserves strict
            # chronological order for transactions at equal timestamps.
            first_target_id = min(
                row["TransactionID"]
                for row in raw_transactions
                if row["SenderCustomerID"] == customer_id
                and row["TransactionTimestamp"] == start_time
            )

            history_parameters.extend(
                [customer_id, start_time, start_time, first_target_id]
            )

        history_query = (
            base_query
            + " WHERE "
            + " OR ".join(history_conditions)
            + " ORDER BY t.TransactionTimestamp, t.TransactionID"
        )

        cursor.execute(history_query, tuple(history_parameters))
        history = cursor.fetchall()

        cursor.close()

        return {
            "history": history,
            "raw_transactions": raw_transactions,
        }

    finally:
        connection.close()
