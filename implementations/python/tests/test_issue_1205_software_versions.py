"""Software version predicates retain their explicit comparison semantics."""

import pytest
from pydantic import ValidationError
from raes.runtime_software import RuntimeSoftwareComponent
from raes_contracts.canonical import canonical_json_digest


def _relation(name="numeric-triplet"):
    return {
        "authority": "https://openrae.org/semantics/versions",
        "contract_id": name,
        "revision": "1",
        "digest": canonical_json_digest({"relation": name, "revision": "1"}),
    }


def test_component_accepts_version_range_without_an_exact_author_version():
    component = RuntimeSoftwareComponent.model_validate(
        {
            "component_id": "scanner",
            "name": "scanner",
            "version_constraint": {
                "kind": "version",
                "relation": _relation(),
                "lower": "7.9.0",
                "upper": "7.11.0",
                "upper_closed": False,
            },
        }
    )
    assert "version" not in component.model_fields_set
    from raes_contracts.software_versions import version_membership

    assert version_membership("7.10.0", component.version_constraint) == "conformant"
    assert version_membership("7.11.0", component.version_constraint) == "nonconformant"


@pytest.mark.parametrize(
    "relation,lower,upper,actual,expected",
    [
        ("numeric-triplet", "7.9.0", None, "7.10.0", "conformant"),
        ("numeric-triplet", None, "7.10.0", "7.9.0", "conformant"),
        ("numeric-triplet", "7.9.0", None, "7.9.0", "nonconformant"),
        ("numeric-triplet", None, "7.10.0", "7.10.0", "nonconformant"),
        ("numeric-triplet", "7.9.0", None, "7.10.0-1", "unresolved"),
        ("debian", "1:1.0-2", None, "2:0.1-1", "conformant"),
        ("debian", None, "1.0-1", "1.0~rc1-1", "conformant"),
        ("rpm", "1.0-1", None, "1.0-2", "conformant"),
        ("rpm", "2.0", "2.0.1", "2.0^20250611", "conformant"),
        ("private-order", "a", "z", "m", "unsupported"),
    ],
)
def test_named_version_relation_boundaries(relation, lower, upper, actual, expected):
    from raes_contracts.software_versions import VersionDomain, version_membership

    domain = VersionDomain(
        relation=_relation(relation), lower=lower, upper=upper, lower_closed=False, upper_closed=False
    )
    assert version_membership(actual, domain) == expected


def test_application_constraint_does_not_constrain_distribution_package_version():
    component = RuntimeSoftwareComponent.model_validate(
        {
            "component_id": "agent",
            "name": "agent",
            "version": "4.12.0",
            "package_version": "4.12.0-1",
            "version_constraint": {"relation": _relation(), "lower": "4.0.0", "upper": "5.0.0"},
        }
    )
    assert component.package_version == "4.12.0-1"
    with pytest.raises(ValidationError, match="version.*constraint"):
        RuntimeSoftwareComponent.model_validate({**component.model_dump(), "version": "6.0.0"})


def test_recursive_relation_retains_unknown_comparison_as_unsupported():
    from raes_contracts.realization_structure import RealizationConstraintDocument, evaluate_realization_constraint

    document = RealizationConstraintDocument.model_validate(
        {
            "semantic_profile": "software-requirements/v1",
            "root": {
                "kind": "domain",
                "domain": {"kind": "version", "relation": _relation("private-order"), "lower": "a"},
            },
        }
    )
    restored = RealizationConstraintDocument.model_validate_json(document.model_dump_json())
    assert evaluate_realization_constraint(restored, "b").status.value == "unsupported"


@pytest.mark.parametrize("mutation", ["digest", "revision", "authority"])
def test_similarly_named_relation_does_not_claim_installed_semantics(mutation):
    from raes_contracts.software_versions import VersionDomain, version_membership

    relation = _relation()
    relation[mutation] = {"digest": "sha256:" + "0" * 64, "revision": "2", "authority": "urn:private"}[mutation]
    assert version_membership("1.0.0", VersionDomain(relation=relation, lower="0.0.0")) == "unsupported"


@pytest.mark.parametrize("literal_first", [True, False])
def test_unknown_comparison_survives_exact_constraint_composition(literal_first):
    from raes_contracts.realization_structure import (
        RealizationConstraintDocument,
        compose_realization_constraints,
        evaluate_realization_constraint,
    )

    exact = RealizationConstraintDocument.model_validate(
        {
            "semantic_profile": "test",
            "root": {"kind": "literal", "value": "b"},
        }
    )
    domain = exact.model_copy(
        update={
            "root": RealizationConstraintDocument.model_validate(
                {
                    "semantic_profile": "test",
                    "root": {
                        "kind": "domain",
                        "domain": {
                            "kind": "version",
                            "relation": _relation("private-order"),
                            "lower": "a",
                        },
                    },
                }
            ).root
        }
    )
    operands = (exact, domain) if literal_first else (domain, exact)
    composed = compose_realization_constraints(*operands)
    assert composed.status.value == "conformant"
    assert evaluate_realization_constraint(composed.document, "b").status.value == "unsupported"


@pytest.mark.parametrize("actual", ["1-", "1::2", "1.0-💥", "1.0\n"])
def test_malformed_debian_values_are_unresolved_not_guessed(actual):
    from raes_contracts.software_versions import VersionDomain, version_membership

    domain = VersionDomain(relation=_relation("debian"), lower="1.0")
    assert version_membership(actual, domain) == "unresolved"


def test_successful_version_relation_has_no_failure_diagnostics():
    from raes_contracts.realization_structure import RealizationConstraintDocument, evaluate_realization_constraint

    document = RealizationConstraintDocument.model_validate(
        {
            "semantic_profile": "test",
            "root": {
                "kind": "domain",
                "domain": {"kind": "version", "relation": _relation(), "lower": "1.0.0"},
            },
        }
    )
    result = evaluate_realization_constraint(document, "2.0.0")
    assert result.conformant
    assert result.diagnostics == ()
