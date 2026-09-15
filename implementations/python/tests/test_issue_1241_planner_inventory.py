"""Review F2: materialized SDL retains the admitted planner projection context."""

from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_contracts.planning import PlanScope, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import admit_materialization_submission, plan
from test_issue_1241_materialization_context import attesting_plan
from test_issue_1241_materialization_runtime import ReportingProvisioner


def _projected_plan(kind):
    execution, model = attesting_plan()
    manifest = execution.manifest
    context = None
    if kind.startswith("profile"):
        from raes_contracts.realization_profiles import profile_context_digest
        from test_issue_1204_profile_carrier import _profiles

        authority, context = _profiles()
        model = replace(model, profile_authority=authority)
        manifest = replace(
            manifest,
            supported_contract_versions=manifest.supported_contract_versions
            | {
                "plan-realization-profiles-v1",
                "backend-realization-preparation-v1",
            },
            domain_profile_context_digest=profile_context_digest(context),
        )
    else:
        from test_issue_1276_random_value_generation import _scoped_flag_scenario, _with_random_value_support

        manifest = _with_random_value_support(manifest)
        model = compile_runtime_model(parse_sdl(_scoped_flag_scenario(kind).replace("web", "host")))
    result = plan(
        model, manifest, scope=PlanScope(run_id="run-1", instantiation_id="instance-1"), profile_context=context
    )
    assert result.is_valid, result.diagnostics
    if kind == "profile_selected":
        from raes_contracts.domain_profiles import DomainProfileBindingBasis
        from raes_runtime.backend_profiles import prepared_profile_violation

        operations = [
            replace(
                op,
                profile_bindings=tuple(
                    binding.model_copy(
                        update={
                            "value": {"name": "green"},
                            "provenance": binding.provenance.model_copy(
                                update={"basis": DomainProfileBindingBasis.BACKEND_SELECTED}
                            ),
                        }
                    )
                    for binding in op.profile_bindings
                ),
            )
            for op in result.provisioning.operations
        ]
        selected = replace(result.provisioning, operations=operations)
        assert prepared_profile_violation(result.provisioning, selected, context) is None
        result = replace(result, provisioning=selected)
    return result


def test_profile_preparation_and_attestation_share_the_real_apply_pipeline(tmp_path):
    from raes_operations.run_artifacts import RunMaterializationArchive
    from raes_reference_backend import create_reference_backend_target
    from raes_runtime.manager import RuntimeManager
    from test_issue_1204_reference_profiles import _reference_profiles

    authority, context, choices = _reference_profiles()
    target = create_reference_backend_target(domain_profile_context=context, profile_choices=choices)
    manifest = replace(
        target.manifest,
        supported_contract_versions=target.manifest.supported_contract_versions
        | {"backend-materialization-attestation-v1"},
    )

    class ReportingBackend:
        def __getattr__(self, name):
            return getattr(target.provisioner, name)

        def apply(self, request, previous):
            result = target.provisioner.apply(request, previous)
            return ReportingProvisioner(manifest).report(request, previous, result)

    manager = RuntimeManager(
        replace(target, manifest=manifest, provisioner=ReportingBackend()),
        materialization_archive=RunMaterializationArchive(tmp_path),
    )
    execution = manager.plan(
        parse_sdl("name: profiles\nnodes:\n  host: {type: compute}\n"),
        profile_authority=authority,
        run_scope=PlanScope(run_id="run-1"),
    )
    assert execution.is_valid, execution.diagnostics
    result = manager.apply(execution)
    assert result.success, result.diagnostics
    assert result.snapshot.entries["provision.node.host"].profile_bindings[0].value == {"name": "green"}
    assert len(result.snapshot.materialization_attestations) == 1
    assert manager.destroy().success


@pytest.mark.parametrize("kind", ["profile", "profile_selected", "per_run", "per_instantiation"])
@pytest.mark.parametrize("phase", ["provisioning", "orchestration", "evaluation"])
@pytest.mark.parametrize("tampered", [False, True])
def test_materialized_inventory_preserves_trusted_planner_projection(kind, phase, tampered):
    execution = _projected_plan(kind)
    entries = {
        op.address: SnapshotEntry(
            op.address,
            RuntimeDomain.PROVISIONING,
            op.resource_type,
            op.payload,
            ordering_dependencies=op.ordering_dependencies,
            refresh_dependencies=op.refresh_dependencies,
            profile_bindings=op.profile_bindings,
        )
        for op in execution.provisioning.operations
    }
    projected = RuntimeSnapshot(entries=entries)
    previous = RuntimeSnapshot() if phase == "provisioning" else projected
    actual = projected
    if tampered:
        changed = dict(entries)
        if kind.startswith("profile"):
            owner = changed["provision.node.host"]
            assert owner.profile_bindings
            changed[owner.address] = replace(owner, profile_bindings=())
        else:
            owner = changed["provision.generated-artifact.techvault-flag"]
            assert owner.payload["scope_binding"]
            changed[owner.address] = replace(owner, payload={**owner.payload, "scope_binding": "run:forged"})
        actual = RuntimeSnapshot(entries=changed)
    request = replace(getattr(execution, phase), operation_id="materialize-once")
    report = ReportingProvisioner(execution.manifest).report(request, previous, ApplyResult(True, actual))
    if tampered:
        with pytest.raises(ValueError, match="inventory|outside its operation domain"):
            admit_materialization_submission(
                report.materialization_attestation, request, execution.manifest, previous, actual
            )
    else:
        admitted = admit_materialization_submission(
            report.materialization_attestation, request, execution.manifest, previous, actual
        )
        assert "scope_binding" not in admitted.sdl
