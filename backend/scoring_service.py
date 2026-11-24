
"""Validation helpers for fraud-scoring results.

This module validates model output before database write-back.
It does not run the ML model or modify the database.
"""

from decimal import Decimal, InvalidOperation


VALID_PREDICTIONS = {"LEGITIMATE", "FRAUDULENT"}


def validate_scoring_result(result):
    """Validate one prediction result returned by the ML component.

    Expected fields:
        transaction_id
        fraud_probability
        prediction
        model_version

    Returns a normalized dictionary if valid.
    Raises ValueError if any field is invalid.
    """

    if not isinstance(result, dict):
        raise ValueError("Scoring result must be a dictionary.")

    required_fields = {
        "transaction_id",
        "fraud_probability",
        "prediction",
        "model_version",
    }

    missing_fields = required_fields - result.keys()

    if missing_fields:
        raise ValueError(
            f"Missing required fields: {', '.join(sorted(missing_fields))}"
        )

    transaction_id = result["transaction_id"]

    if (
        not isinstance(transaction_id, int)
        or isinstance(transaction_id, bool)
        or transaction_id <= 0
    ):
        raise ValueError("transaction_id must be a positive integer.")

    try:
        probability = Decimal(str(result["fraud_probability"]))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("fraud_probability must be a valid number.")

    if not probability.is_finite() or not Decimal("0") <= probability <= Decimal("1"):
        raise ValueError("fraud_probability must be between 0 and 1.")

    prediction = result["prediction"]

    if prediction not in VALID_PREDICTIONS:
        raise ValueError(
            "prediction must be LEGITIMATE or FRAUDULENT."
        )

    model_version = result["model_version"]

    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError("model_version must be a non-empty string.")

    return {
        "transaction_id": transaction_id,
        "fraud_probability": probability,
        "prediction": prediction,
        "model_version": model_version.strip(),
    }

def validate_scoring_batch(results):
    """Validate a batch of prediction results.

    Returns a list of normalized results.
    Rejects the entire batch if any result is invalid.
    """

    if not isinstance(results, list):
        raise ValueError("Scoring batch must be a list.")

    if not results:
        raise ValueError("Scoring batch cannot be empty.")

    validated_results = []
    seen_transaction_ids = set()

    for result in results:
        validated = validate_scoring_result(result)

        transaction_id = validated["transaction_id"]

        if transaction_id in seen_transaction_ids:
            raise ValueError(
                f"Duplicate transaction ID in batch: {transaction_id}"
            )

        seen_transaction_ids.add(transaction_id)
        validated_results.append(validated)

    return validated_results
