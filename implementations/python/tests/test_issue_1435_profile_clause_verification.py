"""API-404 clause verification against each control-plane profile (#1435, for #8).

``docs/research/runtime-control-plane/conformance.md`` maps every API-404
clause to the landed code, conformance cases and operator guidance of the
profiles it binds. These cases add the run binding no profile case exercised:
a request for another run through each composition, and a selected P0 store
rebound to another run. They add the actor, scope and owner bindings of a
selected P1 core over the PostgreSQL ledger, through an in-memory stand-in for
its database connection. They also keep that map tied to its clauses, the
profiles' declared guarantees, the requirement's clause-tagged trace lines and
its cited files.
"""

from __future__ import annotations

import ast
import re
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from control_plane_conformance_fixtures import (
    KEY,
    PROFILES,
    RUN_SCOPE,
    ProfileHarness,
    identities,
    profile_harness,
    terminal_audits,
    witness_events,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts.plan_projection import evaluation_plan_model
from raes_contracts.errors import ConflictError
from raes_contracts.planning import ChangeAction, EvaluationOp, EvaluationPlan
from raes_runtime import control_plane_store_postgresql_mutations as ledger_mutations
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_operation_context import runtime_target_scope
from raes_runtime.control_plane_profiles import ControlPlaneProfile, profile_declaration
from raes_runtime.control_plane_store_memory import InMemoryControlPlaneStore
from raes_runtime.control_plane_store_postgresql import PostgreSQLControlPlaneStore, PostgreSQLStoreConfiguration
from raes_runtime.control_plane_store_postgresql_schema import (
    LEDGER_COLUMNS,
    POSTGRES_LEDGER_SCHEMA_VERSION,
    PROJECTION_COLUMNS,
)
from test_issue_1181_unified_control_plane_mutations import _running_record
from test_issue_1185_api_404_profile_alignment import (
    COMMON_GUARANTEES,
    DURABLE_GUARANTEES,
    REQUIREMENT_PATH,
    TRANSPORT_GUARANTEES,
)

pytestmark = pytest.mark.control_plane_conformance

ROOT = Path(__file__).resolve().parents[3]
CONFORMANCE_PAGE = ROOT / "docs/research/runtime-control-plane/conformance.md"
CODE_ROOT = ROOT / "implementations/python/packages/raes_runtime"
TEST_ROOT = Path(__file__).resolve().parent
ADMITTED_RUN = RUN_SCOPE.removeprefix("run:")
ACCEPTED = "accepted"
# How each composition refuses a request whose run differs from its admitted run.
RUN_REFUSALS = {
    "P0": "operation run scope does not match the admitted control-plane store scope",
    "P1": "operation run scope does not match the admitted control-plane store scope",
    "P2": '409 {"detail":"operation conflict"}',
}
# An unregistered plan that carries an operation. P2's route checks planner
# authorization before the core's run check, so it refuses the plan there and
# records its denial audit. P0 and P1 refuse it on the run check.
OPERATION_PLAN_REFUSALS = {
    "P0": (RUN_REFUSALS["P0"], []),
    "P1": (RUN_REFUSALS["P1"], []),
    "P2": (
        '403 {"detail":"evaluation plan is not planner-authorized"}',
        [("submit_evaluation", False, "planner-authorization-mismatch")],
    ),
}
# Written independently of the requirement document: the profiles each clause binds.
CLAUSE_PROFILES = {
    "API-404-C1": {"P0", "P1", "P2"},
    "API-404-C2": {"P1", "P2"},
    "API-404-C3": {"P2"},
    "API-404-C4": {"P0", "P1", "P2"},
}
# The guarantee identifiers API-404 names for each clause, as the #1185 module
# pins them. C4 names none, so it binds every available profile.
CLAUSE_GUARANTEES = {
    "API-404-C1": COMMON_GUARANTEES,
    "API-404-C2": DURABLE_GUARANTEES,
    "API-404-C3": TRANSPORT_GUARANTEES,
    "API-404-C4": set(),
}
_CITED_FILE = re.compile(r"`([\w/]+\.py)(?:::(\w+))?`")
# A link's page, empty for this page, and its optional heading fragment.
_LINK_TARGET = re.compile(r"\]\(([^)#\s]*)(?:#([^)\s]*))?\)")
_HEADING = re.compile(r"^#+ (.+)$", re.MULTILINE)
_NOT_IN_ANCHOR = re.compile(r"[^\w -]")
# A trace line that names its clauses, such as "(API-404-C1/C3 ...".
_CLAUSE_TRACE = re.compile(
    r"^- (?:IMPLEMENTS → CODE_FILE|TESTS → TEST|DOCUMENTS → DOCUMENTATION) `([^`]+)` \(API-404-(C\d(?:/C\d)*)\b",
    re.MULTILINE,
)
# The table cell that holds each kind of traced artifact, and its path prefix.
_TRACE_CELLS = (
    ("implementations/python/packages/raes_runtime/", 2),
    ("implementations/python/tests/", 3),
    ("docs/", 4),
)


def _evaluate(harness: ProfileHarness, plan: EvaluationPlan) -> str:
    """Submit one evaluation plan through the composition's own entry point."""

    if harness.client is not None:
        response = harness.client.post(
            "/operations/evaluation",
            json=evaluation_plan_model(plan).model_dump(mode="json"),
            headers=harness.headers(),
        )
        accepted = response.status_code == 200 and response.json()["accepted"]
        return ACCEPTED if accepted else f"{response.status_code} {response.text}"
    try:
        receipt = harness.plane.submit_evaluation(plan, idempotency_key=KEY, identity=identities()["alice"])
    except ConflictError as refusal:
        return str(refusal)
    return ACCEPTED if receipt.accepted else repr(receipt.diagnostics)


@pytest.mark.parametrize("profile", PROFILES)
def test_request_for_another_run_changes_nothing(profile: str, tmp_path: Path) -> None:
    witness = tmp_path / "effects.jsonl"
    with profile_harness(profile, tmp_path) as harness:
        assert _evaluate(harness, EvaluationPlan(run_id="another-run")) == RUN_REFUSALS[profile]

        assert harness.store.load_records() == {}
        assert harness.store.read_audit() == []
        assert witness_events(witness) == []
        assert harness.snapshot_cut() == ({}, 0)

        # The same plan for the admitted run is accepted, and the same reads see
        # its record, terminal audit, evaluator start and revision.
        assert _evaluate(harness, EvaluationPlan(run_id=ADMITTED_RUN)) == ACCEPTED
        (operation_id,) = harness.store.load_records()
        assert len(terminal_audits(harness.store, operation_id)) == 1
        assert witness_events(witness) == [{"event": "evaluate", "operation_id": operation_id}]
        assert harness.snapshot_cut()[1] == 1


@pytest.mark.parametrize("profile", PROFILES)
def test_plan_with_operations_for_another_run_leaves_no_record_or_effect(profile: str, tmp_path: Path) -> None:
    operation = EvaluationOp(
        action=ChangeAction.CREATE, address="evaluation.assertion.test", resource_type="assertion", payload={}
    )
    refusal, audit = OPERATION_PLAN_REFUSALS[profile]
    with profile_harness(profile, tmp_path) as harness:
        assert _evaluate(harness, EvaluationPlan(run_id="another-run", operations=[operation])) == refusal

        # Read the audit before the snapshot: P2 audits the snapshot read too.
        assert [(event.action, event.allowed, event.reason) for event in harness.store.read_audit()] == audit
        assert harness.store.load_records() == {}
        assert witness_events(tmp_path / "effects.jsonl") == []
        assert harness.snapshot_cut() == ({}, 0)


def test_selected_p0_store_cannot_be_rebound_to_another_run() -> None:
    store = InMemoryControlPlaneStore()
    RuntimeControlPlane(create_stub_target(), store=store, run_scope=RUN_SCOPE, profile=ControlPlaneProfile.P0).close()
    target = create_stub_target()

    with pytest.raises(ConflictError, match="store scope does not match runtime admission"):
        RuntimeControlPlane(target, store=store, run_scope="run:another", profile=ControlPlaneProfile.P0)

    # The refusal leaves the store bound to its first scope, which reopens.
    RuntimeControlPlane(create_stub_target(), store=store, run_scope=RUN_SCOPE, profile=ControlPlaneProfile.P0).close()


class _Rows:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchone(self) -> tuple[object, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _LedgerDatabase:
    """The ledger metadata and owner lock that runtime admission reads and writes."""

    def __init__(self, metadata: dict[str, str]) -> None:
        self.metadata = dict(metadata)
        self.lock_holder: object | None = None
        self.connections: list[_LedgerConnection] = []

    def connect(self, *, autocommit: bool = False) -> _LedgerConnection:
        connection = _LedgerConnection(self)
        self.connections.append(connection)
        return connection


class _LedgerConnection:
    """Answers only the statements of ``PostgreSQLControlPlaneStore.admit_runtime``."""

    def __init__(self, database: _LedgerDatabase) -> None:
        self.database = database
        self.closed = False
        self._pending: dict[str, str] | None = None

    def __enter__(self) -> _LedgerConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self.database.lock_holder is self:
            self.database.lock_holder = None
        self.closed = True

    @contextmanager
    def transaction(self):
        # Metadata changes land only when the transaction body completes.
        self._pending = dict(self.database.metadata)
        try:
            yield
            self.database.metadata = self._pending
        finally:
            self._pending = None

    @contextmanager
    def cursor(self):
        yield self

    def executemany(self, statement: str, rows) -> None:
        assert statement.startswith("INSERT INTO raes_ledger_metadata")
        self._pending.update(rows)

    def execute(self, statement: str, params: tuple[object, ...] = ()) -> _Rows:
        if statement.startswith("SELECT pg_try_advisory_lock"):
            if self.database.lock_holder is None:
                self.database.lock_holder = self
            return _Rows([(self.database.lock_holder is self,)])
        if statement.startswith("SELECT EXISTS(SELECT 1 FROM pg_locks"):
            return _Rows([(self.database.lock_holder is self,)])
        if statement == "SELECT to_regclass(%s)":
            # Admission looks up each ledger table. This ledger has all of them.
            return _Rows([params])
        if statement.startswith("SELECT attname FROM pg_attribute"):
            # Admission reads the columns of each ledger table. This ledger has all of them.
            return _Rows([(name,) for name in {**LEDGER_COLUMNS, **PROJECTION_COLUMNS}[params[0]]])
        if statement.startswith("SELECT key, value FROM raes_ledger_metadata"):
            return _Rows(sorted(self._pending.items()))
        if statement.startswith("INSERT INTO raes_ledger_metadata(key, value) VALUES ('owner-generation'"):
            self._pending["owner-generation"] = params[0]
            return _Rows([])
        raise AssertionError(f"unexpected ledger statement: {statement}")


def _ledger(database: _LedgerDatabase, monkeypatch: pytest.MonkeyPatch) -> PostgreSQLControlPlaneStore:
    ledger = PostgreSQLControlPlaneStore(
        PostgreSQLStoreConfiguration(host="ledger.example", database="rae_ledger", user="rae_ledger")
    )
    monkeypatch.setattr(ledger, "_connect", database.connect)
    return ledger


def _scoped_ledger_metadata() -> dict[str, str]:
    return {
        "schema-version": POSTGRES_LEDGER_SCHEMA_VERSION,
        "target-scope": runtime_target_scope(create_stub_target().name),
        "run-scope": RUN_SCOPE,
        "owner-generation": "1",
    }


@pytest.mark.parametrize(("target_name", "run"), [("other", RUN_SCOPE), ("stub", "run:another")])
def test_selected_p1_refuses_a_postgresql_ledger_for_another_scope(
    target_name: str, run: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _LedgerDatabase(_scoped_ledger_metadata())
    ledger = _ledger(database, monkeypatch)
    target = replace(create_stub_target(), name=target_name)

    # P1 selection accepts the ledger, so the refusal comes from its admission.
    with pytest.raises(ConflictError, match="PostgreSQL ledger scope does not match runtime admission"):
        RuntimeControlPlane(target, store=ledger, run_scope=run, profile=ControlPlaneProfile.P1)

    assert database.metadata == _scoped_ledger_metadata()
    assert database.lock_holder is None
    assert all(connection.closed for connection in database.connections)
    assert not ledger.admitted

    # The ledger's own scope is still admitted, and admission advances its owner generation.
    ledger.admit_runtime(target_scope=runtime_target_scope("stub"), run_scope=RUN_SCOPE)
    assert ledger.admitted
    assert database.metadata["owner-generation"] == "2"


def test_selected_p1_admits_one_postgresql_ledger_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _LedgerDatabase(_scoped_ledger_metadata())
    database.lock_holder = object()
    ledger = _ledger(database, monkeypatch)
    target = create_stub_target()

    with pytest.raises(ConflictError, match="PostgreSQL ledger already has a runtime owner"):
        RuntimeControlPlane(target, store=ledger, run_scope=RUN_SCOPE, profile=ControlPlaneProfile.P1)
    assert database.metadata == _scoped_ledger_metadata()
    assert all(connection.closed for connection in database.connections)
    assert not ledger.admitted

    database.lock_holder = None
    target_scope = runtime_target_scope("stub")
    ledger.admit_runtime(target_scope=target_scope, run_scope=RUN_SCOPE)
    with pytest.raises(ConflictError, match="PostgreSQL ledger already has runtime admission"):
        ledger.admit_runtime(target_scope=target_scope, run_scope=RUN_SCOPE)
    assert database.metadata["owner-generation"] == "2"


def test_postgresql_ledger_claims_stay_with_the_submitting_actor() -> None:
    import sqlite3

    from raes_runtime.control_plane_store_local_codec import encode_payload
    from raes_runtime.control_plane_store_records import _record_payload

    record = _running_record("ledger-actor")
    context = record.receipt.context
    other_actor = context.model_copy(update={"actor_id": f"{context.actor_id}-other"})

    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE raes_ledger_operations(actor_id, operation_kind, idempotency_key, payload, digest)"
        )
        content, digest = encode_payload(_record_payload(record))
        connection.execute(
            "INSERT INTO raes_ledger_operations VALUES (?, ?, ?, ?, ?)",
            (context.actor_id, context.operation_kind.value, record.idempotency_key, content, digest),
        )

        class Parameters:
            def execute(self, statement, parameters):
                return connection.execute(statement.replace("%s", "?"), parameters)

        key = record.idempotency_key
        assert ledger_mutations.find_by_idempotency(None, Parameters(), key, context=context) == record
        assert ledger_mutations.find_by_idempotency(None, Parameters(), key, context=other_actor) is None


def _clause_section() -> str:
    page = CONFORMANCE_PAGE.read_text(encoding="utf-8")
    return page.split("\n## API-404 clause verification\n", 1)[1].split("\n## ", 1)[0]


def _clause_rows() -> dict[str, list[str]]:
    rows = [line.strip().strip("|").split("|") for line in _clause_section().splitlines() if line.startswith("| `API")]
    return {cells[0].strip().strip("`"): [cell.strip() for cell in cells] for cells in rows}


def _declared_profiles(guarantees: set[str]) -> set[str]:
    """Available profiles whose declared guarantees include every given identifier."""

    declarations = [profile_declaration(profile) for profile in ControlPlaneProfile]
    return {
        declaration.profile.value
        for declaration in declarations
        if declaration.available and guarantees <= {claim.identifier for claim in declaration.guarantees}
    }


def test_clause_map_binds_each_clause_to_its_declared_profiles() -> None:
    declared = {clause: _declared_profiles(guarantees) for clause, guarantees in CLAUSE_GUARANTEES.items()}
    # A note after ";" in a cell, such as "P3 is unavailable", binds no profile.
    table = {
        clause: set(re.findall(r"\bP\d\b", cells[1].partition(";")[0])) for clause, cells in _clause_rows().items()
    }

    assert declared == CLAUSE_PROFILES
    assert table == CLAUSE_PROFILES


def _cites_existing(path: str, function: str) -> bool:
    source = (TEST_ROOT if Path(path).name.startswith("test_") else CODE_ROOT) / path
    if not source.is_file():
        return False
    tree = ast.parse(source.read_text(encoding="utf-8"))
    return not function or function in {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def test_clause_map_cites_existing_code_and_tests() -> None:
    rows = _clause_rows()
    # Every entry of each Implementation and Conformance cell must be a citation
    # the pattern reads, so an emptied cell or a narrowed pattern fails here.
    entries = [entry for cells in rows.values() for cell in (cells[2], cells[3]) for entry in cell.split(", ")]
    citations = sorted(set(_CITED_FILE.findall(_clause_section())))

    assert rows.keys() == CLAUSE_PROFILES.keys()
    assert [entry for entry in entries if not _CITED_FILE.fullmatch(entry)] == []
    assert [citation for citation in citations if not _cites_existing(*citation)] == []


def _heading_anchors(page: Path) -> set[str]:
    """The fragments GitHub derives from a page's headings, without duplicate suffixes."""

    headings = _HEADING.findall(page.read_text(encoding="utf-8"))
    return {_NOT_IN_ANCHOR.sub("", heading.strip().lower()).replace(" ", "-") for heading in headings}


def _link_resolves(target: str, fragment: str) -> bool:
    page = CONFORMANCE_PAGE.parent / target if target else CONFORMANCE_PAGE
    return page.is_file() and (not fragment or fragment in _heading_anchors(page))


def test_clause_map_links_resolve() -> None:
    links = _LINK_TARGET.findall(_clause_section())

    assert links
    assert [link for link in links if not _link_resolves(*link)] == []


def test_clause_map_cites_each_clause_tagged_trace_line() -> None:
    rows = _clause_rows()
    traced = _CLAUSE_TRACE.findall(REQUIREMENT_PATH.read_text(encoding="utf-8"))
    missing = []
    for path, clauses in traced:
        for prefix, cell in _TRACE_CELLS:
            if not path.startswith(prefix):
                continue
            for clause in clauses.split("/"):
                cells = rows[f"API-404-{clause}"]
                if prefix == "docs/":
                    pages = {
                        (CONFORMANCE_PAGE.parent / target).resolve() for target, _ in _LINK_TARGET.findall(cells[cell])
                    }
                    cited = (ROOT / path).resolve() in pages
                else:
                    cited = path.removeprefix(prefix) in {file for file, _ in _CITED_FILE.findall(cells[cell])}
                if not cited:
                    missing.append((clause, path))

    assert traced
    assert missing == []
