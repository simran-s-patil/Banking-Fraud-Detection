"""Secure MySQL connection helper for the banking fraud backend."""

import os
import mysql.connector
from mysql.connector import Error


def get_connection():
    """Create a MySQL connection using environment variables."""

    host = os.getenv("BANKING_DB_HOST", "127.0.0.1")
    port = int(os.getenv("BANKING_DB_PORT", "3306"))
    user = os.getenv("BANKING_DB_USER", "")
    password = os.getenv("BANKING_DB_PASSWORD", "")
    database = os.getenv(
        "BANKING_DB_NAME", "banking_fraud_detection"
    )

    if (
        host in ("localhost", "127.0.0.1", "::1")
        and port == 3306
        and os.getenv("BANKING_DB_ALLOW_LOCAL") != "1"
    ):
        raise RuntimeError("Local MySQL access is not enabled.")

    if not user or not password:
        raise RuntimeError("Database credentials are missing.")

    return mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        connection_timeout=10,
    )


def test_connection():
    """Test the connection and return database information."""

    connection = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT VERSION(), DATABASE()")
        result = cursor.fetchone()
        cursor.close()

        return {
            "status": "connected",
            "mysql_version": result[0],
            "database": result[1],
        }

    except Error as error:
        raise RuntimeError(
            f"MySQL connection failed: {error}"
        ) from error

    finally:
        if connection is not None and connection.is_connected():
            connection.close()