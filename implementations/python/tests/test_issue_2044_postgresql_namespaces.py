"""Namespace selection and ownership through the PostgreSQL provider boundary."""

from dataclasses import replace

import pytest
from raes_contracts.errors import ConflictError, OperationalError
from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore, PostgreSQLStoreConfiguration
from raes_runtime.runtime_decisions import runtime_store_digest
from raes_runtime.runtime_resource_ownership import ledger_identity
from test_issue_1435_profile_clause_verification import _LedgerConnection, _LedgerDatabase, _Rows


def configuration(**options):
    return PostgreSQLStoreConfiguration(host="ledger.example", database="rae_ledger", user="rae_ledger", **options)


@pytest.mark.parametrize(
    "namespace",
    ["", "public", "information_schema", "pg_temp", "pg_catalog", "a.b", "a-b", 'a"b', "A", "a b", "a" * 64, 1],
)
def test_namespace_validation_refuses_aliases_and_sql_input(namespace):
    with pytest.raises((TypeError, ValueError), match="namespace"):
        configuration(namespace=namespace)


def test_named_store_identity_is_distinct_and_legacy_digest_is_unchanged():
    legacy = PostgreSQLControlPlaneStore(configuration())
    first = PostgreSQLControlPlaneStore(configuration(namespace="trial_one"))
    second = PostgreSQLControlPlaneStore(configuration(namespace="trial_two"))
    assert ledger_identity(legacy) == ("postgresql-ledger", ("ledger.example", 5432, "rae_ledger", "rae_ledger"))
    assert len({runtime_store_digest(store) for store in (legacy, first, second)}) == 3
    assert runtime_store_digest(first) == runtime_store_digest(
        PostgreSQLControlPlaneStore(configuration(namespace="trial_one"))
    )
    assert ledger_identity(type("Wrapped", (), {"raw_store": first})()) == ledger_identity(first)


@pytest.mark.parametrize("namespace", [None, "a", "a" * 63, "select"])
def test_every_connection_selects_only_the_configured_namespace(monkeypatch, namespace):
    cluster = database(monkeypatch)
    store = PostgreSQLControlPlaneStore(configuration(namespace=namespace))
    for autocommit in (False, True):
        connection = store._connect(autocommit=autocommit)
        try:
            assert connection.namespace == (namespace or "public")
            assert connection.statements[0] == (f'SET search_path TO "{namespace or "public"}", pg_temp', ())
        finally:
            connection.close()
    assert all(connection.closed for connection in cluster.connections)


class Database:
    """Admission metadata segregates only when the real provider selects a path."""

    def __init__(self):
        self.ledgers = {}
        self.locks = {}
        self.connections = []

    def connect(self, **options):
        connection = Connection(self)
        self.connections.append(connection)
        return connection


class Connection(_LedgerConnection):
    def __init__(self, cluster):
        self.cluster = cluster
        self.lock_key = None
        self.namespace = "public"
        self.statements = []
        super().__init__(self._ledger())

    def _ledger(self):
        return self.cluster.ledgers.setdefault(self.namespace, _LedgerDatabase({"schema-version": "5"}))

    def commit(self):
        pass

    def close(self):
        if self.cluster.locks.get(self.lock_key) is self:
            del self.cluster.locks[self.lock_key]
        super().close()

    def execute(self, statement, params=()):
        if not isinstance(statement, str):
            statement = statement.as_string()
        self.statements.append((statement, params))
        if statement.startswith("SET search_path TO "):
            self.namespace = statement.split('"')[1]
            self.database = self._ledger()
            return _Rows([])
        if statement.startswith("SELECT pg_try_advisory_lock"):
            self.lock_key = params[0]
            self.cluster.locks.setdefault(self.lock_key, self)
            return _Rows([(self.cluster.locks[self.lock_key] is self,)])
        if statement.startswith("SELECT EXISTS(SELECT 1 FROM pg_locks"):
            key = (params[0] << 32) | params[1]
            return _Rows([(self.cluster.locks.get(key) is self,)])
        if statement.startswith("SELECT value FROM raes_ledger_metadata WHERE key='owner-generation'"):
            return _Rows([(self.database.metadata.get("owner-generation"),)])
        if statement.startswith("SELECT pg_try_advisory_xact_lock"):
            return _Rows([(params[0] not in self.cluster.locks,)])
        if statement.startswith("SELECT attname FROM pg_attribute"):
            return super().execute(statement, (params[0].rsplit(".", 1)[-1],))
        return super().execute(statement, params)


def database(monkeypatch):
    import psycopg

    cluster = Database()
    monkeypatch.setattr(psycopg, "connect", cluster.connect)
    return cluster


def test_connection_binding_isolates_admission_and_owner_locks(monkeypatch):
    cluster = database(monkeypatch)
    stores = [
        PostgreSQLControlPlaneStore(configuration(namespace=name)) for name in ("engine", "trial_one", "trial_two")
    ]
    leases = []
    try:
        for index, store in enumerate(stores):
            leases.append(store.admit_runtime(target_scope="target:test", run_scope=f"run:{index}"))
        assert len(cluster.locks) == 3
        assert {name: ledger.metadata["run-scope"] for name, ledger in cluster.ledgers.items() if name != "public"} == {
            "engine": "run:0",
            "trial_one": "run:1",
            "trial_two": "run:2",
        }
        duplicate = PostgreSQLControlPlaneStore(replace(configuration(namespace="trial_one"), user="other_role"))
        with pytest.raises(ConflictError, match="runtime owner"):
            duplicate.admit_runtime(target_scope="other", run_scope="run:other")
        for store in stores:
            with store._connection():
                pass
        cluster.locks.pop(leases[1]._connection.lock_key)
        with pytest.raises(OperationalError, match="ownership has ended"), stores[1]._connection():
            pytest.fail("lost lease allowed access")
    finally:
        for lease in leases:
            lease.close()


def test_namespace_reopen_checks_scope_and_advances_only_its_generation(monkeypatch):
    cluster = database(monkeypatch)
    config = configuration(namespace="trial_one")
    first = PostgreSQLControlPlaneStore(config)
    first.admit_runtime(target_scope="target:test", run_scope="run:one").close()
    wrong = PostgreSQLControlPlaneStore(config)
    with pytest.raises(ConflictError, match="scope does not match"):
        wrong.admit_runtime(target_scope="target:test", run_scope="run:two")
    assert not wrong.admitted
    assert not cluster.locks
    reopened = PostgreSQLControlPlaneStore(config)
    lease = reopened.admit_runtime(target_scope="target:test", run_scope="run:one")
    try:
        assert reopened.admit_execution_generation() == 2
        cluster.ledgers["trial_one"].metadata["owner-generation"] = "3"
        with pytest.raises(ConflictError, match="owner is stale"), reopened._connection():
            pytest.fail("stale generation allowed access")
    finally:
        lease.close()


def test_store_can_reacquire_after_an_intervening_owner(monkeypatch):
    database(monkeypatch)
    config = configuration(namespace="trial_one")
    original = PostgreSQLControlPlaneStore(config)
    original.admit_runtime(target_scope="target:test", run_scope="run:one").close()
    intervening = PostgreSQLControlPlaneStore(config)
    intervening.admit_runtime(target_scope="target:test", run_scope="run:one").close()
    lease = original.admit_runtime(target_scope="target:test", run_scope="run:one")
    try:
        assert original.admit_execution_generation() == 3
    finally:
        lease.close()


@pytest.mark.parametrize(
    "field,value", [("target_scope", ""), ("run_scope", ""), ("target_scope", "a" * 257), ("run_scope", None)]
)
def test_direct_scope_validation_precedes_connection(monkeypatch, field, value):
    store = PostgreSQLControlPlaneStore(configuration())
    monkeypatch.setattr(store, "_connect", lambda **_: pytest.fail("invalid scope reached connection"))
    with pytest.raises((TypeError, ValueError), match="scope"):
        store.admit_runtime(**{"target_scope": "target:test", "run_scope": "run:one", field: value})


def test_bootstrap_refuses_a_live_owner_before_ddl(monkeypatch):
    cluster = database(monkeypatch)
    store = PostgreSQLControlPlaneStore(configuration(namespace="trial_one"))
    lease = store.admit_runtime(target_scope="target:test", run_scope="run:one")
    try:
        with pytest.raises(ConflictError, match="runtime owner|bootstrap"):
            PostgreSQLControlPlaneStore(configuration(namespace="trial_one")).initialize_schema()
        assert not any(sql.startswith("CREATE") for conn in cluster.connections for sql, _ in conn.statements)
    finally:
        lease.close()
