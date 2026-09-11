"""Issue #1212 scoped observation and reporting-demand acceptance tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes import SDLValidationError
from raes.evidence_requirements import EvidenceRequirement
from raes.parser import parse_sdl
from raes_backend_stubs.manifest import create_stub_manifest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import ExperimentCaptureSpecModel, ExperimentSpecModel, ExperimentTaskModel, schema_bundle
from raes_contracts.observation_demand import (
    AchievedObservationValue,
    EffectiveObservationDemand,
    ObservationBasis,
    ObservationDemandDocument,
    ObservationDemandMode,
    ObservationDemandResolution,
    ObservationDemandRule,
    ObservationLifecycleDecision,
    ObservationLifecycleItem,
    ObservationLifecycleStage,
    ObservationPurpose,
    ObservationSelector,
    execute_observation_lifecycle,
    normalize_observation_demands,
    realization_description_report,
)
from raes_contracts.plan_projection import provisioning_plan_digest, provisioning_plan_model, runtime_plan_digest
from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
from raes_contracts.realization_observation import compute_substrate_readback_addresses
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api_models import _provisioning_plan
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.manager import RuntimeManager
from raes_runtime.observation_execution import (
    ConfiguredObservationRuntime,
    ObservationRuntimeCapability,
    ObservationSelectorPattern,
)
from raes_runtime.registry import RuntimeTarget

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _fixture(relative: str) -> dict[str, object]:
    return json.loads((_REPO_ROOT / relative).read_text(encoding="utf-8"))


def _selector(
    scope: str,
    name: str,
    *,
    kind: str = "stream",
    component_refs: tuple[str, ...] = (),
    coverage_profile: str | None = None,
    max_items: int | None = None,
) -> ObservationSelector:
    return ObservationSelector(
        semantic_scope=scope,
        component_refs=component_refs,
        data_kind=kind,
        names=(name,),
        coverage_profile=coverage_profile,
        max_items=max_items,
    )


def _document(*rules: ObservationDemandRule) -> ObservationDemandDocument:
    return ObservationDemandDocument(
        schema_version="observation-demand/v1",
        document_id="issue-1212",
        scope_profile="recursive-realization-constraint/v1",
        rules=rules,
    )


def _runtime_target(base: RuntimeTarget, observation_runtime: ConfiguredObservationRuntime) -> RuntimeTarget:
    return RuntimeTarget(
        name=base.name,
        manifest=base.manifest,
        provisioner=base.provisioner,
        orchestrator=base.orchestrator,
        evaluator=base.evaluator,
        participant_runtime=base.participant_runtime,
        time_runtime=base.time_runtime,
        observation_runtime=observation_runtime,
    )


def _runtime_capability(
    selector: ObservationSelector,
    *,
    stages: frozenset[ObservationLifecycleStage],
    bases: frozenset[ObservationBasis] = frozenset(),
    redaction_policies: frozenset[str] = frozenset(),
    integrity_policies: frozenset[str] = frozenset(),
) -> ObservationRuntimeCapability:
    scope_tokens = selector.semantic_scope.split("/")
    scope_family = f"/{scope_tokens[1]}" if len(scope_tokens) > 1 and scope_tokens[1] else ""
    capability_id = _runtime_capability_id(selector)
    return ObservationRuntimeCapability(
        capability_id=capability_id,
        selector_pattern=ObservationSelectorPattern(
            data_kind=selector.data_kind,
            names=frozenset(selector.names),
            semantic_scope_prefix=scope_family,
            component_ref_prefixes=tuple(
                dict.fromkeys(reference.rsplit(".", 1)[0] for reference in selector.component_refs)
            ),
            window_refs=frozenset(selector.window_refs),
            coverage_profiles=(
                frozenset({selector.coverage_profile}) if selector.coverage_profile is not None else frozenset()
            ),
            max_items=selector.max_items,
        ),
        capture_kind="trace",
        channel_kind="runtime-snapshot",
        stages=stages,
        bases=bases,
        redaction_policies=redaction_policies,
        integrity_policies=integrity_policies,
    )


def _runtime_capability_id(selector: ObservationSelector) -> str:
    scope_family = selector.semantic_scope.split("/")[1] if selector.semantic_scope else "root"
    return f"{scope_family}:{selector.data_kind}:{'|'.join(selector.names)}"


def _test_protector(item: ObservationLifecycleItem, _demand: object) -> ObservationLifecycleItem:
    return ObservationLifecycleItem(item.selector_key, item.values, "sha256:test-integrity")


def test_exact_environment_has_no_implicit_experimental_collection_retention_or_export() -> None:
    """Environment precision is independent from an absent observation-demand document."""

    called: list[str] = []
    result = execute_observation_lifecycle(
        normalize_observation_demands(None, target_scopes=("/nodes/kali",)),
        producers={
            "/nodes/kali|stream|filesystem-trace": lambda: called.append("filesystem") or ("event",),
            "/nodes/kali|stream|package-scan": lambda: called.append("packages") or ("nmap",),
        },
        supported=frozenset(
            {
                "/nodes/kali|stream|filesystem-trace",
                "/nodes/kali|stream|package-scan",
            }
        ),
    )

    assert called == []
    assert result.collected == result.retained == result.exported == ()


def test_effective_none_mode_cannot_carry_collection_work() -> None:
    selector = _selector("/nodes/kali", "filesystem-trace")

    with pytest.raises(ValueError, match="none observation demand cannot select or process data"):
        EffectiveObservationDemand(
            scope="/nodes/kali",
            purpose="experimental",
            mode="none",
            selectors=(selector,),
            collection="require",
            retention="disable",
            export="disable",
            basis="observed",
        )


@pytest.mark.parametrize("mode", [ObservationDemandMode.SELECTED, ObservationDemandMode.EXHAUSTIVE])
def test_same_environment_can_select_or_exhaustively_observe_a_supported_scope(mode: ObservationDemandMode) -> None:
    selector = _selector(
        "/nodes/kali",
        "filesystem-trace",
        coverage_profile="modeled-files/v1" if mode is ObservationDemandMode.EXHAUSTIVE else None,
        max_items=64 if mode is ObservationDemandMode.EXHAUSTIVE else None,
    )
    document = _document(
        ObservationDemandRule(
            rule_id="filesystem",
            scope="/nodes/kali",
            purpose=ObservationPurpose.EXPERIMENTAL,
            mode=mode,
            selector=selector,
            collection=ObservationLifecycleDecision.REQUIRE,
            redaction="redact-sensitive",
            integrity="checksum",
        )
    )
    key = selector.key
    result = execute_observation_lifecycle(
        normalize_observation_demands(document, target_scopes=("/nodes/kali",)),
        producers={key: lambda: ("open:/etc/example",)},
        supported=frozenset({key}),
        protector=_test_protector,
    )

    assert tuple(item.selector_key for item in result.collected) == (key,)
    assert result.retained == result.exported == ()


def test_abstract_action_trace_does_not_require_concrete_machine_detail() -> None:
    selector = _selector(
        "/abstract/computers",
        "actions",
        coverage_profile="declared-transition-system/v1",
        max_items=6,
    )
    document = _document(
        ObservationDemandRule(
            rule_id="all-actions",
            scope="/abstract/computers",
            purpose="experimental",
            mode="exhaustive",
            selector=selector,
            collection="require",
            export="require",
            redaction="redact-sensitive",
            integrity="checksum",
        )
    )
    trace = ({"actor": "a", "action": "increment"}, {"actor": "a", "action": "send"})
    result = execute_observation_lifecycle(
        normalize_observation_demands(document, target_scopes=("/abstract/computers",)),
        producers={selector.key: lambda: trace},
        supported=frozenset({selector.key}),
        protector=_test_protector,
    )

    assert result.exported[0].values == trace
    assert all(token not in selector.key for token in ("os", "package", "packet"))


def test_mixed_scopes_keep_operational_collection_and_experimental_lifecycle_independent() -> None:
    packets = _selector("/links/observed", "packets")
    health = _selector("/nodes/operational", "health")
    silent = _selector("/nodes/silent", "trace")
    document = _document(
        ObservationDemandRule(
            rule_id="packets",
            scope="/links/observed",
            purpose="experimental",
            mode="selected",
            selector=packets,
            collection="require",
            retention="require",
            export="disable",
            redaction="redact-sensitive",
            integrity="checksum",
        ),
        ObservationDemandRule(
            rule_id="operational",
            scope="/nodes/operational",
            purpose="operational",
            mode="operational-only",
            selector=health,
            collection="require",
        ),
        ObservationDemandRule(
            rule_id="silent",
            scope="/nodes/silent",
            purpose="experimental",
            mode="none",
            prohibited_stages=("collection", "retention", "export"),
        ),
    )
    called: list[str] = []

    def producer(key: str):
        return lambda: called.append(key) or ("event",)

    result = execute_observation_lifecycle(
        normalize_observation_demands(
            document,
            target_scopes=("/links/observed", "/nodes/operational", "/nodes/silent"),
        ),
        producers={item.key: producer(item.key) for item in (packets, health, silent)},
        supported=frozenset(item.key for item in (packets, health, silent)),
        protector=_test_protector,
    )

    assert called == [packets.key, health.key]
    assert tuple(item.selector_key for item in result.collected) == (packets.key,)
    assert result.retained == result.collected
    assert result.exported == ()
    assert result.operational_count == 1


def test_restrictive_descendant_partitions_broad_selector_without_rejecting_allowed_siblings() -> None:
    broad_selector = _selector("/nodes", "filesystem-trace")
    resolution = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="broad-trace",
                scope="/nodes",
                purpose="experimental",
                mode="selected",
                selector=broad_selector,
                collection="require",
                retention="require",
                redaction="none",
                integrity="none",
            ),
            ObservationDemandRule(
                rule_id="sensitive-none",
                scope="/nodes/sensitive",
                purpose="experimental",
                mode="none",
            ),
        ),
        target_scopes=("/nodes", "/nodes/sensitive"),
    )

    assert resolution.is_valid
    broad = next(demand for demand in resolution.effective if demand.scope == "/nodes")
    child = next(demand for demand in resolution.effective if demand.scope == "/nodes/sensitive")
    assert child.mode is ObservationDemandMode.NONE
    assert broad.selectors[0].excluded_scopes == ("/nodes/sensitive",)
    calls: list[str] = []
    result = execute_observation_lifecycle(
        resolution,
        producers={broad.selectors[0].key: lambda: calls.append("allowed-remainder") or ("event",)},
        supported=frozenset({broad.selectors[0].key}),
    )
    assert calls == ["allowed-remainder"]
    assert len(result.retained) == 1


def test_unsupported_or_prohibited_required_work_fails_before_any_producer() -> None:
    packets = _selector("/links/red", "packets")
    called: list[str] = []
    unsupported = _document(
        ObservationDemandRule(
            rule_id="packets",
            scope="/links/red",
            purpose="experimental",
            mode="selected",
            selector=packets,
            collection="require",
            required=True,
            redaction="redact-sensitive",
            integrity="checksum",
        )
    )
    unsupported_resolution = normalize_observation_demands(unsupported, target_scopes=("/links/red",))
    with pytest.raises(ValueError, match="unsupported-required-observation"):
        execute_observation_lifecycle(
            unsupported_resolution,
            producers={packets.key: lambda: called.append("called") or ()},
            supported=frozenset(),
        )
    assert called == []

    conflict = _document(
        ObservationDemandRule(
            rule_id="root-ban",
            scope="",
            purpose="experimental",
            mode="none",
            prohibited_stages=(ObservationLifecycleStage.COLLECTION,),
        ),
        ObservationDemandRule(
            rule_id="child-request",
            scope="/links/red",
            purpose="experimental",
            mode="selected",
            selector=packets,
            collection="require",
            required=True,
            redaction="redact-sensitive",
            integrity="checksum",
        ),
    )
    conflict_resolution = normalize_observation_demands(conflict, target_scopes=("/links/red",))
    with pytest.raises(ValueError, match="required-prohibited-conflict"):
        execute_observation_lifecycle(
            conflict_resolution,
            producers={packets.key: lambda: called.append("called") or ()},
            supported=frozenset({packets.key}),
        )
    assert called == []


def test_backend_selection_report_uses_requested_depth_and_truthful_basis() -> None:
    selector = _selector("/nodes/kali", "os_distribution", kind="field")
    document = _document(
        ObservationDemandRule(
            rule_id="selected-distribution",
            scope="/nodes/kali",
            purpose="realization-description",
            mode="selected",
            selector=selector,
            basis=ObservationBasis.BACKEND_SELECTED,
        )
    )
    resolution = normalize_observation_demands(document, target_scopes=("/nodes/kali",))
    report = realization_description_report(
        resolution,
        {
            selector.key: AchievedObservationValue("Kali", ObservationBasis.BACKEND_SELECTED),
            _selector("/nodes/kali", "repository", kind="field").key: AchievedObservationValue(
                "private-cache", ObservationBasis.BACKEND_SELECTED
            ),
        },
    )

    assert report == ((selector.key, "Kali", ObservationBasis.BACKEND_SELECTED, None, None, False),)
    assert "private-cache" not in repr(report)


def test_reporting_never_promotes_requested_basis_to_achieved_basis() -> None:
    selector = _selector("/nodes/kali", "os_distribution", kind="field")
    resolution = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="verified-distribution",
                scope="/nodes/kali",
                purpose="realization-description",
                mode="selected",
                selector=selector,
                basis="independently-verified",
            )
        ),
        target_scopes=("/nodes/kali",),
    )

    report = realization_description_report(
        resolution,
        {selector.key: AchievedObservationValue("Kali", ObservationBasis.BACKEND_SELECTED)},
    )

    assert report == ()


def test_strong_reporting_basis_requires_trusted_evidence_bound_to_the_selected_value() -> None:
    selector = _selector("/nodes/kali", "os_distribution", kind="field")
    resolution = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="verified-distribution",
                scope="/nodes/kali",
                purpose="realization-description",
                mode="selected",
                selector=selector,
                basis="independently-verified",
                required=True,
            )
        ),
        target_scopes=("/nodes/kali",),
    )
    achieved = AchievedObservationValue(
        "Kali",
        ObservationBasis.INDEPENDENTLY_VERIFIED,
        evidence_ref="evidence:invented",
    )

    with pytest.raises(ValueError, match="required-realization-description-basis-unsatisfied"):
        realization_description_report(resolution, {selector.key: achieved})
    with pytest.raises(ValueError, match="required-realization-description-basis-unsatisfied"):
        realization_description_report(
            resolution,
            {selector.key: achieved},
            evidence_validator=lambda _key, _value: False,
        )

    report = realization_description_report(
        resolution,
        {selector.key: achieved},
        evidence_validator=lambda key, value: (
            key == selector.key and value.value == "Kali" and value.evidence_ref == "evidence:invented"
        ),
    )

    assert report == (
        (
            selector.key,
            "Kali",
            ObservationBasis.INDEPENDENTLY_VERIFIED,
            "evidence:invented",
            None,
            False,
        ),
    )


def test_runtime_rejects_strong_reporting_capability_without_trusted_evidence_verifier() -> None:
    selector = _selector("/nodes/kali", "os_distribution", kind="field")
    capability = _runtime_capability(
        selector,
        stages=frozenset(),
        bases=frozenset({ObservationBasis.INDEPENDENTLY_VERIFIED}),
    )
    describers = {
        _runtime_capability_id(selector): lambda _selector, _plan, _snapshot: AchievedObservationValue(
            "Kali",
            ObservationBasis.INDEPENDENTLY_VERIFIED,
            evidence_ref="evidence:invented",
        )
    }

    with pytest.raises(ValueError, match="trusted evidence verifier"):
        ConfiguredObservationRuntime(
            capabilities=(capability,),
            describers=describers,
        )


def test_reporting_protection_is_mandatory_and_preserves_evidence_claims() -> None:
    selector = _selector("/nodes/kali", "repository", kind="field")
    resolution = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="repository",
                scope="/nodes/kali",
                purpose="realization-description",
                mode="selected",
                selector=selector,
                basis="backend-selected",
                redaction="redact-sensitive",
                integrity="digest",
                required=True,
            )
        ),
        target_scopes=("/nodes/kali",),
    )
    achieved = AchievedObservationValue("token=secret", ObservationBasis.BACKEND_SELECTED)

    with pytest.raises(ValueError, match="protection-runtime-unavailable"):
        realization_description_report(resolution, {selector.key: achieved})

    report = realization_description_report(
        resolution,
        {selector.key: achieved},
        protector=lambda _key, value, _demand: AchievedObservationValue(
            "[REDACTED]",
            value.basis,
            value.evidence_ref,
            "sha256:protected",
        ),
    )

    assert report == ((selector.key, "[REDACTED]", ObservationBasis.BACKEND_SELECTED, None, "sha256:protected", False),)
    assert "secret" not in repr(report)


def test_inherited_axes_and_monotone_prohibition_are_resolved_independently() -> None:
    selector = _selector("/nodes/kali", "trace")
    document = _document(
        ObservationDemandRule(
            rule_id="root",
            scope="",
            purpose="experimental",
            mode="selected",
            selector=selector,
            collection="require",
            retention="disable",
            export="forbid",
            redaction="redact-sensitive",
            integrity="checksum",
        ),
        ObservationDemandRule(
            rule_id="child",
            scope="/nodes/kali",
            purpose="experimental",
            retention="require",
        ),
    )

    effective = normalize_observation_demands(document, target_scopes=("/nodes/kali",)).effective[0]
    assert effective.mode is ObservationDemandMode.SELECTED
    assert effective.collection is ObservationLifecycleDecision.REQUIRE
    assert effective.retention is ObservationLifecycleDecision.REQUIRE
    assert effective.export is ObservationLifecycleDecision.DISABLE
    assert effective.prohibited_stages == (ObservationLifecycleStage.EXPORT,)
    assert effective.origins["retention"] == "child"
    assert effective.origins["export"] == "root"


def test_explicit_inherit_keeps_parent_axis_and_independent_authorities_compose() -> None:
    parent = _selector("/nodes", "parent-trace")
    operator = _selector("/nodes/kali", "operator-audit")
    document = _document(
        ObservationDemandRule(
            rule_id="parent",
            scope="/nodes",
            purpose="experimental",
            mode="selected",
            selector=parent,
            collection="require",
            redaction="redact-sensitive",
            integrity="checksum",
            authority_ref="author",
        ),
        ObservationDemandRule(
            rule_id="child-inherit",
            scope="/nodes/kali",
            purpose="experimental",
            mode="inherit",
            retention="inherit",
            authority_ref="author",
        ),
        ObservationDemandRule(
            rule_id="operator",
            scope="/nodes/kali",
            purpose="experimental",
            selector=operator,
            collection="require",
            required=True,
            authority_ref="operator-policy",
        ),
    )

    effective = normalize_observation_demands(document, target_scopes=("/nodes/kali",)).effective

    assert len(effective) == 2
    assert {selector.names for demand in effective for selector in demand.selectors} == {parent.names, operator.names}
    assert all(selector.semantic_scope == "/nodes/kali" for demand in effective for selector in demand.selectors)
    assert [demand.required for demand in effective] == [False, True]
    assert all(demand.collection is ObservationLifecycleDecision.REQUIRE for demand in effective)
    assert all(demand.retention is ObservationLifecycleDecision.DISABLE for demand in effective)


def test_required_parent_policy_cannot_be_weakened_by_narrower_optional_none() -> None:
    selector = _selector("/nodes", "audit")
    resolution = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="mandatory-audit",
                scope="/nodes",
                purpose="experimental",
                mode="selected",
                selector=selector,
                collection="require",
                redaction="redact-sensitive",
                integrity="checksum",
                required=True,
                authority_ref="operator-policy",
            ),
            ObservationDemandRule(
                rule_id="local-disable",
                scope="/nodes/kali",
                purpose="experimental",
                mode="none",
                authority_ref="author",
            ),
        ),
        target_scopes=("/nodes/kali",),
    )

    assert resolution.is_valid
    assert resolution.effective[0].mode is ObservationDemandMode.SELECTED
    assert resolution.effective[0].selectors == (selector.model_copy(update={"semantic_scope": "/nodes/kali"}),)
    assert resolution.effective[0].collection is ObservationLifecycleDecision.REQUIRE


def test_equal_scope_independent_mandatory_authorities_conflict_explicitly() -> None:
    selector = _selector("/nodes/kali", "audit")
    resolution = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="require-audit",
                scope="/nodes/kali",
                purpose="experimental",
                mode="selected",
                selector=selector,
                collection="require",
                redaction="redact-sensitive",
                integrity="checksum",
                required=True,
                authority_ref="operator-policy",
            ),
            ObservationDemandRule(
                rule_id="forbid-audit",
                scope="/nodes/kali",
                purpose="experimental",
                mode="none",
                required=True,
                authority_ref="site-policy",
            ),
        ),
        target_scopes=("/nodes/kali",),
    )

    assert not resolution.is_valid
    assert any(diagnostic.code == "observation.authority-conflict" for diagnostic in resolution.diagnostics)


def test_compiler_rejects_invalid_observation_resolution_instead_of_carrying_a_winner() -> None:
    scenario = parse_sdl(
        """
        name: conflicting-observation-authority
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        evidence_requirements:
          required-trace:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: required-trace
              scope: /nodes/kali
              purpose: experimental
              mode: selected
              selector:
                semantic_scope: /nodes/kali
                data_kind: stream
                names: [trace]
              collection: require
              redaction: redact-sensitive
              integrity: checksum
              required: true
          required-none:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: required-none
              scope: /nodes/kali
              purpose: experimental
              mode: none
              required: true
        """
    )

    with pytest.raises(ValueError, match="observation demand normalization failed"):
        compile_scenario_runtime_model(scenario)


def test_sdl_cannot_impersonate_an_independent_observation_policy_authority() -> None:
    scenario = parse_sdl(
        """
        name: forged-observation-authority
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        evidence_requirements:
          forged:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: forged
              scope: /nodes/kali
              purpose: realization-description
              mode: selected
              selector:
                semantic_scope: /nodes/kali
                data_kind: field
                names: [os_distribution]
              basis: backend-selected
              authority_ref: operator-policy
        """
    )

    with pytest.raises(ValueError, match="cannot assert a non-author policy authority"):
        compile_scenario_runtime_model(scenario)


def test_selected_scope_requires_privacy_and_integrity_policy() -> None:
    selector = _selector("/links/red", "packets")
    with pytest.raises(ValueError, match="selected experimental demand requires redaction and integrity policy"):
        ObservationDemandRule(
            rule_id="unsafe",
            scope="/links/red",
            purpose="experimental",
            mode="selected",
            selector=selector,
            collection="require",
        )


def test_scope_profile_is_closed_and_versioned() -> None:
    with pytest.raises(ValueError, match="recursive-realization-constraint/v1"):
        ObservationDemandDocument(
            schema_version="observation-demand/v1",
            document_id="unknown-scope-profile",
            scope_profile="positional-json-pointer/v1",
        )


@pytest.mark.parametrize(
    ("scope", "component_ref", "message"),
    [
        ("/nodes/missing", "nodes.kali", "does not resolve to a stable SDL semantic scope"),
        ("/nodes/kali/runtime/packages/9", "nodes.kali", "does not resolve to a stable SDL semantic scope"),
        ("/nodes/kali", "nodes.missing", "component_ref 'nodes.missing'"),
    ],
)
def test_authored_observation_scopes_and_component_refs_must_resolve(
    scope: str,
    component_ref: str,
    message: str,
) -> None:
    with pytest.raises(SDLValidationError, match=message):
        parse_sdl(
            f"""
            name: invalid-observation-address
            nodes:
              kali:
                type: compute
                resources: {{ram: 1 gib, cpu: 1}}
                runtime:
                  packages:
                    - {{manager: apt, name: bash, version: '5.2'}}
            evidence_requirements:
              distribution:
                source_class: processor_backend
                scope_refs: [nodes.kali]
                window: run
                channel: api_response
                sensitivity: plain
                redaction: redact_sensitive
                integrity: checksum
                retention: not_retained
                loss_disclosure: required
                observation_demand:
                  rule_id: distribution
                  scope: {scope}
                  purpose: realization-description
                  mode: selected
                  selector:
                    semantic_scope: {scope}
                    component_refs: [{component_ref}]
                    data_kind: field
                    names: [os_distribution]
                  basis: backend-selected
            """
        )


def test_authored_scope_resolves_stable_keyed_sequence_members() -> None:
    scenario = parse_sdl(
        """
        name: stable-observation-address
        nodes:
          kali:
            type: compute
            resources: {ram: 1 gib, cpu: 1}
            runtime:
              packages:
                - {manager: apt, name: bash, version: '5.2'}
        evidence_requirements:
          package-version:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: package-version
              scope: /nodes/kali/runtime/packages/0
              purpose: realization-description
              mode: selected
              selector:
                semantic_scope: /nodes/kali/runtime/packages/0
                component_refs: [nodes.kali]
                data_kind: field
                names: [version]
              basis: backend-selected
        """
    )

    demand = next(
        item
        for item in compile_scenario_runtime_model(scenario).observation_demands
        if item.purpose is ObservationPurpose.REALIZATION_DESCRIPTION
    )
    scope = demand.scope
    assert "/packages/@" in scope
    assert "/packages/0" not in scope
    assert demand.selectors[0].component_refs == ("provision.node.kali",)


def test_shared_contract_is_carried_by_sdl_task_capture_and_run_policy_owners() -> None:
    selector = _selector("/nodes/kali", "os_distribution", kind="field")
    rule = ObservationDemandRule(
        rule_id="distribution",
        scope="/nodes/kali",
        purpose="realization-description",
        mode="selected",
        selector=selector,
        basis="backend-selected",
    )
    document = _document(rule)
    authored = EvidenceRequirement(
        source_class="processor_backend",
        scope_refs=["nodes.kali"],
        window="run",
        channel="api_response",
        sensitivity="plain",
        redaction="redact_sensitive",
        integrity="checksum",
        retention="not_retained",
        loss_disclosure="required",
        observation_demand=rule,
    )
    assert authored.observation_demand == rule

    task_payload = _fixture("contracts/fixtures/experiment-core/experiment-task-v1/valid/reference.json")
    task_payload["observation_demands"] = document.model_dump(mode="json")
    assert ExperimentTaskModel.model_validate(task_payload).observation_demands == document

    capture_payload = _fixture("contracts/fixtures/experiment-core/experiment-capture-spec-v1/valid/reference.json")
    first_capture = next(iter(capture_payload["capture_requirements"].values()))
    first_capture["observation_demand"] = rule.model_dump(mode="json")
    assert (
        next(
            iter(ExperimentCaptureSpecModel.model_validate(capture_payload).capture_requirements.values())
        ).observation_demand
        == rule
    )

    spec_payload = _fixture("contracts/fixtures/experiment-core/experiment-authoring-input-v1/valid/reference.json")
    spec_payload["run_plan"]["observation_demands"] = document.model_dump(mode="json")
    assert ExperimentSpecModel.model_validate(spec_payload).run_plan.observation_demands == document


def test_effective_demand_survives_published_plan_round_trip_and_changes_digest() -> None:
    selector = _selector("/nodes/kali", "filesystem-trace")
    document = _document(
        ObservationDemandRule(
            rule_id="filesystem",
            scope="/nodes/kali",
            purpose="experimental",
            mode="selected",
            selector=selector,
            collection="require",
            redaction="redact-sensitive",
            integrity="checksum",
        )
    )
    effective = normalize_observation_demands(document, target_scopes=("/nodes/kali",)).effective
    baseline = ProvisioningPlan()
    demanded = ProvisioningPlan(observation_demands=effective)
    published = provisioning_plan_model(demanded)
    restored = _provisioning_plan(published)

    assert restored.observation_demands == effective
    assert provisioning_plan_digest(demanded) != provisioning_plan_digest(baseline)


def test_sdl_demand_is_normalized_once_carried_to_plans_and_owned_by_one_phase() -> None:
    scenario = parse_sdl(
        """
        name: observation-demand-plan
        nodes:
          kali:
            type: compute
            source: kali-linux
            resources: {ram: 1 gib, cpu: 1}
        evidence_requirements:
          selected-distribution:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: selected-distribution
              scope: /nodes/kali
              purpose: realization-description
              mode: selected
              selector:
                semantic_scope: /nodes/kali
                data_kind: field
                names: [os_distribution]
              basis: backend-selected
        """
    )
    runtime_model = compile_scenario_runtime_model(scenario)
    execution = plan(runtime_model, create_stub_manifest())

    assert runtime_model.observation_demands
    assert execution.provisioning.observation_demands == runtime_model.observation_demands
    assert execution.orchestration.observation_demands == runtime_model.observation_demands
    assert execution.evaluation.observation_demands == runtime_model.observation_demands
    assert execution.observation_owner is RuntimeDomain.PROVISIONING


def test_composite_runtime_executes_observation_once_at_the_last_actionable_phase() -> None:
    observed: list[tuple[str, str]] = []
    runtime = ConfiguredObservationRuntime(
        capabilities=(
            ObservationRuntimeCapability(
                capability_id="node-filesystem-trace",
                selector_pattern=ObservationSelectorPattern(
                    data_kind="stream",
                    names=frozenset({"filesystem-trace"}),
                    semantic_scope_prefix="/nodes",
                ),
                capture_kind="trace",
                channel_kind="runtime-snapshot",
                stages=frozenset({ObservationLifecycleStage.COLLECTION}),
            ),
        ),
        producers={
            "node-filesystem-trace": lambda selector, plan, _snapshot: (
                observed.append((selector.semantic_scope, type(plan).__name__)) or ("event",)
            )
        },
    )
    target = _runtime_target(create_stub_target(), runtime)
    scenario = parse_sdl(
        """
        name: multi-phase-observation-owner
        nodes:
          vm:
            type: compute
            resources: {ram: 1 gib, cpu: 1}
            conditions: {health: ops}
            roles: {ops: operator}
        conditions:
          health: {command: /bin/true, interval: 15}
        propositions:
          health:
            description: The governed VM has declared runtime state.
            subjects: [nodes.vm]
            basis: declared_state
            predicate:
              kind: presence
              property: runtime
              semantic_ref: urn:raes:declared-property:runtime
              operator: exists
        assertions:
          pre-health: {proposition: health, role: precondition, polarity: positive}
        events:
          kickoff: {assertions: [pre-health]}
        scripts:
          timeline: {start_time: 0, end_time: 60, speed: 1, events: {kickoff: 10}}
        stories:
          main: {scripts: [timeline]}
        evidence_requirements:
          filesystem:
            source_class: processor_backend
            scope_refs: [nodes.vm]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: filesystem
              scope: /nodes/vm
              purpose: experimental
              mode: selected
              selector:
                semantic_scope: /nodes/vm
                data_kind: stream
                names: [filesystem-trace]
              collection: require
              redaction: none
              integrity: none
              required: false
        """
    )
    manager = RuntimeManager(target)
    execution = manager.plan(scenario)

    assert execution.observation_owner is RuntimeDomain.ORCHESTRATION
    result = manager.apply(execution)

    assert result.success
    assert observed == [("/nodes/vm", "OrchestrationPlan")]


def test_authored_demand_executes_protected_collection_and_retention_in_control_plane() -> None:
    scenario = parse_sdl(
        """
        name: runtime-observation-demand
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        evidence_requirements:
          filesystem:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: run_lifetime
            loss_disclosure: required
            observation_demand:
              rule_id: filesystem
              scope: /nodes/kali
              purpose: experimental
              mode: selected
              selector:
                semantic_scope: /nodes/kali
                data_kind: stream
                names: [filesystem-trace]
              collection: require
              retention: require
              export: disable
              redaction: redact-sensitive
              integrity: digest
              required: false
        """
    )
    selector = _selector("/nodes/kali", "filesystem-trace")
    calls: list[str] = []
    describe_calls: list[str] = []
    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector,
                stages=frozenset(
                    {
                        ObservationLifecycleStage.COLLECTION,
                        ObservationLifecycleStage.RETENTION,
                        ObservationLifecycleStage.EXPORT,
                    }
                ),
                bases=frozenset({ObservationBasis.BACKEND_SELECTED}),
                redaction_policies=frozenset({"redact-sensitive"}),
                integrity_policies=frozenset({"digest"}),
            ),
        ),
        producers={
            _runtime_capability_id(selector): lambda _selector, _plan, _snapshot: (
                calls.append("collect") or ("token=secret",)
            )
        },
        describers={
            _runtime_capability_id(selector): lambda _selector, _plan, _snapshot: (
                describe_calls.append("describe")
                or AchievedObservationValue("unexpected", ObservationBasis.BACKEND_SELECTED)
            )
        },
        redactors={
            "redact-sensitive": lambda values: tuple(
                "[REDACTED]" if "secret" in str(value) else value for value in values
            )
        },
        integrity_providers={"digest": lambda _key, _values: "sha256:protected"},
    )
    target = _runtime_target(create_stub_target(), runtime)
    execution_plan = RuntimeManager(target).plan(scenario)
    provisioning = execution_plan.provisioning
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(target, store=store)
    control_plane.register_planner_produced_plan(execution_plan)

    receipt = control_plane.submit_provisioning(provisioning)
    execution = control_plane.observation_execution(receipt.operation_id)

    assert control_plane.get_operation(receipt.operation_id).state.value == "succeeded"
    assert calls == ["collect"]
    assert describe_calls == []
    result_payload = store.load_records()[receipt.operation_id].result_payload
    assert result_payload is not None
    assert result_payload["operation_id"] == receipt.operation_id
    assert result_payload["retained"][0]["values"] == ["[REDACTED]"]
    assert "export_outbox" not in result_payload
    assert execution is not None
    assert execution.lifecycle.collected[0].selector_key == selector.key
    assert execution.lifecycle.collected[0].values == ()
    assert execution.lifecycle.collected[0].integrity_ref == "sha256:protected"
    assert "secret" not in repr(execution.lifecycle)
    recovered = RuntimeControlPlane(target, store=store)
    recovered_execution = recovered.observation_execution(receipt.operation_id)
    assert recovered_execution is not None
    assert recovered_execution.lifecycle == execution.lifecycle


def test_required_observation_rejects_mutation_and_read_only_failure_is_terminal() -> None:
    scenario = parse_sdl(
        """
        name: runtime-observation-failure
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        evidence_requirements:
          filesystem:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: filesystem
              scope: /nodes/kali
              purpose: experimental
              mode: selected
              selector:
                semantic_scope: /nodes/kali
                data_kind: stream
                names: [filesystem-trace]
              collection: require
              redaction: redact-sensitive
              integrity: digest
              required: true
        """
    )
    selector = _selector("/nodes/kali", "filesystem-trace")

    collection_calls: list[str] = []

    def fail_collection(_selector: object, _plan: object, _snapshot: object) -> tuple[object, ...]:
        collection_calls.append("collect")
        raise RuntimeError("adapter failed")

    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector,
                stages=frozenset({ObservationLifecycleStage.COLLECTION}),
                redaction_policies=frozenset({"redact-sensitive"}),
                integrity_policies=frozenset({"digest"}),
            ),
        ),
        producers={_runtime_capability_id(selector): fail_collection},
        redactors={"redact-sensitive": lambda values: values},
        integrity_providers={"digest": lambda _key, _values: "sha256:unused"},
    )
    target = _runtime_target(create_stub_target(), runtime)
    control_plane = RuntimeControlPlane(target)

    provisioning = RuntimeManager(target).plan(scenario).provisioning
    receipt = control_plane.submit_provisioning(provisioning)
    assert not receipt.accepted
    assert receipt.diagnostics[0].code == "observation.required-execution-atomicity-unavailable"
    assert collection_calls == []
    assert control_plane.snapshot.entries == {}
    receipt = control_plane.submit_provisioning(ProvisioningPlan(observation_demands=provisioning.observation_demands))
    status = control_plane.get_operation(receipt.operation_id)

    assert receipt.accepted
    assert status is not None
    assert status.state.value == "failed"
    assert any(diagnostic.code == "observation.runtime-adapter-failed" for diagnostic in status.diagnostics)
    assert control_plane.snapshot.entries == {}
    assert status.changed_addresses == []
    assert collection_calls == ["collect"]


def test_runtime_manager_uses_the_same_observation_apply_boundary() -> None:
    scenario = parse_sdl(
        """
        name: manager-observation-demand
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        evidence_requirements:
          distribution:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: distribution
              scope: /nodes/kali
              purpose: realization-description
              mode: selected
              selector:
                semantic_scope: /nodes/kali
                data_kind: field
                names: [os_distribution]
              basis: backend-selected
              required: false
        """
    )
    selector = _selector("/nodes/kali", "os_distribution", kind="field")
    describe_calls: list[str] = []
    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector,
                stages=frozenset(),
                bases=frozenset({ObservationBasis.BACKEND_SELECTED}),
            ),
        ),
        describers={
            _runtime_capability_id(selector): lambda _selector, _plan, _snapshot: (
                describe_calls.append("describe") or AchievedObservationValue("Kali", ObservationBasis.BACKEND_SELECTED)
            )
        },
    )
    target = _runtime_target(create_stub_target(), runtime)
    manager = RuntimeManager(target)

    result = manager.apply(manager.plan(scenario))

    assert result.success
    assert describe_calls == ["describe"]


def test_control_plane_persists_no_placeholder_for_an_unsupported_optional_selector() -> None:
    selector = _selector("/nodes/kali", "filesystem-trace")
    demands = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="optional-retention",
                scope="/nodes/kali",
                purpose="experimental",
                mode="selected",
                selector=selector,
                collection="require",
                retention="require",
                redaction="redact-sensitive",
                integrity="digest",
            )
        ),
        target_scopes=("/nodes/kali",),
    ).effective
    target = create_stub_target()
    manager = RuntimeManager(target)
    scenario = parse_sdl(
        """
        name: optional-manager-observation
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )
    execution = manager.plan(scenario)
    execution = replace(
        execution,
        provisioning=replace(execution.provisioning, observation_demands=demands),
    )

    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(target, store=store)
    control_plane.register_planner_produced_plan(execution)
    receipt = control_plane.submit_provisioning(execution.provisioning)
    result = control_plane.observation_execution(receipt.operation_id)

    assert control_plane.get_operation(receipt.operation_id).state.value == "succeeded"
    assert result is not None
    assert result.lifecycle.collected == ()
    assert result.lifecycle.retained == ()
    payload = store.load_records()[receipt.operation_id].result_payload
    assert payload is not None
    assert payload["lifecycle"]["collected"] == []
    assert payload["lifecycle"]["retained"] == []
    assert payload["retained"] == []


def test_direct_manager_rejects_executable_persistence_without_a_durable_owner() -> None:
    selector = _selector("/nodes/kali", "filesystem-trace")
    demands = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="retention",
                scope="/nodes/kali",
                purpose="experimental",
                mode="selected",
                selector=selector,
                collection="require",
                retention="require",
                redaction="redact-sensitive",
                integrity="digest",
            )
        ),
        target_scopes=("/nodes/kali",),
    ).effective
    collect_calls: list[str] = []
    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector,
                stages=frozenset(
                    {
                        ObservationLifecycleStage.COLLECTION,
                        ObservationLifecycleStage.RETENTION,
                    }
                ),
                redaction_policies=frozenset({"redact-sensitive"}),
                integrity_policies=frozenset({"digest"}),
            ),
        ),
        producers={
            _runtime_capability_id(selector): lambda _selector, _plan, _snapshot: (
                collect_calls.append("collect") or ("value",)
            )
        },
        redactors={"redact-sensitive": lambda values: values},
        integrity_providers={"digest": lambda _key, _values: "sha256:unused"},
    )
    manager = RuntimeManager(_runtime_target(create_stub_target(), runtime))
    scenario = parse_sdl(
        """
        name: non-atomic-manager-observation
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )
    execution = manager.plan(scenario)
    execution = replace(
        execution,
        provisioning=replace(execution.provisioning, observation_demands=demands),
    )

    result = manager.apply(execution)

    assert not result.success
    assert result.diagnostics[0].code == "observation.durable-lifecycle-owner-unavailable"
    assert collect_calls == []


def test_authored_realization_description_reports_only_achieved_basis() -> None:
    scenario = parse_sdl(
        """
        name: runtime-realization-description
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        evidence_requirements:
          distribution:
            source_class: processor_backend
            scope_refs: [nodes.kali]
            window: run
            channel: api_response
            sensitivity: plain
            redaction: redact_sensitive
            integrity: checksum
            retention: not_retained
            loss_disclosure: required
            observation_demand:
              rule_id: distribution
              scope: /nodes/kali
              purpose: realization-description
              mode: selected
              selector:
                semantic_scope: /nodes/kali
                data_kind: field
                names: [os_distribution]
              basis: backend-selected
              required: false
        """
    )
    selector = _selector("/nodes/kali", "os_distribution", kind="field")
    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector,
                stages=frozenset(),
                bases=frozenset({ObservationBasis.BACKEND_SELECTED}),
            ),
        ),
        describers={
            _runtime_capability_id(selector): lambda _selector, _plan, _snapshot: AchievedObservationValue(
                "Kali", ObservationBasis.BACKEND_SELECTED
            )
        },
    )
    target = _runtime_target(create_stub_target(), runtime)
    manager = RuntimeManager(target)
    manager_result = manager.apply(manager.plan(scenario))
    assert manager_result.success
    assert manager_result.details["realized_form_disclosures"][0]["realized_value_summary"] == '"Kali"'
    control_plane = RuntimeControlPlane(target)
    execution_plan = RuntimeManager(target).plan(scenario)
    control_plane.register_planner_produced_plan(execution_plan)

    receipt = control_plane.submit_provisioning(execution_plan.provisioning)
    execution = control_plane.observation_execution(receipt.operation_id)

    assert control_plane.get_operation(receipt.operation_id).state.value == "succeeded"
    assert execution is not None
    assert execution.realized_form_disclosures == ()
    disclosure = manager_result.details["realized_form_disclosures"][0]
    assert disclosure["concern_id"] == selector.key
    assert disclosure["basis"] == "backend-realized"


def test_realization_detail_creates_no_experimental_demand_but_keeps_operational_verification() -> None:
    scenario = parse_sdl(
        """
        name: exact-without-telemetry
        nodes:
          kali:
            type: compute
            os: linux
            os_distribution: ubuntu
            os_version: "24.04"
            source: exact-image
            resources: {ram: 1 gib, cpu: 1}
            runtime:
              environment:
                - name: APP_MODE
                  value: exact
                  provenance: operator
                  source: scenario
        """
    )
    model = compile_scenario_runtime_model(scenario)

    assert model.observation_demands == ()
    environment = next(
        requirement
        for requirement in model.realization_requirements
        if requirement.requirement_kind == "runtime-environment"
    )
    assert environment.verification_scope is not None
    assert environment.required_observation_strength is not None


def test_backend_does_not_persist_unrequested_realization_observations() -> None:
    scenario = parse_sdl(
        """
        name: exact-backend-without-telemetry
        realization:
          constraints:
            - field_pointer: /nodes/kali
              concern: compute-substrate
              posture: exact
              domain: {kind: exact, value: "x-openrae:in-process-emulation"}
        nodes:
          kali:
            type: compute
            source: exact-image
            resources: {ram: 1 gib, cpu: 1}
        """
    )
    selector = _selector("/nodes/kali", "filesystem-trace")
    calls: list[str] = []
    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector,
                stages=frozenset({ObservationLifecycleStage.COLLECTION}),
            ),
        ),
        producers={
            _runtime_capability_id(selector): lambda _selector, _plan, _snapshot: calls.append("collect") or ("event",)
        },
    )
    target = _runtime_target(create_stub_target(), runtime)
    model = compile_scenario_runtime_model(scenario)
    substrate_requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "compute-substrate"
    )
    assert substrate_requirement.verification_scope is None
    assert substrate_requirement.required_observation_strength is None
    execution_plan = plan(model, target.manifest)
    provisioning = execution_plan.provisioning
    assert (
        compute_substrate_readback_addresses(
            plan=provisioning,
            envelope=target.manifest.realization_envelope,
            previous=(),
        )
        == ()
    )
    control_plane = RuntimeControlPlane(target)
    control_plane.register_planner_produced_plan(execution_plan)

    receipt = control_plane.submit_provisioning(provisioning)

    assert control_plane.get_operation(receipt.operation_id).state.value == "succeeded"
    assert calls == []
    assert control_plane.snapshot.realization_observations == ()


def test_native_realization_readback_is_not_reused_as_unprotected_retention() -> None:
    scenario = parse_sdl(
        """
        name: exact-backend-selected-telemetry
        realization:
          constraints:
            - field_pointer: /nodes/kali
              concern: compute-substrate
              posture: exact
              domain: {kind: exact, value: "x-openrae:in-process-emulation"}
        nodes:
          kali:
            type: compute
            source: exact-image
            resources: {ram: 1 gib, cpu: 1}
        """
    )
    selector = _selector("/nodes/kali", "compute-substrate", kind="field")
    demands = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="substrate",
                scope="/nodes/kali",
                purpose="experimental",
                mode="selected",
                selector=selector,
                collection="require",
                retention="require",
                redaction="redact-sensitive",
                integrity="checksum",
            )
        ),
        target_scopes=("/nodes/kali",),
    ).effective
    target = create_stub_target()
    execution_plan = RuntimeManager(target).plan(scenario)
    provisioning = execution_plan.provisioning
    provisioning = replace(provisioning, observation_demands=demands)
    control_plane = RuntimeControlPlane(target)
    control_plane.register_planner_produced_plan(replace(execution_plan, provisioning=provisioning))

    receipt = control_plane.submit_provisioning(provisioning)

    assert control_plane.get_operation(receipt.operation_id).state.value == "succeeded"
    assert control_plane.snapshot.realization_observations == ()


def test_direct_submission_rejects_unsupported_required_selector_before_backend_apply() -> None:
    selector = _selector("/nodes/kali", "filesystem-trace")
    demands = normalize_observation_demands(
        _document(
            ObservationDemandRule(
                rule_id="required-trace",
                scope="/nodes/kali",
                purpose="experimental",
                mode="selected",
                selector=selector,
                collection="require",
                required=True,
                redaction="redact-sensitive",
                integrity="checksum",
            )
        ),
        target_scopes=("/nodes/kali",),
    ).effective
    base_target = create_stub_target()
    apply_calls: list[str] = []

    class _SpyProvisioner:
        def validate(self, provisioning):
            return base_target.provisioner.validate(provisioning)

        def apply(self, provisioning, snapshot):
            apply_calls.append("apply")
            return base_target.provisioner.apply(provisioning, snapshot)

    incompatible = _selector("/nodes/kali", "packet-trace")
    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                incompatible,
                stages=frozenset({ObservationLifecycleStage.COLLECTION}),
            ),
        ),
        producers={_runtime_capability_id(incompatible): lambda _selector, _plan, _snapshot: ()},
    )
    target = RuntimeTarget(
        name="incompatible-observation-capability",
        manifest=base_target.manifest,
        provisioner=_SpyProvisioner(),
        orchestrator=base_target.orchestrator,
        evaluator=base_target.evaluator,
        participant_runtime=base_target.participant_runtime,
        time_runtime=base_target.time_runtime,
        observation_runtime=runtime,
    )
    scenario = parse_sdl(
        """
        name: direct-required-observation
        nodes:
          kali: {type: compute, resources: {ram: 1 gib, cpu: 1}}
        """
    )
    provisioning = replace(RuntimeManager(base_target).plan(scenario).provisioning, observation_demands=demands)
    control_plane = RuntimeControlPlane(target)

    receipt = control_plane.submit_provisioning(provisioning)

    assert not receipt.accepted
    assert receipt.diagnostics[0].code == "observation.unsupported-required-selector"
    assert control_plane.get_operation(receipt.operation_id) is None
    assert apply_calls == []


def test_more_specific_effective_policy_blocks_broad_selector_side_effects() -> None:
    broad_selector = _selector("/nodes", "filesystem-trace")
    broad = EffectiveObservationDemand(
        scope="/nodes",
        purpose="experimental",
        mode="selected",
        selectors=(broad_selector,),
        collection="require",
        retention="require",
        export="require",
        basis="observed",
        redaction="none",
        integrity="none",
    )
    child = EffectiveObservationDemand(
        scope="/nodes/sensitive",
        purpose="experimental",
        mode="none",
        collection="disable",
        retention="disable",
        export="disable",
        basis="observed",
    )
    calls: list[str] = []

    result = execute_observation_lifecycle(
        ObservationDemandResolution((broad, child)),
        producers={broad_selector.key: lambda: calls.append("collect") or ("secret",)},
        supported=frozenset({broad_selector.key}),
    )

    assert calls == []
    assert result.collected == result.retained == result.exported == ()


def test_more_specific_effective_policy_blocks_broad_describer_side_effects() -> None:
    selector = _selector("/nodes", "os_distribution", kind="field")
    broad = EffectiveObservationDemand(
        scope="/nodes",
        purpose="realization-description",
        mode="selected",
        selectors=(selector,),
        collection="disable",
        retention="disable",
        export="disable",
        basis="backend-selected",
    )
    child = EffectiveObservationDemand(
        scope="/nodes/sensitive",
        purpose="realization-description",
        mode="none",
        collection="disable",
        retention="disable",
        export="disable",
        basis="backend-selected",
    )
    describe_calls: list[str] = []
    runtime = ConfiguredObservationRuntime(
        capabilities=(
            _runtime_capability(
                selector,
                stages=frozenset(),
                bases=frozenset({ObservationBasis.BACKEND_SELECTED}),
            ),
        ),
        describers={
            _runtime_capability_id(selector): lambda _selector, _plan, _snapshot: (
                describe_calls.append("describe")
                or AchievedObservationValue("secret", ObservationBasis.BACKEND_SELECTED)
            )
        },
    )
    target = _runtime_target(create_stub_target(), runtime)
    control_plane = RuntimeControlPlane(target)

    receipt = control_plane.submit_provisioning(
        ProvisioningPlan(observation_demands=(broad, child)),
    )

    assert control_plane.get_operation(receipt.operation_id).state.value == "succeeded"
    assert describe_calls == []
    assert control_plane.observation_execution(receipt.operation_id).realized_form_disclosures == ()


def test_planner_authorization_digest_is_domain_separated_and_registers_all_phases() -> None:
    authorization_plan = plan(
        compile_scenario_runtime_model(parse_sdl("name: domain-separated-authorization")),
        create_stub_manifest(),
    )
    orchestration = authorization_plan.orchestration
    evaluation = authorization_plan.evaluation

    assert runtime_plan_digest(orchestration) != runtime_plan_digest(evaluation)
    control_plane = RuntimeControlPlane(create_stub_target())
    control_plane.register_planner_produced_plan(authorization_plan)
    assert control_plane.is_planner_authorized_plan(orchestration)
    assert control_plane.is_planner_authorized_plan(evaluation)


def test_observation_demand_is_in_the_published_schema_bundle() -> None:
    schema = schema_bundle()["observation-demand-v1"]
    assert schema["properties"]["contract_id"]["const"] == "observation-demand-v1"
    assert schema["properties"]["schema_version"]["const"] == "observation-demand/v1"
    published = _fixture("contracts/schemas/control-plane/observation-demand-v1.json")
    assert schema == published
    valid = _fixture("contracts/fixtures/control-plane/observation-demand-v1/valid/mixed-scopes.json")
    invalid = _fixture("contracts/fixtures/control-plane/observation-demand-v1/invalid/unbounded-exhaustive.json")
    policy_empty = _fixture("contracts/fixtures/control-plane/observation-demand-v1/invalid/policy-empty-rule.json")
    validator = Draft202012Validator(published)
    assert not list(validator.iter_errors(valid))
    assert list(validator.iter_errors(invalid))
    assert list(validator.iter_errors(policy_empty))
    assert ObservationDemandDocument.model_validate(valid)
    with pytest.raises(ValueError, match="at least one policy axis"):
        ObservationDemandDocument.model_validate(policy_empty)


@pytest.mark.parametrize("missing", ["coverage_profile", "max_items"])
def test_published_selector_schema_enforces_coverage_pair(missing: str) -> None:
    payload = _fixture("contracts/fixtures/control-plane/observation-demand-v1/valid/mixed-scopes.json")
    selector = payload["rules"][0]["selector"]
    selector.update({"coverage_profile": "bounded-packets/v1", "max_items": 64})
    selector.pop(missing)

    schema = schema_bundle()["observation-demand-v1"]
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValueError, match="coverage_profile and max_items"):
        ObservationDemandDocument.model_validate(payload)
