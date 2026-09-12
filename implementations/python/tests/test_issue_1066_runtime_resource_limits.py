"""Issue #1066: portable, governed runtime process-resource limits."""

from __future__ import annotations

import copy
import json
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes import SDLValidationError, instantiate_scenario, parse_sdl
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.nodes import (
    RuntimeProcessLimitResource,
    RuntimeProcessResourceLimit,
    RuntimeResourceLimits,
)
from raes.runtime_resource_limits import process_resource_limit_identity_digest
from raes_backend_protocols.manifest import (
    backend_manifest_from_v2_model_with_envelope,
    backend_manifest_v2_model,
)
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.apparatus import (
    ProcessResourceLimitCapability,
    RealizationObservationCapability,
)
from raes_contracts.planning import (
    ChangeAction,
    ProvisioningPlan,
    ProvisionOp,
    RealizationAuthorityMode,
    RuntimeDomain,
)
from raes_contracts.realization_authority import planned_realization_selection_diagnostics
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    realization_envelope_digest,
    realizer_configuration_digest,
)
from raes_contracts.realization_observation import RealizationObservationDisclosure
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import (
    ObservationStrength,
    RealizationSupportMode,
    RealizationVerificationScope,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan, realization_authority_diagnostics
from raes_processor.semantics.realization import (
    CompiledRealizationRequirement,
    RealizationValueConstraint,
    project_realization_concern,
    realization_disclosure,
)
from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

_ADDRESS = "provision.node.worker"
_FIELD_PATH = "nodes.worker.runtime.operational_policy.resource_limits.process_limits"
_ENVELOPE_FIXTURE = (
    Path(__file__).parents[3] / "contracts/fixtures/realization-envelope/realization-envelope-v1/valid/generic.json"
)


def _scenario(process_limits: str, *, variables: str = "", realization: str = "") -> str:
    variable_block = textwrap.dedent(variables).strip()
    realization_block = textwrap.dedent(realization).strip()
    limit_block = textwrap.indent(textwrap.dedent(process_limits).strip(), " " * 12)
    prefix = "\n".join(part for part in ("name: issue-1066-process-limits", variable_block, realization_block) if part)
    return f"""{prefix}
nodes:
  worker:
    type: compute
    resources: {{ram: 1 gib, cpu: 1}}
    runtime:
      processes:
        - name: search
          role: primary
          user: search
      operational_policy:
        resource_limits:
          process_limits:
{limit_block}
"""


def _exact_limit(*, soft: int | str = 65536, hard: int | str = 65536) -> dict[str, object]:
    return {
        "resource": "open_file_descriptors",
        "soft": soft,
        "hard": hard,
        "subject": {"name": "search", "role": "primary"},
        "scope": "subtree",
    }


def _payload(value: object) -> dict[str, object]:
    return {
        "spec": {
            "node": {
                "runtime": {
                    "operational_policy": {
                        "resource_limits": {"process_limits": value},
                    }
                }
            }
        }
    }


def _plan(value: object) -> ProvisioningPlan:
    return ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=_ADDRESS,
                resource_type="node",
                payload=_payload(value),
            )
        ]
    )


def _snapshot(
    value: object,
    *,
    observation_strength: ObservationStrength | None = None,
) -> RuntimeSnapshot:
    observations = ()
    if observation_strength is not None:
        observations = (
            RealizationObservationDisclosure(
                address=_ADDRESS,
                field_path=_FIELD_PATH,
                domain="runtime-realization",
                requirement_kind="process-resource-limits",
                verification_scope=RealizationVerificationScope.CONFIGURATION,
                observation_strength=observation_strength,
            ),
        )
    return RuntimeSnapshot(
        entries={
            _ADDRESS: SnapshotEntry(
                address=_ADDRESS,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="node",
                payload=_payload(value),
            )
        },
        realization_observations=observations,
    )


def _requirement(
    explicitness: ExplicitnessClass,
    *,
    constraints: tuple = (),
) -> CompiledRealizationRequirement:
    return CompiledRealizationRequirement(
        field_path=_FIELD_PATH,
        address=_ADDRESS,
        domain="runtime-realization",
        requirement_kind="process-resource-limits",
        explicitness=explicitness,
        provenance=ExplicitnessProvenance.AUTHOR_DECLARED,
        verification_scope=RealizationVerificationScope.CONFIGURATION,
        required_observation_strength=ObservationStrength.GUEST_OBSERVED,
        value_constraints=constraints,
    )


def _configuration_bound_envelope(
    capability: ProcessResourceLimitCapability,
) -> BackendRealizationEnvelopeModel:
    payload = json.loads(_ENVELOPE_FIXTURE.read_text(encoding="utf-8"))
    payload["configuration"]["process_resource_limits"] = [
        {
            "resource": capability.resource.value,
            "scopes": sorted(scope.value for scope in capability.scopes),
            "minimum": capability.minimum,
            "maximum": capability.maximum,
            "supports_unlimited": capability.supports_unlimited,
        }
    ]
    payload["configuration"]["configuration_digest"] = realizer_configuration_digest(payload["configuration"])
    payload["digest"] = realization_envelope_digest(payload)
    return BackendRealizationEnvelopeModel.model_validate(payload)


def _supporting_manifest(
    *,
    mode: RealizationSupportMode = RealizationSupportMode.CONSTRAINED,
    bind_configuration: bool = True,
    configuration_capability: ProcessResourceLimitCapability | None = None,
):
    manifest = create_stub_manifest()
    declaration = manifest.realization_support[0]
    capability = ProcessResourceLimitCapability(
        resource="open_file_descriptors",
        scopes=frozenset({"subtree"}),
        minimum=1024,
        maximum=1_000_000,
        supports_unlimited=True,
    )
    options = {
        "realization_support": (
            replace(
                declaration,
                support_mode=mode,
                supported_exact_requirement_kinds=(
                    declaration.supported_exact_requirement_kinds | {"runtime-processes"}
                ),
                supported_constraint_kinds=(
                    declaration.supported_constraint_kinds | frozenset({"process-resource-limits"})
                ),
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "process-resource-limits": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                    "runtime-processes": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                },
                process_resource_limits=(capability,),
            ),
        ),
    }
    if bind_configuration:
        options.update(
            supported_contract_versions=manifest.supported_contract_versions | frozenset({"realization-envelope-v1"}),
            realization_envelope=_configuration_bound_envelope(configuration_capability or capability),
        )
    return replace(
        manifest,
        **options,
    )


def test_portable_limit_model_accepts_finite_and_unlimited_pairs() -> None:
    limits = RuntimeResourceLimits(
        process_limits=[
            _exact_limit(),
            {
                "resource": "locked_memory_bytes",
                "soft": 0,
                "hard": "unlimited",
                "subject": {"role": "primary"},
                "scope": "process",
            },
        ]
    )

    assert limits.process_limits[0].resource is RuntimeProcessLimitResource.OPEN_FILE_DESCRIPTORS
    assert limits.process_limits[1].hard == "unlimited"
    assert "open_files" not in RuntimeResourceLimits.model_json_schema()["properties"]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({**_exact_limit(), "soft": -1}, ">= 0"),
        ({**_exact_limit(), "soft": True}, "integer"),
        ({**_exact_limit(), "soft": 10, "hard": 9}, "soft.*hard"),
        ({**_exact_limit(), "resource": "nofile"}, "resource"),
        ({**_exact_limit(), "subject": {}}, "structural selector"),
        ({**_exact_limit(), "subject": {"name": "search-${selector}"}}, "only in soft and hard"),
        ({**_exact_limit(), "scope": "container"}, "scope"),
    ],
)
def test_portable_limit_model_rejects_invalid_or_native_values(value: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        RuntimeProcessResourceLimit.model_validate(value)


def test_process_limit_identities_are_unique_and_match_declared_processes() -> None:
    duplicate_limit = _exact_limit()
    duplicate_limits = [duplicate_limit, copy.deepcopy(duplicate_limit)]
    with pytest.raises(ValidationError, match="Duplicate runtime process resource limit"):
        RuntimeResourceLimits(process_limits=duplicate_limits)

    source = _scenario(
        """
        - resource: open_file_descriptors
          soft: 65536
          hard: 65536
          subject: {name: missing}
          scope: subtree
        """
    )
    with pytest.raises(SDLValidationError, match="does not match any process"):
        parse_sdl(source)

    for unmatched_subject in ("{role: worker}", "{user: missing}", "{command: [/usr/bin/other]}"):
        source = _scenario(
            f"""
        - resource: open_file_descriptors
          soft: 65536
          hard: 65536
          subject: {unmatched_subject}
          scope: subtree
        """
        )
        with pytest.raises(SDLValidationError, match="does not match any process"):
            parse_sdl(source)


def test_redacted_command_selector_requires_a_lossless_stable_identity() -> None:
    for subject in (
        {"command": ["/private/one"], "command_redacted": True},
        {"command": ["/private/two"], "command_redacted": True},
        {"command_redacted": True},
    ):
        limit = {**_exact_limit(), "subject": subject}
        with pytest.raises(ValidationError, match="redacted command|stable projected selector"):
            RuntimeProcessResourceLimit.model_validate(limit)


def test_compiler_preserves_exact_empty_and_constrained_process_limit_posture() -> None:
    absent = compile_runtime_model(
        parse_sdl(
            """
name: issue-1066-absent-process-limits
nodes:
  worker:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    runtime:
      processes:
        - {name: search, role: primary, user: search}
"""
        )
    )
    assert not any(
        requirement.requirement_kind == "process-resource-limits" for requirement in absent.realization_requirements
    )

    exact_empty = compile_runtime_model(parse_sdl(_scenario("[]")))
    empty_requirement = next(
        requirement
        for requirement in exact_empty.realization_requirements
        if requirement.requirement_kind == "process-resource-limits"
    )
    assert empty_requirement.explicitness is ExplicitnessClass.EXACT

    constrained_source = _scenario(
        """
        - resource: open_file_descriptors
          soft: ${soft_limit}
          hard: 65536
          subject: {name: search}
          scope: subtree
        """,
        variables="""
        variables:
          soft_limit:
            type: integer
            default: 32768
            allowed_values: [16384, 32768, 65536]
        """,
    )
    instantiated = instantiate_scenario(parse_sdl(constrained_source))
    model = compile_runtime_model(instantiated)
    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "process-resource-limits"
    )

    assert requirement.explicitness is ExplicitnessClass.CONSTRAINED
    assert len(requirement.value_constraints) == 1
    assert requirement.value_constraints[0].leaf == "soft"
    assert requirement.value_constraints[0].allowed_values == (16384, 32768, 65536)


def test_plan_authority_admits_in_bound_identity_addressed_process_limit() -> None:
    source = _scenario(
        """
        - resource: open_file_descriptors
          soft: ${soft_limit}
          hard: 65536
          subject: {name: search}
          scope: subtree
        """,
        variables="""
        variables:
          soft_limit:
            type: integer
            default: 32768
            allowed_values: [16384, 32768, 65536]
        """,
    )
    execution = plan(
        compile_runtime_model(instantiate_scenario(parse_sdl(source))),
        _supporting_manifest(),
    )
    authority = next(
        entry
        for entry in execution.provisioning.realization_authority
        if entry.requirement_kind == "process-resource-limits"
    )

    assert authority.mode is RealizationAuthorityMode.CONSTRAINED
    assert authority.bounds[0].identity_digest is not None
    assert planned_realization_selection_diagnostics(execution.provisioning) == []


def test_backend_admission_requires_typed_domain_and_guest_observation() -> None:
    model = compile_runtime_model(
        parse_sdl(
            _scenario(
                """
        - resource: open_file_descriptors
          soft: 65536
          hard: 65536
          subject: {name: search}
          scope: subtree
        """
            )
        )
    )

    unsupported = plan(model, create_stub_manifest())
    supported = plan(model, _supporting_manifest())
    too_small_capability = replace(
        _supporting_manifest(),
        realization_support=(
            replace(
                _supporting_manifest().realization_support[0],
                process_resource_limits=(
                    ProcessResourceLimitCapability(
                        resource="open_file_descriptors",
                        scopes=frozenset({"subtree"}),
                        minimum=1024,
                        maximum=4096,
                    ),
                ),
            ),
        ),
    )
    out_of_domain = plan(model, too_small_capability)

    assert any(d.code == "realization.unsupported-process-resource-limits" for d in unsupported.diagnostics)
    assert not any(d.code.startswith("realization.") for d in supported.diagnostics)
    assert any(d.code == "realization.process-resource-limit-domain-mismatch" for d in out_of_domain.diagnostics)


def test_plan_authority_readmission_reconstructs_process_limit_capability_dimensions() -> None:
    model = compile_runtime_model(
        parse_sdl(
            _scenario(
                """
        - resource: open_file_descriptors
          soft: 65536
          hard: 65536
          subject: {name: search}
          scope: subtree
        """
            )
        )
    )
    admitted = plan(model, _supporting_manifest())
    incompatible = replace(
        _supporting_manifest(),
        realization_support=(
            replace(
                _supporting_manifest().realization_support[0],
                process_resource_limits=(
                    ProcessResourceLimitCapability(
                        resource="open_file_descriptors",
                        scopes=frozenset({"subtree"}),
                        minimum=1024,
                        maximum=4096,
                    ),
                ),
            ),
        ),
    )

    diagnostics = realization_authority_diagnostics(admitted.provisioning, incompatible)

    assert [diagnostic.code for diagnostic in diagnostics] == ["realization.process-resource-limit-domain-mismatch"]


def test_backend_admission_requires_the_selected_configuration_to_repeat_the_exact_domain() -> None:
    model = compile_runtime_model(
        parse_sdl(
            _scenario(
                """
        - resource: open_file_descriptors
          soft: 2048
          hard: 2048
          subject: {name: search}
          scope: subtree
        """
            )
        )
    )
    differently_bound = _supporting_manifest(
        configuration_capability=ProcessResourceLimitCapability(
            resource="open_file_descriptors",
            scopes=frozenset({"subtree"}),
            minimum=1024,
            maximum=4096,
            supports_unlimited=False,
        )
    )

    for manifest in (_supporting_manifest(bind_configuration=False), differently_bound):
        planned = plan(model, manifest)
        assert any(
            diagnostic.code == "realization.process-resource-limit-domain-mismatch"
            for diagnostic in planned.diagnostics
        )


def test_typed_apparatus_domain_round_trips_through_backend_manifest_contract() -> None:
    manifest = _supporting_manifest()
    model = backend_manifest_v2_model(manifest)
    capability = model.realization_support[0].process_resource_limits[0]

    assert capability.resource.value == "open_file_descriptors"
    assert [scope.value for scope in capability.scopes] == ["subtree"]
    assert capability.minimum == 1024
    assert capability.maximum == 1_000_000
    assert capability.supports_unlimited is True

    assert manifest.realization_envelope is not None
    restored = backend_manifest_from_v2_model_with_envelope(model, manifest.realization_envelope)
    assert restored.realization_support[0].process_resource_limits == (
        manifest.realization_support[0].process_resource_limits[0],
    )


def test_exact_runtime_gate_rejects_substitution_excess_and_weak_observation() -> None:
    declared = [_exact_limit()]
    requirement = _requirement(ExplicitnessClass.EXACT)
    manifest = _supporting_manifest()

    diagnostics, provenance = realization_disclosure(
        (requirement,),
        _plan(declared),
        _snapshot(declared, observation_strength=ObservationStrength.GUEST_OBSERVED),
        manifest=manifest,
    )
    assert diagnostics == []
    assert provenance

    substituted = [{**_exact_limit(), "soft": 32768}]
    excess = [*declared, {**_exact_limit(), "resource": "locked_memory_bytes"}]
    for observed in (None, substituted, excess):
        snapshot = (
            RuntimeSnapshot(
                realization_observations=_snapshot(
                    declared,
                    observation_strength=ObservationStrength.GUEST_OBSERVED,
                ).realization_observations
            )
            if observed is None
            else _snapshot(observed, observation_strength=ObservationStrength.GUEST_OBSERVED)
        )
        diagnostics, provenance = realization_disclosure(
            (requirement,),
            _plan(declared),
            snapshot,
            manifest=manifest,
        )
        assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
        assert provenance == ()

    diagnostics, provenance = realization_disclosure(
        (requirement,),
        _plan(declared),
        _snapshot(declared, observation_strength=ObservationStrength.DAEMON_OBSERVED),
        manifest=manifest,
    )
    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()


def test_constrained_runtime_gate_accepts_only_the_authored_finite_leaf_domain() -> None:
    declared = [_exact_limit(soft=32768)]
    constraint = RealizationValueConstraint(
        identity_digest=process_resource_limit_identity_digest(declared[0]),
        leaf="soft",
        parameter=("soft_limit",),
        allowed_values=(16384, 32768, 65536),
    )
    requirement = _requirement(ExplicitnessClass.CONSTRAINED, constraints=(constraint,))
    supporting = _supporting_manifest()
    manifest = replace(
        supporting,
        realization_support=(
            replace(
                supporting.realization_support[0],
                supported_exact_requirement_kinds=frozenset(),
            ),
        ),
    )

    accepted = [{**_exact_limit(), "soft": 65536}]
    diagnostics, provenance = realization_disclosure(
        (requirement,),
        _plan(declared),
        _snapshot(accepted, observation_strength=ObservationStrength.GUEST_OBSERVED),
        manifest=manifest,
    )
    assert diagnostics == []
    assert provenance[0].provenance.value == "backend-realized"

    for rejected in (
        [{**_exact_limit(), "soft": 8192}],
        [{**_exact_limit(), "hard": 131072}],
    ):
        diagnostics, provenance = realization_disclosure(
            (requirement,),
            _plan(declared),
            _snapshot(rejected, observation_strength=ObservationStrength.GUEST_OBSERVED),
            manifest=manifest,
        )
        assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
        assert provenance == ()


def test_effective_observation_rejects_unresolved_limit_variables() -> None:
    declared = [_exact_limit()]
    unresolved = [{**_exact_limit(), "soft": "${soft_limit}"}]

    diagnostics, provenance = realization_disclosure(
        (_requirement(ExplicitnessClass.EXACT),),
        _plan(declared),
        _snapshot(unresolved, observation_strength=ObservationStrength.GUEST_OBSERVED),
        manifest=_supporting_manifest(),
    )

    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()


def test_mixed_constrained_collection_preserves_exact_sibling_member() -> None:
    declared = [_exact_limit(soft=32768), {**_exact_limit(), "subject": {"name": "worker", "role": "primary"}}]
    constraint = RealizationValueConstraint(
        identity_digest=process_resource_limit_identity_digest(declared[0]),
        leaf="soft",
        parameter=("soft_limit",),
        allowed_values=(32768, 65536),
    )
    requirement = _requirement(ExplicitnessClass.CONSTRAINED, constraints=(constraint,))
    for hard, accepted in ((65536, True), (131072, False)):
        realized = [{**declared[1], "hard": hard}, {**declared[0], "soft": 65536}]
        diagnostics, provenance = realization_disclosure(
            (requirement,),
            _plan(declared),
            _snapshot(realized, observation_strength=ObservationStrength.GUEST_OBSERVED),
            manifest=_supporting_manifest(),
        )
        assert (not diagnostics) is accepted
        assert bool(provenance) is accepted


def test_open_backend_choice_requires_typed_apparatus_permission_and_is_disclosed() -> None:
    requirement = _requirement(ExplicitnessClass.OPEN)
    selected = [_exact_limit()]

    diagnostics, provenance = realization_disclosure(
        (requirement,),
        _plan([]),
        _snapshot(selected, observation_strength=ObservationStrength.GUEST_OBSERVED),
        manifest=_supporting_manifest(mode=RealizationSupportMode.OPEN_REALIZATION),
    )
    assert diagnostics == []
    assert provenance[0].provenance.value == "backend-realized"

    diagnostics, provenance = realization_disclosure(
        (requirement,),
        _plan([]),
        _snapshot(selected, observation_strength=ObservationStrength.GUEST_OBSERVED),
        manifest=create_stub_manifest(),
    )
    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()

    diagnostics, provenance = realization_disclosure(
        (requirement,),
        _plan([]),
        _snapshot(selected, observation_strength=ObservationStrength.GUEST_OBSERVED),
        manifest=_supporting_manifest(
            mode=RealizationSupportMode.OPEN_REALIZATION,
            bind_configuration=False,
        ),
    )
    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()


def test_backend_boundary_retains_baseline_on_malformed_limit_observation() -> None:
    manifest = _supporting_manifest()
    execution = plan(
        compile_runtime_model(
            parse_sdl(
                _scenario(
                    """
        - resource: open_file_descriptors
          soft: 65536
          hard: 65536
          subject: {name: search, role: primary}
          scope: subtree
        """
                )
            )
        ),
        manifest,
    )

    def backend() -> ApplyResult:
        malformed = [{**_exact_limit(), "native_name": "nofile"}]
        operation = execution.provisioning.operations[0]
        payload = copy.deepcopy(operation.payload)
        payload["spec"]["node"]["runtime"]["operational_policy"]["resource_limits"]["process_limits"] = malformed
        observation_snapshot = _snapshot(
            malformed,
            observation_strength=ObservationStrength.GUEST_OBSERVED,
        )
        return ApplyResult(
            success=True,
            snapshot=RuntimeSnapshot(
                entries={
                    _ADDRESS: SnapshotEntry(
                        address=_ADDRESS,
                        domain=RuntimeDomain.PROVISIONING,
                        resource_type="node",
                        payload=payload,
                    )
                },
                realization_observations=(
                    *observation_snapshot.realization_observations,
                    RealizationObservationDisclosure(
                        address=_ADDRESS,
                        field_path="nodes.worker.runtime.processes",
                        domain="runtime-realization",
                        requirement_kind="runtime-processes",
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                ),
            ),
            changed_addresses=[_ADDRESS],
        )

    baseline = RuntimeSnapshot()
    result = _call_backend_apply(
        backend,
        address="runtime.provision.node.worker",
        snapshot=baseline,
        realization=_RealizationApplyContext(
            plan=execution.provisioning,
            manifest=manifest,
        ),
    )

    assert result.success is False
    assert result.snapshot == baseline
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["runtime.backend-contract-invalid"]


def test_process_limit_projection_is_order_stable_and_redacts_commands() -> None:
    visible_command = ["/usr/bin/search", "--token=abc123"]
    limits = [
        {
            **_exact_limit(),
            "subject": {
                "name": "search",
                "role": "primary",
                "command": visible_command,
            },
        },
        {
            "resource": "locked_memory_bytes",
            "soft": 0,
            "hard": "unlimited",
            "subject": {
                "name": "search",
                "command_redacted": True,
            },
            "scope": "process",
        },
    ]

    projected = project_realization_concern("process-resource-limits", limits)
    reversed_projection = project_realization_concern("process-resource-limits", list(reversed(limits)))

    assert projected == reversed_projection
    assert project_realization_concern("process-resource-limits", projected, observed=True) == projected
    visible_entry = next(item for item in projected if item["resource"] == "open_file_descriptors")
    redacted_entry = next(item for item in projected if item["resource"] == "locked_memory_bytes")
    assert visible_entry["subject"]["command"] == visible_command
    assert "--token=abc123" in repr(visible_entry)
    assert redacted_entry["subject"]["command"] == []
    assert "--token=abc123" not in repr(redacted_entry)


def test_exact_runtime_gate_rejects_a_different_non_redacted_command_selector() -> None:
    declared = [
        {
            **_exact_limit(),
            "subject": {"name": "search", "command": ["/usr/bin/search", "--serve"]},
        }
    ]
    observed = [
        {
            **_exact_limit(),
            "subject": {"name": "search", "command": ["/usr/bin/search", "--maintenance"]},
        }
    ]

    diagnostics, provenance = realization_disclosure(
        (_requirement(ExplicitnessClass.EXACT),),
        _plan(declared),
        _snapshot(observed, observation_strength=ObservationStrength.GUEST_OBSERVED),
        manifest=_supporting_manifest(),
    )

    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-contract-invalid"]
    assert provenance == ()


def test_prepared_node_demands_project_typed_authored_process_limits() -> None:
    from raes_processor.planner.prepared_node_support import _process_limit_demands

    limit = RuntimeProcessResourceLimit.model_validate(_exact_limit())
    demands = _process_limit_demands("process-resource-limits", [limit])

    assert [(demand.resource, demand.soft, demand.hard) for demand in demands] == [
        (limit.resource, limit.soft, limit.hard)
    ]
    assert demands[0].scope.value == limit.scope.value
    assert demands[0].identity_digest


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"resource": "open_file_descriptors"}, "typed collection"),
        ("open_file_descriptors", "typed collection"),
        ([_exact_limit()], "typed runtime limit records"),
    ],
)
def test_prepared_node_demands_refuse_an_untyped_authored_collection(value: object, message: str) -> None:
    from raes_processor.planner.prepared_node_support import _process_limit_demands

    with pytest.raises(ValueError, match=message):
        _process_limit_demands("process-resource-limits", value)
