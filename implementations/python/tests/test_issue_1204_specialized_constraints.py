"""Specialized safe concern projections retain recursive leaf authority."""

from copy import deepcopy

import pytest
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_processor.semantics.realization_concerns import project_realization_concern
from test_issue_1200_mixed_runtime_constraints import _fixture


@pytest.mark.parametrize(
    "kind,runtime,path,field,value",
    [
        (
            "runtime-mounts",
            {
                "mounts": [
                    {
                        "target": "/data",
                        "source": "/srv/data",
                        "source_kind": "bind",
                        "source_sensitivity": "plain",
                        "options_sensitivity": "plain",
                    }
                ]
            },
            ("mounts", 0),
            "source",
            "/srv/other",
        ),
        (
            "linux-capabilities",
            {"linux_capabilities": {"required": ["CAP_NET_RAW"]}},
            ("linux_capabilities",),
            "required",
            ["CAP_SYS_ADMIN"],
        ),
        (
            "published-ports",
            {"network": {"published_ports": [{"host_port": 8080, "container_port": 80, "protocol": "tcp"}]}},
            ("network", "published_ports", 0),
            "container_port",
            81,
        ),
        (
            "forwarding-agents",
            {"forwarding_agents": [{"forwarding_agent_id": "agent", "agent_kind": "other", "implementation": "other"}]},
            ("forwarding_agents", 0),
            "forwarding_agent_id",
            "replacement",
        ),
        (
            "service-listeners",
            {
                "service_listeners": [
                    {
                        "service_listener_id": "listener",
                        "address": "127.0.0.1",
                        "port": 8080,
                        "protocol": "tcp",
                        "address_family": "ipv4",
                        "scope": "loopback_only",
                    }
                ]
            },
            ("service_listeners", 0),
            "port",
            8081,
        ),
    ],
)
def test_specialized_projection_keeps_exact_siblings_under_open_collection(kind, runtime, path, field, value):
    scope_parts = tuple(item for item in path if isinstance(item, str))
    scope = "/nodes/host/runtime/" + "/".join(scope_parts)
    model, portable, manifest = _fixture(runtime, scope=scope)
    requirement = next(item for item in model.realization_requirements if item.requirement_kind == kind)
    authority = next(item for item in portable.realization_authority if item.requirement_kind == kind)
    assert authority.constraint_document is not None
    assert authority.constraint_document == requirement.constraint_document
    after = deepcopy(runtime)
    cursor = after
    for key in path:
        cursor = cursor[key]
    cursor[field] = value
    original, changed = runtime, after
    for key in scope_parts:
        original, changed = original[key], changed[key]
    # A delegated taxonomy's author template is not itself a known completion.
    if kind != "forwarding-agents":
        assert evaluate_realization_constraint(
            authority.constraint_document, project_realization_concern(kind, original, recursive=True)
        ).conformant
    assert not evaluate_realization_constraint(
        authority.constraint_document, project_realization_concern(kind, changed, recursive=True)
    ).conformant
    if kind != "forwarding-agents":
        admitted = _apply_with_observations(portable, manifest, runtime)
        assert admitted.success, admitted.diagnostics
        rejected = _apply_with_observations(portable, manifest, after)
        assert not rejected.success
        assert rejected.snapshot.entries == {}


def _apply_with_observations(plan, manifest, runtime):
    from dataclasses import replace

    from raes_contracts.runtime_state import ApplyResult, RealizationObservationDisclosure, RuntimeSnapshot
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
    from test_issue_1200_mixed_runtime_constraints import _returned

    returned = _returned(plan, runtime)
    returned = replace(
        returned,
        realization_observations=tuple(
            RealizationObservationDisclosure(
                address=a.address,
                field_path=a.field_path,
                domain=a.domain,
                requirement_kind=a.requirement_kind,
                verification_scope=a.verification_scope,
                observation_strength=a.required_observation_strength,
            )
            for a in plan.realization_authority
            if a.verification_scope is not None and a.required_observation_strength is not None
        ),
    )
    previous = RuntimeSnapshot()
    return _call_backend_apply(
        lambda *_: ApplyResult(True, returned, changed_addresses=list(returned.entries)),
        plan,
        previous,
        address="runtime.specialized",
        snapshot=previous,
        realization=_RealizationApplyContext(plan=plan, manifest=manifest),
    )


def test_process_limit_domain_uses_recursive_identity_bound_authority():
    from raes import instantiate_scenario, parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan
    from test_issue_1066_runtime_resource_limits import _scenario, _supporting_manifest

    scenario = instantiate_scenario(
        parse_sdl(
            _scenario(
                """
    - resource: open_file_descriptors
      soft: '${limit}'
      hard: 65536
      subject: {name: search, role: primary}
      scope: subtree
    """,
                variables="""
    variables:
      limit:
        type: integer
        default: 16384
        allowed_values: [16384, 32768]
    """,
            )
        )
    )
    execution = plan(compile_runtime_model(scenario), _supporting_manifest())
    assert execution.is_valid, execution.diagnostics
    authority = next(
        item
        for item in execution.provisioning.realization_authority
        if item.requirement_kind == "process-resource-limits"
    )
    assert authority.constraint_document is not None
    for soft, accepted in [(16384, True), (32768, True), (65536, False)]:
        value = [
            {
                "resource": "open_file_descriptors",
                "soft": soft,
                "hard": 65536,
                "subject": {"name": "search", "role": "primary"},
                "scope": "subtree",
            }
        ]
        assert (
            evaluate_realization_constraint(
                authority.constraint_document,
                project_realization_concern("process-resource-limits", value, recursive=True),
            ).conformant
            is accepted
        )


@pytest.mark.parametrize("opened", [False, True])
def test_capability_set_membership_is_not_retargeted_by_canonical_sorting(opened):
    runtime = {"linux_capabilities": {"required": ["CAP_NET_RAW"]}}
    _, portable, manifest = _fixture(runtime, scope="/nodes/host/runtime/linux_capabilities" if opened else None)
    expanded = {"linux_capabilities": {"required": ["CAP_NET_BIND_SERVICE", "CAP_NET_RAW"]}}
    result = _apply_with_observations(portable, manifest, expanded)
    assert result.success is opened, result.diagnostics
    assert _apply_with_observations(portable, manifest, runtime).success


def test_minimal_process_capability_override_survives_safe_projection():
    runtime = {
        "linux_capabilities": {"process_overrides": [{"subject": {"name": "worker"}, "effective": ["CAP_NET_RAW"]}]}
    }
    _, portable, manifest = _fixture(runtime)
    result = _apply_with_observations(portable, manifest, runtime)
    assert result.success, result.diagnostics


def test_scalar_capability_domain_changes_a_member_without_changing_its_exact_peer():
    from raes import instantiate_scenario, parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan

    source = """
name: finite-capability-set
realization: {default: closed}
variables:
  capability:
    type: string
    default: CAP_NET_RAW
    allowed_values: [CAP_NET_RAW, CAP_NET_BIND_SERVICE]
nodes:
  host:
    type: compute
    runtime:
      linux_capabilities:
        required: ['${capability}', CAP_SYS_CHROOT]
"""
    _, _, manifest = _fixture({"linux_capabilities": {"required": ["CAP_NET_RAW"]}})
    execution = plan(compile_runtime_model(instantiate_scenario(parse_sdl(source))), manifest)
    assert execution.is_valid, execution.diagnostics
    for members, accepted in [
        (["CAP_SYS_CHROOT", "CAP_NET_BIND_SERVICE"], True),
        (["CAP_SYS_CHROOT", "CAP_SYS_ADMIN"], False),
        (["CAP_NET_RAW"], False),
    ]:
        result = _apply_with_observations(
            execution.provisioning, manifest, {"linux_capabilities": {"required": members}}
        )
        assert result.success is accepted, result.diagnostics


@pytest.mark.parametrize(
    "selected,peer_port,accepted", [(8080, 443, True), (8081, 443, True), (8082, 443, False), (8081, 444, False)]
)
def test_finite_endpoint_identity_preserves_exact_peer(selected, peer_port, accepted):
    from raes import instantiate_scenario, parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan

    source = """
name: finite-endpoint
variables:
  port:
    type: integer
    default: 8080
    allowed_values: [8080, 8081]
nodes:
  host:
    type: compute
    runtime:
      network:
        published_ports:
          - {host_port: '${port}', container_port: 80}
          - {host_port: 8443, container_port: 443}
"""
    runtime = {"network": {"published_ports": [{"host_port": 8080, "container_port": 80}]}}
    _, _, manifest = _fixture(runtime)
    execution = plan(compile_runtime_model(instantiate_scenario(parse_sdl(source))), manifest)
    assert execution.is_valid, execution.diagnostics
    runtime["network"]["published_ports"] = [
        {"host_port": 8443, "container_port": peer_port},
        {"host_port": selected, "container_port": 80},
    ]
    result = _apply_with_observations(execution.provisioning, manifest, runtime)
    assert result.success is accepted, result.diagnostics


def test_overlapping_finite_endpoint_identities_fail_before_apply():
    from raes import instantiate_scenario, parse_sdl
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.planner import plan

    source = """
name: overlapping-endpoints
variables:
  port:
    type: integer
    default: 8080
    allowed_values: [8080, 8443]
nodes:
  host:
    type: compute
    runtime:
      network:
        published_ports:
          - {host_port: '${port}', container_port: 80}
          - {host_port: 8443, container_port: 443}
"""
    _, _, manifest = _fixture({"network": {"published_ports": [{"host_port": 8080, "container_port": 80}]}})
    execution = plan(compile_runtime_model(instantiate_scenario(parse_sdl(source))), manifest)
    assert not execution.is_valid
    assert any(diagnostic.code == "realization.authority-bound-unavailable" for diagnostic in execution.diagnostics)
