"""Negotiated materialization keeps the authenticated full original SDL input."""

import json
from dataclasses import replace

import pytest
from raes import canonical_instantiated_sdl_digest, parse_sdl
from raes_contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
from raes_contracts.planning import PlanScope
from raes_contracts.vocabulary import RealizationSupportMode
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane_api_models import _provisioning_plan
from test_sem_218_realization_designation import _manifest


def attesting_plan(source=None):
    original = _manifest(RealizationSupportMode.OPEN_REALIZATION)
    manifest = replace(
        original,
        supported_contract_versions=original.supported_contract_versions | {"backend-materialization-attestation-v1"},
    )
    model = compile_runtime_model(
        parse_sdl(
            source or "name: retained-context\ndescription: original source context\nnodes:\n  host: {type: compute}"
        )
    )
    return plan(model, manifest, scope=PlanScope(run_id="run-1")), model


def test_negotiated_plan_retains_full_source_not_only_compiled_resources():
    execution, model = attesting_plan()
    assert execution.is_valid, execution.diagnostics
    source = execution.provisioning.materialization_source
    assert source.run_id == "run-1"
    assert source.instantiated_digest == canonical_instantiated_sdl_digest(model.realization_instance).value
    assert json.loads(source.snapshot)["scenario"]["description"] == "original source context"
    assert execution.orchestration.materialization_source == source
    assert execution.evaluation.materialization_source == source
    restored = _provisioning_plan(provisioning_plan_model(execution.provisioning))
    assert restored.materialization_source == source
    assert runtime_plan_digest(restored) == runtime_plan_digest(execution.provisioning)
    assert runtime_plan_digest(replace(restored, materialization_source=None)) != runtime_plan_digest(restored)


def test_tampered_source_cannot_reuse_the_original_input_identity():
    execution, _model = attesting_plan()
    source = execution.provisioning.materialization_source
    changed = json.loads(source.snapshot)
    changed["scenario"]["description"] = "substituted"
    source_type = type(source)
    substituted = {**source.model_dump(), "snapshot": json.dumps(changed)}
    with pytest.raises(ValueError):
        source_type.model_validate(substituted)
