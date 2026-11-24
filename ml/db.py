"""MySQL connection helper for the ML pipeline.

Defaults point at the disposable test instance (127.0.0.1:33070), never at
the user's real database. Connecting to port 3306 requires an explicit
opt-in (ML_ALLOW_PORT_3306=1) so a stray default can never reach it.
Credentials are read from environment variables only, never hardcoded,
logged, or written to any output file.
"""
import os

import mysql.connector

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 33070
DEFAULT_DB = "banking_fraud_detection"
DEFAULT_USER = "root"


def get_connection():
    host = os.environ.get("ML_DB_HOST", DEFAULT_HOST)
    port = int(os.environ.get("ML_DB_PORT", DEFAULT_PORT))
    user = os.environ.get("ML_DB_USER", DEFAULT_USER)
    password = os.environ.get("ML_DB_PASSWORD", "")
    database = os.environ.get("ML_DB_NAME", DEFAULT_DB)

    is_real_db = port == 3306 and host in ("localhost", "127.0.0.1", "::1")
    if is_real_db and os.environ.get("ML_ALLOW_PORT_3306") != "1":
        raise RuntimeError(
            "Refusing to connect to port 3306 (the user's real database) without "
            "explicit permission. Set ML_ALLOW_PORT_3306=1 only if the user has "
            "explicitly approved this connection for this run."
        )

    return mysql.connector.connect(
        host=host, port=port, user=user, password=password, database=database
    )
