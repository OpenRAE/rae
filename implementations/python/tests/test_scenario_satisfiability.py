"""Governed whole-scenario satisfiability analysis (issue #826)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import raes_processor.satisfiability._solver as solver_adapter
import z3
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from raes_contracts.satisfiability import (
    ConstraintClauseKind,
    ConstraintClauseModel,
    ConstraintSort,
    ConstraintSymbolModel,
    NormalizedConstraintModel,
    SatisfiabilityOutcome,
    ScenarioSatisfiabilityEvidenceModel,
)
from raes_processor.satisfiability import (
    SatisfiabilityEvidenceError,
    SatisfiabilityOperationalError,
    analyze_scenario_file,
    replay_satisfiability_evidence,
)
from raes_processor.satisfiability._solver import (
    SOLVER_TIMEOUT_MS,
    SolverOperationalError,
    _check,
    _CheckBudget,
    _select_witness,
    _solver_check_budget,
    solve_model,
)

_SATISFIABLE = """\
name: satisfiable-control
variables:
  platform:
    type: string
    allowed_values: [windows, linux]
    required: true
nodes:
  target:
    type: compute
    os: ${platform}
"""

_UNSATISFIABLE = """\
name: unsatisfiable-control
variables:
  platform:
    type: string
    allowed_values: [linux, allow]
    required: true
nodes:
  target:
    type: compute
    os: ${platform}
infrastructure:
  target:
    acls:
      - action: ${platform}
"""

_UNSUPPORTED = """\
name: unsupported-control
variables:
  cpu_count:
    type: integer
    allowed_values: [1, 2]
    required: true
nodes:
  target:
    type: compute
    resources:
      ram: 1 gib
      cpu: ${cpu_count}
"""

_EMPTY_TARGET_DOMAIN = """\
name: empty-target-domain
variables:
  copies:
    type: integer
    allowed_values: [0]
    required: true
nodes:
  target:
    type: vm
infrastructure:
  target:
    count: ${copies}
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_satisfiable_control_emits_replayable_lexicographic_witness(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)

    evidence = analyze_scenario_file(source)

    assert evidence.outcome is SatisfiabilityOutcome.SATISFIABLE
    assert evidence.witness is not None
    assert evidence.unsat_core is None
    assert evidence.unsupported is None
    bindings = evidence.witness.snapshot.scenario.instantiation_provenance.root_binding_values
    assert bindings == {"platform": "linux"}
    assert replay_satisfiability_evidence(source, evidence) == evidence


def test_unsatisfiable_control_emits_stable_replayable_core(tmp_path: Path) -> None:
    source = _write(tmp_path, "unsatisfiable.sdl.yaml", _UNSATISFIABLE)

    first = analyze_scenario_file(source)
    second = analyze_scenario_file(source)

    assert first.outcome is SatisfiabilityOutcome.UNSATISFIABLE
    assert first.witness is None
    assert first.unsat_core is not None
    assert first.unsupported is None
    assert first.unsat_core.clause_ids == tuple(sorted(first.unsat_core.clause_ids))
    assert len(first.unsat_core.clause_ids) >= 2
    assert first.model_dump_json() == second.model_dump_json()
    assert replay_satisfiability_evidence(source, first) == first


def test_integer_and_boolean_targets_use_finite_domains(tmp_path: Path) -> None:
    source = _write(
        tmp_path,
        "scalar-targets.sdl.yaml",
        """\
name: scalar-targets
variables:
  copies: {type: integer, allowed_values: [2, 0, 1], required: true}
  private: {type: boolean, required: true}
nodes:
  target: {type: compute}
infrastructure:
  target:
    count: ${copies}
    properties:
      cidr: 192.0.2.0/24
      gateway: 192.0.2.1
      internal: ${private}
""",
    )

    evidence = analyze_scenario_file(source)

    assert evidence.outcome is SatisfiabilityOutcome.SATISFIABLE
    assert evidence.witness is not None
    bindings = evidence.witness.snapshot.scenario.instantiation_provenance.root_binding_values
    assert bindings == {"copies": 1, "private": False}


def test_unsupported_construct_fails_closed_with_value_free_diagnostic(tmp_path: Path) -> None:
    source = _write(tmp_path, "unsupported.sdl.yaml", _UNSUPPORTED)

    evidence = analyze_scenario_file(source)

    assert evidence.outcome is SatisfiabilityOutcome.UNSUPPORTED
    assert evidence.witness is None
    assert evidence.unsat_core is None
    assert evidence.unsupported is not None
    assert [item.code for item in evidence.diagnostics] == ["scenario-satisfiability.unsupported-target"]
    rendered = evidence.model_dump_json()
    assert "cpu_count" not in " ".join(item.message for item in evidence.diagnostics)
    assert str(tmp_path) not in rendered


def test_replay_rejects_source_solver_and_payload_mutations(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    evidence = analyze_scenario_file(source)

    source.write_text(_SATISFIABLE.replace("windows, linux", "linux, windows"), encoding="utf-8")
    with pytest.raises(SatisfiabilityEvidenceError, match="source digest"):
        replay_satisfiability_evidence(source, evidence)

    source.write_text(_SATISFIABLE, encoding="utf-8")
    payload = evidence.model_dump(mode="json")
    payload["solver_configuration"]["random_seed"] = 1
    with pytest.raises(ValidationError):
        ScenarioSatisfiabilityEvidenceModel.model_validate(payload)

    payload = evidence.model_dump(mode="json")
    payload["witness"]["snapshot_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError):
        ScenarioSatisfiabilityEvidenceModel.model_validate(payload)


def test_evidence_contract_rejects_cross_outcome_payloads(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    payload = analyze_scenario_file(source).model_dump(mode="json")
    payload["outcome"] = "unsatisfiable"

    with pytest.raises(ValidationError):
        ScenarioSatisfiabilityEvidenceModel.model_validate(payload)


def test_evidence_bytes_are_stable_across_json_round_trip(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    evidence = analyze_scenario_file(source)

    round_tripped = ScenarioSatisfiabilityEvidenceModel.model_validate(json.loads(evidence.model_dump_json()))

    assert json.dumps(evidence.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) == json.dumps(
        round_tripped.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )


def test_stored_evidence_replays_after_model_round_trip(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    evidence = analyze_scenario_file(source)
    stored = ScenarioSatisfiabilityEvidenceModel.model_validate_json(evidence.model_dump_json())

    replayed = replay_satisfiability_evidence(source, stored)

    assert replayed.model_dump(mode="json") == stored.model_dump(mode="json")


def test_domain_order_permutations_have_same_solver_neutral_semantics(tmp_path: Path) -> None:
    first = analyze_scenario_file(_write(tmp_path, "first.sdl.yaml", _SATISFIABLE))
    second = analyze_scenario_file(
        _write(
            tmp_path,
            "second.sdl.yaml",
            _SATISFIABLE.replace("[windows, linux]", "[linux, windows]"),
        )
    )

    assert first.outcome is second.outcome is SatisfiabilityOutcome.SATISFIABLE
    assert first.normalized_model.symbols == second.normalized_model.symbols
    assert first.normalized_model.clauses == second.normalized_model.clauses
    assert first.witness is not None and second.witness is not None
    assert (
        first.witness.snapshot.scenario.instantiation_provenance.root_binding_values
        == second.witness.snapshot.scenario.instantiation_provenance.root_binding_values
        == {"platform": "linux"}
    )


def test_contract_rejects_unknown_fields(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    payload = deepcopy(analyze_scenario_file(source).model_dump(mode="json"))
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        ScenarioSatisfiabilityEvidenceModel.model_validate(payload)


def test_max_length_variable_names_have_bounded_portable_normalized_ids(tmp_path: Path) -> None:
    variable_name = "v" * 64
    source = _write(
        tmp_path,
        "long-identifier.sdl.yaml",
        _SATISFIABLE.replace("platform", variable_name),
    )

    evidence = analyze_scenario_file(source)

    assert evidence.outcome is SatisfiabilityOutcome.SATISFIABLE
    assert all(len(item.symbol_id) == 71 for item in evidence.normalized_model.symbols)


def test_symbol_limit_returns_bounded_unsupported_evidence(tmp_path: Path) -> None:
    variables = "\n".join(f"  flag_{index:03d}: {{type: boolean, required: true}}" for index in range(129))
    source = _write(tmp_path, "symbol-limit.sdl.yaml", f"name: symbol-limit\nvariables:\n{variables}\n")

    evidence = analyze_scenario_file(source)

    assert evidence.outcome is SatisfiabilityOutcome.UNSUPPORTED
    assert len(evidence.normalized_model.symbols) == 128
    assert [item.code for item in evidence.diagnostics] == ["scenario-satisfiability.resource-limit"]


def test_diagnostic_limit_returns_bounded_unsupported_evidence(tmp_path: Path) -> None:
    variables = "\n".join(
        f"  count_{index:03d}: {{type: integer, allowed_values: [1, 2], required: true}}" for index in range(65)
    )
    nodes = "\n".join(
        "\n".join(
            (
                f"  target_{index:03d}:",
                "    type: compute",
                "    resources:",
                "      ram: 1 gib",
                f"      cpu: ${{count_{index:03d}}}",
            )
        )
        for index in range(65)
    )
    source = _write(
        tmp_path,
        "diagnostic-limit.sdl.yaml",
        f"name: diagnostic-limit\nvariables:\n{variables}\nnodes:\n{nodes}\n",
    )

    evidence = analyze_scenario_file(source)

    assert evidence.outcome is SatisfiabilityOutcome.UNSUPPORTED
    assert len(evidence.diagnostics) == 64
    assert "scenario-satisfiability.resource-limit" in {item.code for item in evidence.diagnostics}


def test_clause_limit_returns_bounded_unsupported_evidence(tmp_path: Path) -> None:
    nodes = "\n".join(f"  target_{index:03d}: {{type: compute, os: '${{platform}}'}}" for index in range(512))
    source = _write(
        tmp_path,
        "clause-limit.sdl.yaml",
        "\n".join(
            (
                "name: clause-limit",
                "variables:",
                "  platform: {type: string, allowed_values: [linux, windows], required: true}",
                "nodes:",
                nodes,
                "",
            )
        ),
    )

    evidence = analyze_scenario_file(source)

    assert evidence.outcome is SatisfiabilityOutcome.UNSUPPORTED
    assert len(evidence.normalized_model.clauses) == 512
    assert [item.code for item in evidence.diagnostics] == ["scenario-satisfiability.resource-limit"]


def test_published_valid_and_invalid_fixtures_enforce_outcome_joins() -> None:
    fixtures = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "satisfiability"
    valid = fixtures / "scenario-satisfiability-evidence-v1" / "valid" / "unsupported-target.json"
    invalid = fixtures / "scenario-satisfiability-evidence-v1" / "invalid" / "cross-outcome-payload.json"

    ScenarioSatisfiabilityEvidenceModel.model_validate_json(valid.read_text(encoding="utf-8"))
    invalid_payload = invalid.read_text(encoding="utf-8")
    with pytest.raises(ValidationError) as exc_info:
        ScenarioSatisfiabilityEvidenceModel.model_validate_json(invalid_payload)

    assert "outcome must select exactly one matching payload" in str(exc_info.value)


def _force_unknown_on_call(monkeypatch: pytest.MonkeyPatch, target_call: int) -> None:
    """Make the target solver check report unknown as a timeout proxy."""

    original = z3.Solver.check
    state = {"calls": 0}

    def patched(self: z3.Solver, *assumptions: object) -> z3.CheckSatResult:
        state["calls"] += 1
        if state["calls"] == target_call:
            return z3.unknown
        return original(self, *assumptions)

    monkeypatch.setattr(z3.Solver, "check", patched)


def test_unknown_during_initial_decision_fails_without_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    _force_unknown_on_call(monkeypatch, target_call=1)

    with pytest.raises(SatisfiabilityOperationalError) as exc_info:
        analyze_scenario_file(source)

    error = exc_info.value
    assert error.solver_phase == "initial-decision"
    assert error.solver_check_count == 1
    assert error.solver_check_budget is not None
    assert error.solver_check_budget >= 1


def test_unknown_during_core_reduction_fails_loudly_with_budget_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write(tmp_path, "unsatisfiable.sdl.yaml", _UNSATISFIABLE)
    # Call one is the decisive UNSAT check; call two is the first deletion
    # probe, where accepting unknown would forge subset minimality.
    _force_unknown_on_call(monkeypatch, target_call=2)

    with pytest.raises(SatisfiabilityOperationalError) as exc_info:
        analyze_scenario_file(source)

    error = exc_info.value
    assert error.solver_phase == "core-reduction"
    assert error.solver_check_count == 2
    assert error.solver_check_budget is not None
    assert error.solver_check_budget >= 2
    assert error.solver_timeout_ms == SOLVER_TIMEOUT_MS
    assert error.solver_reason


def test_unknown_during_witness_selection_fails_loudly_with_budget_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    # Call one decides SAT; call two probes the canonical first domain value,
    # where accepting unknown would forge lexicographic selection.
    _force_unknown_on_call(monkeypatch, target_call=2)
    monkeypatch.setattr(z3.Solver, "reason_unknown", lambda _solver: "timeout\n" + ("x" * 300))

    with pytest.raises(SatisfiabilityOperationalError) as exc_info:
        analyze_scenario_file(source)

    error = exc_info.value
    assert error.solver_phase == "witness-selection"
    assert error.solver_check_count == 2
    assert error.solver_check_budget is not None
    assert error.solver_check_budget >= 2
    assert error.solver_timeout_ms == SOLVER_TIMEOUT_MS
    assert error.solver_reason is not None
    assert len(error.solver_reason) == 256
    assert "\n" not in error.solver_reason


def test_operational_errors_render_complete_and_minimal_context() -> None:
    detailed = SatisfiabilityOperationalError(
        "solver failed",
        solver_phase="witness-selection",
        solver_check_count=2,
        solver_check_budget=5,
        solver_timeout_ms=SOLVER_TIMEOUT_MS,
        solver_reason="timeout",
    )
    assert str(detailed) == (
        f"solver failed (phase=witness-selection, check=2/5, timeout_ms={SOLVER_TIMEOUT_MS}, reason=timeout)"
    )

    minimal_service = SatisfiabilityOperationalError("analysis failed")
    assert str(minimal_service) == "analysis failed"

    minimal = SolverOperationalError("solver failed", phase="initial-decision")
    assert minimal.reason is None
    assert str(minimal) == f"solver failed (phase=initial-decision, timeout_ms={SOLVER_TIMEOUT_MS})"


def test_witness_selection_fails_if_a_prior_sat_decision_cannot_be_reproduced(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    model = analyze_scenario_file(source).normalized_model
    session = SimpleNamespace(
        check=lambda *_args, **_kwargs: z3.unsat,
        budget=SimpleNamespace(checks_used=1, max_checks=2),
    )

    with pytest.raises(SolverOperationalError, match="deterministic witness selection failed") as raised:
        _select_witness(
            model,
            tuple(clause.clause_id for clause in model.clauses),
            session,
        )

    assert raised.value.reason == "no-feasible-domain-member-after-sat"


def test_duplicate_clause_ids_rejected_at_solver_boundary(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    model = analyze_scenario_file(source).normalized_model
    # ``model_copy`` bypasses contract validation to inject collapsed identity;
    # the adapter must reject it before tracked-assumption construction.
    duplicated = model.model_copy(update={"clauses": model.clauses + (model.clauses[0],)})

    with pytest.raises(SolverOperationalError, match="duplicate clause ids") as exc_info:
        solve_model(duplicated)

    assert exc_info.value.phase == "model-validation"
    assert exc_info.value.reason == "duplicate-clause-id"


def test_empty_target_domain_is_explicitly_unsatisfiable(tmp_path: Path) -> None:
    source = _write(tmp_path, "empty-target-domain.sdl.yaml", _EMPTY_TARGET_DOMAIN)

    evidence = analyze_scenario_file(source)

    assert evidence.outcome is SatisfiabilityOutcome.UNSATISFIABLE
    assert evidence.unsat_core is not None
    assert any(clause.allowed_values == () for clause in evidence.normalized_model.clauses)


def test_derived_solver_check_budget_fails_closed_before_extra_check(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    model = analyze_scenario_file(source).normalized_model
    clause_ids = tuple(clause.clause_id for clause in model.clauses)
    fixed_indexes: dict[str, int] = {}
    budget = _CheckBudget(max_checks=0)

    with pytest.raises(SolverOperationalError, match="check budget exhausted") as exc_info:
        _check(
            model,
            clause_ids,
            fixed_indexes,
            budget=budget,
            phase="test-probe",
        )

    assert exc_info.value.check_count == 0
    assert exc_info.value.check_budget == 0
    assert exc_info.value.reason == "derived-check-budget-exhausted"


def test_compatibility_check_seam_runs_one_complete_probe(tmp_path: Path) -> None:
    source = _write(tmp_path, "satisfiable.sdl.yaml", _SATISFIABLE)
    model = analyze_scenario_file(source).normalized_model
    clause_ids = tuple(clause.clause_id for clause in model.clauses)

    result = _check(model, clause_ids, {}, budget=_CheckBudget(max_checks=1), phase="test-probe")

    assert result == z3.sat


def test_remaining_timeout_fails_when_no_operation_time_remains(monkeypatch: pytest.MonkeyPatch) -> None:
    budget = _CheckBudget(max_checks=1, started_ns=0)
    monkeypatch.setattr(solver_adapter.time, "monotonic_ns", lambda: budget.deadline_ns)

    with pytest.raises(SolverOperationalError, match="operation deadline exhausted") as raised:
        budget.remaining_timeout_ms("test-probe", check_count=1)

    assert raised.value.phase == "test-probe"
    assert raised.value.reason == "operation-deadline-exhausted"


def _normalized_model(domain_sizes: list[int], masks_by_symbol: list[list[int]]) -> NormalizedConstraintModel:
    symbols = tuple(
        ConstraintSymbolModel(
            symbol_id=f"symbol:{symbol_index:03d}",
            variable=f"value_{symbol_index:03d}",
            sort=ConstraintSort.INTEGER,
            domain=tuple(sorted(range(domain_size), key=lambda value: str(value).encode("utf-8"))),
        )
        for symbol_index, domain_size in enumerate(domain_sizes)
    )
    clauses = tuple(
        ConstraintClauseModel(
            clause_id=f"clause:{symbol_index:03d}:{clause_index:03d}",
            kind=ConstraintClauseKind.TARGET_DOMAIN,
            symbol_id=symbols[symbol_index].symbol_id,
            source_address=f"/nodes/node_{symbol_index:03d}/constraint_{clause_index:03d}",
            allowed_values=tuple(value for value in symbol.domain if mask & (1 << value)),
        )
        for symbol_index, (symbol, masks) in enumerate(zip(symbols, masks_by_symbol, strict=True))
        for clause_index, mask in enumerate(masks)
    )
    return NormalizedConstraintModel(
        profile="raes-finite-domain-constraints/v1",
        theory_profile="raes-finite-domain-theory/v1",
        translation_profile="raes-sdl-authoring-translation/v1",
        source_digest="sha256:" + "1" * 64,
        authored_digest={
            "profile": "raes-sdl-semantic/v2",
            "algorithm": "sha256",
            "value": "sha256:" + "2" * 64,
        },
        symbols=symbols,
        clauses=clauses,
    )


@st.composite
def _bounded_models(draw: st.DrawFn) -> NormalizedConstraintModel:
    domain_sizes = draw(st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=4))
    masks_by_symbol = []
    for domain_size in domain_sizes:
        masks_by_symbol.append(
            draw(
                st.lists(
                    st.integers(min_value=0, max_value=(1 << domain_size) - 1),
                    min_size=0,
                    max_size=4,
                )
            )
        )
    return _normalized_model(domain_sizes, masks_by_symbol)


def _finite_reference(
    model: NormalizedConstraintModel,
) -> tuple[SatisfiabilityOutcome, dict[str, str | int | bool] | tuple[str, ...]]:
    clauses = {clause.clause_id: clause for clause in model.clauses}
    all_clause_ids = tuple(clauses)

    def feasible(clause_ids: tuple[str, ...], fixed: dict[str, int]) -> bool:
        selected = [clauses[clause_id] for clause_id in clause_ids]
        for symbol in model.symbols:
            indexes = [fixed[symbol.symbol_id]] if symbol.symbol_id in fixed else list(range(len(symbol.domain)))
            for clause in selected:
                if clause.symbol_id == symbol.symbol_id:
                    indexes = [index for index in indexes if symbol.domain[index] in clause.allowed_values]
            if not indexes:
                return False
        return True

    if feasible(all_clause_ids, {}):
        fixed: dict[str, int] = {}
        assignment: dict[str, str | int | bool] = {}
        for symbol in model.symbols:
            for index, value in enumerate(symbol.domain):
                if feasible(all_clause_ids, {**fixed, symbol.symbol_id: index}):
                    fixed[symbol.symbol_id] = index
                    assignment[symbol.variable] = value
                    break
        return SatisfiabilityOutcome.SATISFIABLE, assignment
    core = list(all_clause_ids)
    for clause_id in all_clause_ids:
        candidate = tuple(item for item in core if item != clause_id)
        if not feasible(candidate, {}):
            core = list(candidate)
    return SatisfiabilityOutcome.UNSATISFIABLE, tuple(sorted(core))


@given(_bounded_models())
@settings(max_examples=100, deadline=None)
def test_incremental_solver_matches_finite_reference(model: NormalizedConstraintModel) -> None:
    result = solve_model(model)
    expected_outcome, expected_evidence = _finite_reference(model)

    assert result.outcome is expected_outcome
    assert (result.assignment if result.assignment is not None else result.core) == expected_evidence


def test_one_solver_is_constructed_for_all_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _normalized_model([4, 4], [[0b1000], [0b1000]])
    original = solver_adapter.z3.SolverFor
    constructions = 0

    def counted(logic: str):
        nonlocal constructions
        constructions += 1
        return original(logic)

    monkeypatch.setattr(solver_adapter.z3, "SolverFor", counted)

    result = solve_model(model)

    assert result.assignment == {"value_000": 3, "value_001": 3}
    assert constructions == 1


def test_published_maximum_witness_shape_has_a_finite_derived_budget() -> None:
    model = _normalized_model([256] * 128, [[] for _index in range(128)])

    assert _solver_check_budget(model).max_checks == 32_769


def test_operation_deadline_covers_model_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter((0, 0, SOLVER_TIMEOUT_MS * 1_000_000))
    monkeypatch.setattr(solver_adapter.time, "monotonic_ns", clock.__next__)
    model = _normalized_model([1], [[]])

    with pytest.raises(SolverOperationalError, match="operation deadline exhausted") as raised:
        solve_model(model)

    assert raised.value.phase == "model-construction"
    assert raised.value.check_count == 0
    assert raised.value.reason == "operation-deadline-exhausted"


def test_operation_deadline_starts_before_model_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0}
    original_validation = solver_adapter._require_unique_clause_ids

    def validation_finishing_at_deadline(model: NormalizedConstraintModel) -> None:
        original_validation(model)
        clock["now"] = SOLVER_TIMEOUT_MS * 1_000_000

    monkeypatch.setattr(solver_adapter.time, "monotonic_ns", lambda: clock["now"])
    monkeypatch.setattr(solver_adapter, "_require_unique_clause_ids", validation_finishing_at_deadline)
    model = _normalized_model([1], [[]])

    with pytest.raises(SolverOperationalError, match="operation deadline exhausted") as raised:
        solve_model(model)

    assert raised.value.phase == "model-validation"
    assert raised.value.check_count == 0
    assert raised.value.reason == "operation-deadline-exhausted"


def test_result_returned_after_operation_deadline_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0}
    original_check = z3.Solver.check

    def complete_after_deadline(self: z3.Solver, *assumptions: object) -> z3.CheckSatResult:
        result = original_check(self, *assumptions)
        clock["now"] = SOLVER_TIMEOUT_MS * 1_000_000
        return result

    monkeypatch.setattr(solver_adapter.time, "monotonic_ns", lambda: clock["now"])
    monkeypatch.setattr(z3.Solver, "check", complete_after_deadline)
    model = _normalized_model([1], [[]])

    with pytest.raises(SolverOperationalError, match="operation deadline exhausted") as raised:
        solve_model(model)

    assert raised.value.phase == "initial-decision"
    assert raised.value.check_count == 1
    assert raised.value.reason == "operation-deadline-exhausted"


def test_result_selection_finishing_at_operation_deadline_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0}
    original_selection = solver_adapter._select_witness

    def selection_finishing_at_deadline(
        model: NormalizedConstraintModel,
        all_clause_ids: tuple[str, ...],
        session: solver_adapter._SolverSession,
    ) -> dict[str, str | int | bool]:
        assignment = original_selection(model, all_clause_ids, session)
        clock["now"] = SOLVER_TIMEOUT_MS * 1_000_000
        return assignment

    monkeypatch.setattr(solver_adapter.time, "monotonic_ns", lambda: clock["now"])
    monkeypatch.setattr(solver_adapter, "_select_witness", selection_finishing_at_deadline)
    model = _normalized_model([1], [[]])

    with pytest.raises(SolverOperationalError, match="operation deadline exhausted") as raised:
        solve_model(model)

    assert raised.value.phase == "result-selection"
    assert raised.value.check_count == 2
    assert raised.value.reason == "operation-deadline-exhausted"
