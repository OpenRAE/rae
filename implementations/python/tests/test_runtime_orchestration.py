"""Runtime orchestration-authority (RuntimeOrchestrationAuthority) SDL surface tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes._errors import SDLValidationError
from raes.runtime_orchestration import (
    RuntimeOrchestrationAuthority,
    RuntimeOrchestrationEngine,
    RuntimeOrchestrationLifecyclePolicy,
    RuntimeOrchestrationPrivilegeClass,
    RuntimeOrchestrationRealizedChild,
    RuntimeOrchestrationScope,
    RuntimeOrchestrationSpawnTemplate,
)
from raes.scenario import Scenario
from raes.validator import SemanticValidator

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _host_root_authority(**overrides) -> dict:
    authority = {
        "orchestration_authority_id": "shuffle-orborus",
        "control_interface_ref": "docker-sock",
        "engine": "docker",
        "engine_api_version": "1.44",
        "name": "orborus",
        "scope": {"organization_ref": "org-aptl", "environment_name": "shuffle"},
        "spawn_templates": [
            {"template_id": "worker", "image_ref": "ghcr.io/shuffle/shuffle-worker:1.4.0", "purpose": "workflow"}
        ],
        "lifecycle_policy": {"timeout": "300s", "cleanup": "on_exit", "execution_timeout": "600s"},
        "realized_children": [
            {"workload_id": "worker-pool", "image_ref": "shuffle-worker:1.4.0", "count": 550, "evidence_ref": "ev-1"}
        ],
        "privilege_class": "host_root_equivalent",
    }
    authority.update(overrides)
    return authority


def _namespaced_authority(**overrides) -> dict:
    authority = {
        "orchestration_authority_id": "rootless-runner",
        "engine": "podman",
        "privilege_class": "namespaced",
    }
    authority.update(overrides)
    return authority


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_full_host_root_authority_is_valid() -> None:
    authority = RuntimeOrchestrationAuthority(**_host_root_authority())
    assert authority.orchestration_authority_id == "shuffle-orborus"
    assert authority.control_interface_ref == "docker-sock"
    assert authority.engine == RuntimeOrchestrationEngine.DOCKER
    assert authority.engine_api_version == "1.44"
    assert authority.privilege_class == RuntimeOrchestrationPrivilegeClass.HOST_ROOT_EQUIVALENT
    assert authority.scope.organization_ref == "org-aptl"
    assert authority.spawn_templates[0].template_id == "worker"
    assert authority.lifecycle_policy.execution_timeout == "600s"
    assert authority.realized_children[0].count == 550


def test_namespaced_authority_without_control_interface_is_valid() -> None:
    authority = RuntimeOrchestrationAuthority(**_namespaced_authority())
    assert authority.privilege_class == RuntimeOrchestrationPrivilegeClass.NAMESPACED
    assert authority.control_interface_ref == ""


def test_minimal_authority_defaults_to_unknown() -> None:
    authority = RuntimeOrchestrationAuthority(orchestration_authority_id="auth-1")
    assert authority.engine == RuntimeOrchestrationEngine.UNKNOWN
    assert authority.privilege_class == RuntimeOrchestrationPrivilegeClass.UNKNOWN
    assert authority.scope is None
    assert authority.lifecycle_policy is None
    assert authority.spawn_templates == []
    assert authority.realized_children == []


# --------------------------------------------------------------------------- #
# Stable-id rejection (empty / variable placeholder)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad_id", ["", "   ", "${authority}"])
def test_authority_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="orchestration_authority_id"):
        RuntimeOrchestrationAuthority(**_namespaced_authority(orchestration_authority_id=bad_id))


@pytest.mark.parametrize("bad_id", ["", "${template}"])
def test_template_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="template_id"):
        RuntimeOrchestrationSpawnTemplate(template_id=bad_id)


@pytest.mark.parametrize("bad_id", ["", "${workload}"])
def test_workload_id_rejects_empty_or_variable(bad_id: str) -> None:
    with pytest.raises(ValidationError, match="workload_id"):
        RuntimeOrchestrationRealizedChild(workload_id=bad_id)


# --------------------------------------------------------------------------- #
# Enum normalization + sentinels
# --------------------------------------------------------------------------- #


def test_engine_normalization_is_case_and_separator_insensitive() -> None:
    authority = RuntimeOrchestrationAuthority(orchestration_authority_id="a", engine="CRI-O")
    assert authority.engine == RuntimeOrchestrationEngine.CRI_O


def test_privilege_class_normalization_is_case_and_separator_insensitive() -> None:
    authority = RuntimeOrchestrationAuthority(
        orchestration_authority_id="a",
        control_interface_ref="sock",
        privilege_class="HOST-ROOT-EQUIVALENT",
    )
    assert authority.privilege_class == RuntimeOrchestrationPrivilegeClass.HOST_ROOT_EQUIVALENT


def test_unknown_and_other_sentinels_present_on_open_enums() -> None:
    assert RuntimeOrchestrationEngine.UNKNOWN
    assert RuntimeOrchestrationEngine.OTHER
    assert RuntimeOrchestrationPrivilegeClass.UNKNOWN
    assert RuntimeOrchestrationPrivilegeClass.OTHER


def test_engine_variable_placeholder_is_preserved() -> None:
    authority = RuntimeOrchestrationAuthority(orchestration_authority_id="a", engine="${engine}")
    assert authority.engine == "${engine}"


def test_unknown_enum_value_is_rejected() -> None:
    with pytest.raises(ValidationError, match="engine"):
        RuntimeOrchestrationAuthority(orchestration_authority_id="a", engine="not-a-real-engine")


# --------------------------------------------------------------------------- #
# require_profile_for_privilege_class guard
# --------------------------------------------------------------------------- #


def test_host_root_description_allows_missing_interface_knowledge() -> None:
    authority = RuntimeOrchestrationAuthority(**_host_root_authority(control_interface_ref=""))
    assert authority.control_interface_ref == ""


def test_host_root_template_allows_variable_interface_ref() -> None:
    authority = RuntimeOrchestrationAuthority(**_host_root_authority(control_interface_ref="${sock}"))
    assert authority.control_interface_ref == "${sock}"


def test_host_root_equivalent_with_concrete_ref_passes() -> None:
    authority = RuntimeOrchestrationAuthority(**_host_root_authority(control_interface_ref="docker-sock"))
    assert authority.control_interface_ref == "docker-sock"


def test_variable_privilege_class_is_exempt_from_guard() -> None:
    # A ${var} discriminator asserts nothing concrete, so the guard must not fire
    # even with an empty control_interface_ref.
    authority = RuntimeOrchestrationAuthority(
        orchestration_authority_id="a",
        privilege_class="${privilege}",
        control_interface_ref="",
    )
    assert authority.privilege_class == "${privilege}"


@pytest.mark.parametrize("permissive", ["namespaced", "unknown", "other"])
def test_permissive_privilege_classes_do_not_require_control_interface(permissive: str) -> None:
    authority = RuntimeOrchestrationAuthority(
        orchestration_authority_id="a",
        privilege_class=permissive,
        control_interface_ref="",
    )
    assert authority.control_interface_ref == ""


# --------------------------------------------------------------------------- #
# realized-child count parsing
# --------------------------------------------------------------------------- #


def test_realized_child_count_accepts_int_var_and_none() -> None:
    assert RuntimeOrchestrationRealizedChild(workload_id="w", count=12).count == 12
    assert RuntimeOrchestrationRealizedChild(workload_id="w", count="${n}").count == "${n}"
    assert RuntimeOrchestrationRealizedChild(workload_id="w").count is None


def test_realized_child_count_rejects_negative() -> None:
    with pytest.raises(ValidationError, match="count"):
        RuntimeOrchestrationRealizedChild(workload_id="w", count=-1)


def test_realized_child_count_rejects_non_integer() -> None:
    with pytest.raises(ValidationError, match="count"):
        RuntimeOrchestrationRealizedChild(workload_id="w", count="lots")


# --------------------------------------------------------------------------- #
# Local stable-id uniqueness
# --------------------------------------------------------------------------- #


def test_duplicate_spawn_template_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime orchestration stable id"):
        RuntimeOrchestrationAuthority(
            **_namespaced_authority(
                spawn_templates=[{"template_id": "dup"}, {"template_id": "dup"}],
            )
        )


def test_duplicate_workload_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime orchestration stable id"):
        RuntimeOrchestrationAuthority(
            **_namespaced_authority(
                realized_children=[{"workload_id": "dup"}, {"workload_id": "dup"}],
            )
        )


def test_template_id_colliding_with_authority_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime orchestration stable id"):
        RuntimeOrchestrationAuthority(
            **_namespaced_authority(
                orchestration_authority_id="shared",
                spawn_templates=[{"template_id": "shared"}],
            )
        )


def test_template_and_workload_id_collision_across_collections_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Duplicate runtime orchestration stable id"):
        RuntimeOrchestrationAuthority(
            **_namespaced_authority(
                spawn_templates=[{"template_id": "shared"}],
                realized_children=[{"workload_id": "shared"}],
            )
        )


def test_distinct_ids_across_collections_are_accepted() -> None:
    authority = RuntimeOrchestrationAuthority(
        **_namespaced_authority(
            spawn_templates=[{"template_id": "t1"}, {"template_id": "t2"}],
            realized_children=[{"workload_id": "w1"}, {"workload_id": "w2"}],
        )
    )
    assert {t.template_id for t in authority.spawn_templates} == {"t1", "t2"}
    assert {c.workload_id for c in authority.realized_children} == {"w1", "w2"}


# --------------------------------------------------------------------------- #
# Nested-model field plumbing + extra-field rejection
# --------------------------------------------------------------------------- #


def test_scope_and_lifecycle_models_carry_their_fields() -> None:
    scope = RuntimeOrchestrationScope(organization_ref="org", environment_name="env")
    assert scope.organization_ref == "org"
    policy = RuntimeOrchestrationLifecyclePolicy(timeout="1m", cleanup="always", execution_timeout="10m")
    assert policy.cleanup == "always"


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        RuntimeOrchestrationAuthority(orchestration_authority_id="a", bogus_field="x")


# --------------------------------------------------------------------------- #
# Scenario-level control_interface_ref resolution (validator.py)
# --------------------------------------------------------------------------- #


def _validate(scenario: Scenario) -> list[str]:
    validator = SemanticValidator(scenario)
    try:
        validator.validate()
        return []
    except SDLValidationError as exc:
        return exc.errors


def _docker_sock_interface(**overrides) -> dict:
    interface = {
        "control_interface_id": "docker-sock",
        "path": "/var/run/docker.sock",
        "kind": "unix_socket",
        "access": "read_write",
    }
    interface.update(overrides)
    return interface


def _authority_node(*, authority: dict, interfaces: list[dict] | None = None) -> dict:
    return {
        "type": "compute",
        "resources": {"ram": "2 gib", "cpu": 2},
        "runtime": {
            "local_control_interfaces": interfaces if interfaces is not None else [_docker_sock_interface()],
            "orchestration_authorities": [authority],
        },
    }


def test_surface_is_node_scoped_not_top_level() -> None:
    assert "orchestration_authorities" not in Scenario.model_fields


def test_host_root_authority_with_docker_sock_interface_is_valid() -> None:
    scenario = Scenario(
        name="orchestration",
        nodes={"soar": _authority_node(authority=_host_root_authority())},
    )
    assert _validate(scenario) == []


def test_control_interface_ref_must_resolve_to_same_node_interface() -> None:
    scenario = Scenario(
        name="orchestration",
        nodes={
            "soar": _authority_node(
                authority=_host_root_authority(control_interface_ref="missing-sock"),
            )
        },
    )
    errors = _validate(scenario)
    assert any("control_interface_ref 'missing-sock'" in error for error in errors)


def test_host_root_description_preserves_observed_access_without_granting_it() -> None:
    scenario = Scenario(
        name="orchestration",
        nodes={
            "soar": _authority_node(
                authority=_host_root_authority(), interfaces=[_docker_sock_interface(access="read_only")]
            )
        },
    )
    assert _validate(scenario) == []
    assert scenario.nodes["soar"].runtime.local_control_interfaces[0].access == "read_only"


def test_host_root_interface_is_not_identified_by_docker_filename() -> None:
    scenario = Scenario(
        name="orchestration",
        nodes={
            "soar": _authority_node(
                authority=_host_root_authority(), interfaces=[_docker_sock_interface(path="/run/podman/podman.sock")]
            )
        },
    )
    assert _validate(scenario) == []


def test_namespaced_authority_control_interface_is_resolved_but_not_docker_constrained() -> None:
    # Every supplied concrete interface reference must resolve, independently
    # of descriptive privilege or the selected operation's access requirements.
    authority = _namespaced_authority(control_interface_ref="docker-sock")
    scenario = Scenario(
        name="orchestration",
        nodes={
            "runner": _authority_node(
                authority=authority,
                interfaces=[_docker_sock_interface(access="read_only", path="/var/run/podman.sock")],
            )
        },
    )
    assert _validate(scenario) == []
