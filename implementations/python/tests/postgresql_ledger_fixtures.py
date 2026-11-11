"""Disposable PostgreSQL ledger databases for the hosted integration tests.

The CI service container provides one `rae_ledger` database. Each test gets its
own database so that tests on parallel workers never share ledger tables or the
single-owner advisory lock, which PostgreSQL scopes to one database.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

_SERVICE_DATABASE = "rae_ledger"


def ledger_configuration(database: str):
    """Return the store configuration for one database on the CI service."""

    from pydantic import SecretStr
    from raes_runtime.control_plane_store_postgresql import PostgreSQLStoreConfiguration

    # Disposable fixture credentials; no production data or identities.
    return PostgreSQLStoreConfiguration(
        host=os.environ["RAES_TEST_PG_HOST"],
        database=database,
        user="rae_ledger",
        password=SecretStr("integration-only"),
        sslmode="disable",
    )


def _service_connection():
    import psycopg

    configuration = ledger_configuration(_SERVICE_DATABASE)
    return psycopg.connect(
        host=configuration.host,
        dbname=configuration.database,
        user=configuration.user,
        password=configuration.password.get_secret_value(),
        autocommit=True,
    )


@contextmanager
def disposable_ledger_database() -> Iterator[str]:
    """Create one empty ledger database and drop it after the test."""

    from psycopg import sql

    database = f"{_SERVICE_DATABASE}_{uuid4().hex}"
    with _service_connection() as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    try:
        yield database
    finally:
        with _service_connection() as connection:
            # A crashed child process can leave a session open until the server
            # sees the closed socket. End every session before the drop.
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (database,),
            )
            connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
