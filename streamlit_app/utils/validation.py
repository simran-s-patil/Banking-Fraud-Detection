"""Input Validation Helpers for Streamlit Frontend."""
from typing import Any


def validate_customer_id(val: Any) -> tuple[bool, int | None, str | None]:
    """Validate customer ID input."""
    if val is None or str(val).strip() == "":
        return False, None, "Customer ID cannot be empty."
    try:
        cid = int(val)
        if cid <= 0:
            return False, None, "Customer ID must be a positive integer."
        return True, cid, None
    except (ValueError, TypeError):
        return False, None, f"Invalid customer ID: '{val}'. Expected an integer."


def validate_transaction_id(val: Any) -> tuple[bool, int | None, str | None]:
    """Validate transaction ID input."""
    if val is None or str(val).strip() == "":
        return False, None, "Transaction ID cannot be empty."
    try:
        tid = int(val)
        if tid <= 0:
            return False, None, "Transaction ID must be a positive integer."
        return True, tid, None
    except (ValueError, TypeError):
        return False, None, f"Invalid transaction ID: '{val}'. Expected an integer."
