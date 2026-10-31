"""Experiment-owned scenario-family selection policy tests (issue #787)."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from paths import REPO_ROOT
from pydantic import ValidationError
from raes import SDLSelectionError, admit_scenario_family, parse_sdl, validate_experiment_selection_against_family
from raes.scenario import ExpandedScenario, Scenario
from raes.validator import SemanticValidator
from raes_contracts.contracts import ExperimentSpecModel, schema_bundle

_EXPERIMENT_FIXTURE = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "experiment-core"
    / "experiment-authoring-input-v1"
    / "valid"
    / "reference.json"
)
_FAMILY_FIXTURE = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "variation-points-v1" / "valid" / "family.yaml"


def _base_payload() -> dict[str, object]:
    payload = json.loads(_EXPERIMENT_FIXTURE.read_text(encoding="utf-8"))
    payload["intended_scenario_ref"] = {
        "ref_kind": "scenario",
        "ref_id": "fixture-family",
    }
    payload["run_plan"]["stochastic_controls"] = []
    return payload


def _fixed_policy(
    *,
    policy_id: str = "fixed-path",
    point_ref: str = "payload-path",
    value: object = "/opt/a",
) -> dict[str, object]:
    return {
        "kind": "fixed",
        "policy_id": policy_id,
        "purpose": "fixed-configuration",
        "point_ref": point_ref,
        "outcome": {"kind": "literal", "value": value},
        "output_bound": 1,
    }


def _enumerate_policy(
    *,
    policy_id: str = "enumerate-path",
    point_ref: str = "payload-path",
    output_bound: int = 2,
) -> dict[str, object]:
    return {
        "kind": "enumerate",
        "policy_id": policy_id,
        "purpose": "nuisance-variation",
        "point_ref": point_ref,
        "output_bound": output_bound,
    }


def _sampling_control() -> dict[str, object]:
    return {
        "control_id": "sample-control",
        "role": "sampling",
        "executable_binding": {
            "profile_ref": {
                "ref_kind": "profile",
                "ref_id": "blake3-xof-v1",
            },
            "namespace": "fixture-sampling",
            "root_entropy": {
                "kind": "public-seed",
                "encoding": "hex-fixed-width",
                "value": "00" * 32,
            },
        },
    }


def _sample_policy() -> dict[str, object]:
    return {
        "kind": "sample",
        "policy_id": "sample-path",
        "purpose": "nuisance-variation",
        "point_ref": "payload-path",
        "algorithm_profile": "uniform-index-v1",
        "distribution": "uniform",
        "replacement": "with-replacement",
        "sample_count": 200,
        "output_bound": 200,
        "stochastic_control_ref": "sample-control",
    }


def _spec_with_binding_family(binding_family_id: str) -> ExperimentSpecModel:
    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {"fixed-path": _fixed_policy()}
    allocation = payload["run_plan"]["allocation"]
    for condition_id, assignment in allocation["condition_assignments"].items():
        assignment.pop("required_parameters", None)
        assignment["required_refs"] = [
            {
                "ref_kind": "profile",
                "ref_id": f"protocol.reference-red-tactic.{condition_id}",
            }
        ]
    payload["binding_semantics"] = "explicit-required"
    payload["binding_descriptors"] = {
        "schema_version": "experiment-binding-descriptors/v1",
        "descriptors": [
            {
                "binding_id": f"binding.red-tactic.{level}",
                "source_factor_id": "red-tactic",
                "source_factor_level_id": level,
                "source_condition_id": condition_id,
                "target": {
                    "plane": "scenario",
                    "scenario_family_id": binding_family_id,
                    "variation_point_id": "payload-path",
                    "target_id": "variables.payload_path",
                },
                "value_type": "string",
                "value": {"kind": "literal", "value": value},
                "owner": {
                    "contract_id": "sdl-authoring-input-v1",
                    "contract_version": "1",
                    "validator_id": "raes-sdl-instantiation",
                    "validator_version": "1",
                },
            }
            for condition_id, level, value in (
                ("cond-aggressive", "aggressive", "/opt/a"),
                ("cond-stealthy", "stealthy", "/opt/b"),
            )
        ],
    }
    return ExperimentSpecModel.model_validate(payload)


def _expanded_family() -> ExpandedScenario:
    scenario = parse_sdl(_FAMILY_FIXTURE.read_text(encoding="utf-8"))
    return admit_scenario_family(scenario)


def _all_kinds_expanded_family() -> ExpandedScenario:
    payload: dict[str, object] = {
        "name": "all-kinds-family",
        "variables": {
            "payload_path": {
                "type": "string",
                "default": "/opt/a",
                "allowed_values": ["/opt/a", "/opt/b"],
            }
        },
        "nodes": {
            "primary": {
                "type": "compute",
                "os": "linux",
                "resources": {"ram": "1 gib", "cpu": 1},
                "features": {"baseline": ""},
            },
            "secondary": {
                "type": "compute",
                "os": "linux",
                "resources": {"ram": "1 gib", "cpu": 1},
            },
        },
        "features": {
            "baseline": {"type": "configuration"},
            "hardened": {"type": "configuration"},
        },
        "content": {
            "payload": {
                "type": "file",
                "target": "primary",
                "path": "${payload_path}",
            }
        },
        "events": {"recon": {}, "exploit": {}},
        "scripts": {
            "recon": {"start_time": 0, "end_time": 10, "speed": 1, "events": {"recon": 0}},
            "exploit": {"start_time": 10, "end_time": 20, "speed": 1, "events": {"exploit": 10}},
        },
        "stories": {"attack": {"scripts": ["recon", "exploit"]}},
        "variation_points": {
            "payload-path": {
                "kind": "parameter",
                "target": {"kind": "variable", "variable": "payload_path"},
                "domain": {"kind": "enum", "values": ["/opt/a", "/opt/b"]},
            },
            "target-ref": {
                "kind": "governed-reference",
                "target": {"kind": "reference", "owner": "payload", "slot": "content.target"},
                "domain": {
                    "kind": "governed-reference",
                    "authority": "inventory-v1",
                    "allowed_refs": ["primary", "secondary"],
                },
            },
            "host-choice": {
                "kind": "alternative",
                "target": {"kind": "reference", "owner": "payload", "slot": "content.target"},
                "alternatives": {
                    "primary-host": {"reference": "primary"},
                    "secondary-host": {"reference": "secondary"},
                },
            },
            "feature-set": {
                "kind": "subset",
                "target": {"kind": "collection", "owner": "primary", "slot": "nodes.features"},
                "members": {
                    "base": {"reference": "baseline"},
                    "extra": {"reference": "hardened"},
                },
                "minimum": 1,
                "maximum": 2,
            },
            "attack-order": {
                "kind": "order",
                "target": {"kind": "collection", "owner": "attack", "slot": "stories.scripts"},
                "members": {
                    "recon-phase": {"reference": "recon"},
                    "exploit-phase": {"reference": "exploit"},
                },
                "precedence": [{"before": "recon-phase", "after": "exploit-phase"}],
            },
            "start-offset": {
                "kind": "logical-timing",
                "target": {"kind": "logical-timing", "owner": "recon", "slot": "scripts.start_time"},
                "domain": {
                    "kind": "numeric-interval",
                    "numeric_type": "integer",
                    "lower": 0,
                    "upper": 5,
                },
                "unit": "seconds",
            },
        },
    }
    scenario = Scenario.model_validate(payload)
    SemanticValidator(scenario).validate()
    scenario._set_semantic_validated(True)
    expanded = ExpandedScenario.model_validate(payload)
    expanded._set_semantic_validated(True)
    return expanded


def test_fixed_policy_is_a_closed_deterministic_leaf() -> None:
    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {"fixed-path": _fixed_policy()}

    spec = ExperimentSpecModel.model_validate(payload)

    policy = spec.run_plan.selection_policies["fixed-path"]
    assert policy.kind == "fixed"
    assert policy.purpose == "fixed-configuration"
    assert policy.output_bound == 1


def test_enumeration_and_product_use_bounded_named_dimensions() -> None:
    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {
        "fixed-path": _fixed_policy(),
        "enumerate-host": _enumerate_policy(
            policy_id="enumerate-host",
            point_ref="payload-host",
        ),
        "path-host-product": {
            "kind": "product",
            "policy_id": "path-host-product",
            "purpose": "nuisance-variation",
            "policy_refs": ["fixed-path", "enumerate-host"],
            "output_bound": 2,
        },
    }

    spec = ExperimentSpecModel.model_validate(payload)

    assert spec.run_plan.selection_policies["path-host-product"].output_bound == 2


def test_balanced_strata_join_existing_factor_levels_conditions_and_counts() -> None:
    payload = _base_payload()
    payload["factors"] = {
        "payload-host": {
            "name": "Payload host",
            "factor_kind": "treatment",
            "levels": ["primary", "secondary"],
        }
    }
    allocation = payload["run_plan"]["allocation"]
    allocation["compared_conditions"] = ["host-primary", "host-secondary"]
    allocation["condition_assignments"] = {
        "host-primary": {
            "condition_id": "host-primary",
            "factor_levels": {"payload-host": "primary"},
            "required_refs": [{"ref_kind": "scenario-snapshot", "ref_id": "primary"}],
        },
        "host-secondary": {
            "condition_id": "host-secondary",
            "factor_levels": {"payload-host": "secondary"},
            "required_refs": [{"ref_kind": "scenario-snapshot", "ref_id": "secondary"}],
        },
    }
    allocation["target_runs_per_condition"] = 2
    payload["run_plan"]["selection_policies"] = {
        "balanced-host": {
            "kind": "stratified",
            "policy_id": "balanced-host",
            "purpose": "controlled-factor",
            "point_ref": "payload-host",
            "balance": "equal",
            "outcomes": {
                "primary": {"kind": "member", "member_id": "primary-host"},
                "secondary": {"kind": "member", "member_id": "secondary-host"},
            },
            "strata": {
                "host-primary": {
                    "stratum_id": "host-primary",
                    "outcome_ref": "primary",
                    "factor_id": "payload-host",
                    "factor_level_id": "primary",
                    "condition_id": "host-primary",
                    "output_count": 2,
                },
                "host-secondary": {
                    "stratum_id": "host-secondary",
                    "outcome_ref": "secondary",
                    "factor_id": "payload-host",
                    "factor_level_id": "secondary",
                    "condition_id": "host-secondary",
                    "output_count": 2,
                },
            },
            "output_bound": 4,
        }
    }

    spec = ExperimentSpecModel.model_validate(payload)

    assert spec.run_plan.selection_policies["balanced-host"].output_bound == 4


def test_bounded_uniform_sample_requires_one_executable_sampling_control() -> None:
    payload = _base_payload()
    payload["run_plan"]["stochastic_controls"] = [_sampling_control()]
    payload["run_plan"]["selection_policies"] = {"sample-path": _sample_policy()}

    spec = ExperimentSpecModel.model_validate(payload)

    assert spec.run_plan.selection_policies["sample-path"].stochastic_control_ref == "sample-control"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("distribution", "weighted"),
        ("replacement", "without-replacement"),
        ("algorithm_profile", "implementation-default"),
    ],
)
def test_unsupported_sampling_semantics_fail_closed(field: str, value: str) -> None:
    payload = _base_payload()
    payload["run_plan"]["stochastic_controls"] = [_sampling_control()]
    sample = _sample_policy()
    sample[field] = value
    payload["run_plan"]["selection_policies"] = {"sample-path": sample}

    with pytest.raises(ValidationError):
        ExperimentSpecModel.model_validate(payload)


def test_t_way_coverage_fails_closed_until_an_exact_profile_exists() -> None:
    payload = _base_payload()
    coverage = _enumerate_policy()
    coverage["kind"] = "coverage"
    coverage["strength"] = 2
    payload["run_plan"]["selection_policies"] = {"enumerate-path": coverage}

    with pytest.raises(ValidationError):
        ExperimentSpecModel.model_validate(payload)


def test_stochastic_policy_rejects_descriptive_or_missing_control() -> None:
    payload = _base_payload()
    payload["run_plan"]["stochastic_controls"] = [
        {
            "control_id": "sample-control",
            "role": "sampling",
            "value": 7,
        }
    ]
    payload["run_plan"]["selection_policies"] = {"sample-path": _sample_policy()}

    with pytest.raises(ValidationError, match="executable"):
        ExperimentSpecModel.model_validate(payload)


@pytest.mark.parametrize(
    "policy",
    [
        {**_fixed_policy(), "purpose": "controlled-factor"},
        {**_enumerate_policy(), "purpose": "controlled-factor"},
        {**_sample_policy(), "purpose": "controlled-factor"},
    ],
)
def test_controlled_factor_leaf_requires_authoritative_binding_join(
    policy: dict[str, object],
) -> None:
    payload = _base_payload()
    if policy["kind"] == "sample":
        payload["run_plan"]["stochastic_controls"] = [_sampling_control()]
    payload["run_plan"]["selection_policies"] = {policy["policy_id"]: policy}

    with pytest.raises(ValidationError, match="controlled-factor"):
        ExperimentSpecModel.model_validate(payload)


def test_controlled_factor_product_requires_a_controlled_bound_dimension() -> None:
    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {
        "fixed-path": _fixed_policy(),
        "enumerate-host": _enumerate_policy(
            policy_id="enumerate-host",
            point_ref="payload-host",
        ),
        "controlled-product": {
            "kind": "product",
            "policy_id": "controlled-product",
            "purpose": "controlled-factor",
            "policy_refs": ["fixed-path", "enumerate-host"],
            "output_bound": 2,
        },
    }

    with pytest.raises(ValidationError, match="controlled-factor"):
        ExperimentSpecModel.model_validate(payload)


def test_controlled_factor_product_derives_from_a_joined_stratified_dimension() -> None:
    fixture = (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "experiment-core"
        / "experiment-authoring-input-v1"
        / "valid"
        / "stratified-selection.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["run_plan"]["selection_policies"].update(
        {
            "fixed-path": _fixed_policy(),
            "controlled-product": {
                "kind": "product",
                "policy_id": "controlled-product",
                "purpose": "controlled-factor",
                "policy_refs": ["balanced-host", "fixed-path"],
                "output_bound": 4,
            },
        }
    )

    spec = ExperimentSpecModel.model_validate(payload)

    assert spec.run_plan.selection_policies["controlled-product"].purpose == "controlled-factor"


def test_policy_registry_key_and_product_graph_are_validated() -> None:
    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {"wrong-key": _fixed_policy()}
    with pytest.raises(ValidationError, match="policy_id"):
        ExperimentSpecModel.model_validate(payload)

    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {
        "fixed-path": _fixed_policy(),
        "product-a": {
            "kind": "product",
            "policy_id": "product-a",
            "purpose": "nuisance-variation",
            "policy_refs": ["product-b", "fixed-path"],
            "output_bound": 1,
        },
        "product-b": {
            "kind": "product",
            "policy_id": "product-b",
            "purpose": "nuisance-variation",
            "policy_refs": ["product-a", "fixed-path"],
            "output_bound": 1,
        },
    }
    with pytest.raises(ValidationError, match="acyclic"):
        ExperimentSpecModel.model_validate(payload)


def test_stratum_condition_reference_fails_as_bounded_validation_error() -> None:
    fixture = (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "experiment-core"
        / "experiment-authoring-input-v1"
        / "valid"
        / "stratified-selection.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    policy = payload["run_plan"]["selection_policies"]["balanced-host"]
    policy["strata"]["host-primary"]["condition_id"] = "missing-condition"

    with pytest.raises(ValidationError, match="condition_id"):
        ExperimentSpecModel.model_validate(payload)


@pytest.mark.parametrize(
    "policies",
    [
        {"fixed-path": _fixed_policy()},
        {"enumerate-path": _enumerate_policy()},
        {
            "fixed-path": _fixed_policy(),
            "enumerate-host": _enumerate_policy(
                policy_id="enumerate-host",
                point_ref="payload-host",
            ),
            "path-host-product": {
                "kind": "product",
                "policy_id": "path-host-product",
                "purpose": "nuisance-variation",
                "policy_refs": ["fixed-path", "enumerate-host"],
                "output_bound": 2,
            },
        },
    ],
)
def test_contextual_admission_resolves_supported_policies_against_expanded_family(
    policies: dict[str, object],
) -> None:
    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = policies
    spec = ExperimentSpecModel.model_validate(payload)

    admitted = validate_experiment_selection_against_family(
        spec,
        family=_expanded_family(),
    )

    assert admitted is spec


def test_contextual_admission_rejects_unknown_points_and_out_of_domain_values() -> None:
    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {
        "fixed-path": _fixed_policy(value="/secret/not-in-domain"),
    }
    spec = ExperimentSpecModel.model_validate(payload)
    family = _expanded_family()
    with pytest.raises(SDLSelectionError, match="domain"):
        validate_experiment_selection_against_family(
            spec,
            family=family,
        )

    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {
        "fixed-missing": _fixed_policy(
            policy_id="fixed-missing",
            point_ref="missing-point",
        )
    }
    spec = ExperimentSpecModel.model_validate(payload)
    with pytest.raises(SDLSelectionError, match="variation point"):
        validate_experiment_selection_against_family(
            spec,
            family=family,
        )


@pytest.mark.parametrize(
    ("point_ref", "outcome"),
    [
        ("payload-path", {"kind": "literal", "value": "/opt/a"}),
        ("target-ref", {"kind": "reference", "reference_id": "primary"}),
        ("host-choice", {"kind": "member", "member_id": "primary-host"}),
        ("feature-set", {"kind": "subset", "member_ids": ["base"]}),
        (
            "attack-order",
            {"kind": "order", "member_ids": ["recon-phase", "exploit-phase"]},
        ),
        ("start-offset", {"kind": "literal", "value": 3}),
    ],
)
def test_fixed_outcomes_cover_every_sdl_variation_point_kind(
    point_ref: str,
    outcome: dict[str, object],
) -> None:
    payload = _base_payload()
    payload["intended_scenario_ref"]["ref_id"] = "all-kinds-family"
    policy = _fixed_policy(point_ref=point_ref)
    policy["outcome"] = outcome
    payload["run_plan"]["selection_policies"] = {"fixed-path": policy}
    spec = ExperimentSpecModel.model_validate(payload)

    admitted = validate_experiment_selection_against_family(
        spec,
        family=_all_kinds_expanded_family(),
    )

    assert admitted is spec


@pytest.mark.parametrize(
    ("point_ref", "outcome"),
    [
        ("target-ref", {"kind": "reference", "reference_id": "outside-domain"}),
        ("host-choice", {"kind": "member", "member_id": "outside-domain"}),
    ],
)
def test_reference_and_member_outcomes_reject_out_of_domain_ids(
    point_ref: str,
    outcome: dict[str, object],
) -> None:
    payload = _base_payload()
    payload["intended_scenario_ref"]["ref_id"] = "all-kinds-family"
    policy = _fixed_policy(point_ref=point_ref)
    policy["outcome"] = outcome
    payload["run_plan"]["selection_policies"] = {"fixed-path": policy}
    spec = ExperimentSpecModel.model_validate(payload)
    family = _all_kinds_expanded_family()

    with pytest.raises(SDLSelectionError, match="domain"):
        validate_experiment_selection_against_family(
            spec,
            family=family,
        )


def test_contextual_admission_rejects_invalid_subset_order_and_continuous_enumeration() -> None:
    family = _all_kinds_expanded_family()
    payload = _base_payload()
    payload["intended_scenario_ref"]["ref_id"] = "all-kinds-family"
    invalid_order = _fixed_policy(point_ref="attack-order")
    invalid_order["outcome"] = {
        "kind": "order",
        "member_ids": ["exploit-phase", "recon-phase"],
    }
    payload["run_plan"]["selection_policies"] = {"fixed-path": invalid_order}
    spec = ExperimentSpecModel.model_validate(payload)
    with pytest.raises(SDLSelectionError, match="precedence"):
        validate_experiment_selection_against_family(
            spec,
            family=family,
        )

    invalid_subset = _fixed_policy(point_ref="feature-set")
    invalid_subset["outcome"] = {"kind": "subset", "member_ids": []}
    payload["run_plan"]["selection_policies"] = {"fixed-path": invalid_subset}
    spec = ExperimentSpecModel.model_validate(payload)
    with pytest.raises(SDLSelectionError, match="cardinality"):
        validate_experiment_selection_against_family(
            spec,
            family=family,
        )

    family.variation_points["start-offset"].domain.numeric_type = "number"  # type: ignore[union-attr]
    payload["run_plan"]["selection_policies"] = {
        "enumerate-path": _enumerate_policy(
            point_ref="start-offset",
            output_bound=6,
        )
    }
    spec = ExperimentSpecModel.model_validate(payload)
    with pytest.raises(SDLSelectionError, match="continuous"):
        validate_experiment_selection_against_family(
            spec,
            family=family,
        )


def test_uniform_sampling_and_balanced_strata_resolve_against_family() -> None:
    payload = _base_payload()
    payload["run_plan"]["stochastic_controls"] = [_sampling_control()]
    payload["run_plan"]["selection_policies"] = {"sample-path": _sample_policy()}
    sample_spec = ExperimentSpecModel.model_validate(payload)
    admitted_sample = validate_experiment_selection_against_family(
        sample_spec,
        family=_expanded_family(),
    )
    assert admitted_sample is sample_spec

    payload = _base_payload()
    payload["factors"] = {
        "payload-host": {
            "name": "Payload host",
            "factor_kind": "treatment",
            "levels": ["primary", "secondary"],
        }
    }
    allocation = payload["run_plan"]["allocation"]
    allocation["compared_conditions"] = ["host-primary", "host-secondary"]
    allocation["condition_assignments"] = {
        "host-primary": {
            "condition_id": "host-primary",
            "factor_levels": {"payload-host": "primary"},
            "required_refs": [{"ref_kind": "scenario-snapshot", "ref_id": "primary"}],
        },
        "host-secondary": {
            "condition_id": "host-secondary",
            "factor_levels": {"payload-host": "secondary"},
            "required_refs": [{"ref_kind": "scenario-snapshot", "ref_id": "secondary"}],
        },
    }
    allocation["target_runs_per_condition"] = 2
    payload["run_plan"]["selection_policies"] = {
        "balanced-host": {
            "kind": "stratified",
            "policy_id": "balanced-host",
            "purpose": "controlled-factor",
            "point_ref": "payload-host",
            "balance": "equal",
            "outcomes": {
                "primary": {"kind": "member", "member_id": "primary-host"},
                "secondary": {"kind": "member", "member_id": "secondary-host"},
            },
            "strata": {
                "host-primary": {
                    "stratum_id": "host-primary",
                    "outcome_ref": "primary",
                    "factor_id": "payload-host",
                    "factor_level_id": "primary",
                    "condition_id": "host-primary",
                    "output_count": 2,
                },
                "host-secondary": {
                    "stratum_id": "host-secondary",
                    "outcome_ref": "secondary",
                    "factor_id": "payload-host",
                    "factor_level_id": "secondary",
                    "condition_id": "host-secondary",
                    "output_count": 2,
                },
            },
            "output_bound": 4,
        }
    }
    stratified_spec = ExperimentSpecModel.model_validate(payload)
    admitted_stratified = validate_experiment_selection_against_family(
        stratified_spec,
        family=_expanded_family(),
    )
    assert admitted_stratified is stratified_spec


def test_contextual_admission_requires_trusted_expanded_family_identity() -> None:
    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {"fixed-path": _fixed_policy()}
    spec = ExperimentSpecModel.model_validate(payload)
    scenario = parse_sdl(_FAMILY_FIXTURE.read_text(encoding="utf-8"))

    with pytest.raises(SDLSelectionError, match="ExpandedScenario"):
        validate_experiment_selection_against_family(
            spec,
            family=scenario,  # type: ignore[arg-type]
        )

    mismatched = deepcopy(spec)
    mismatched.intended_scenario_ref.ref_id = "other-family"
    family = _expanded_family()
    with pytest.raises(SDLSelectionError, match="family identity"):
        validate_experiment_selection_against_family(
            mismatched,
            family=family,
        )


def test_contextual_admission_joins_binding_descriptors_to_family_identity() -> None:
    matching = _spec_with_binding_family("fixture-family")

    admitted = validate_experiment_selection_against_family(
        matching,
        family=_expanded_family(),
    )

    assert admitted is matching

    mismatched = _spec_with_binding_family("other-family")
    family = _expanded_family()
    with pytest.raises(SDLSelectionError, match="binding target family identity"):
        validate_experiment_selection_against_family(
            mismatched,
            family=family,
        )


def test_published_schema_declares_selection_semantic_invariants() -> None:
    schema = schema_bundle()["experiment-authoring-input-v1"]
    invariant_ids = {invariant["id"] for invariant in schema["x-raes-invariants"]}

    assert {
        "experiment-selection-policies-valid",
        "experiment-selection-factor-joins-valid",
    }.issubset(invariant_ids)
