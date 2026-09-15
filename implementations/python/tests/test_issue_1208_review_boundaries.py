"""Review regressions for exact authored authority and realized credentials."""

import pytest
from raes_contracts.bounded_domains import EnumDomain
from raes_contracts.profile_selections import selected_profile_authority
from raes_contracts.realization_profiles import ProfileBindingConstraint
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationDomainValue,
    RealizationNormalizationMetadata,
    normalize_realization_literal,
    realization_constraint_binding,
)
from test_issue_1208_profile_selections import _account_profile, _mailbox_case


def test_supplied_authority_cannot_broaden_any_authored_value():
    binding, context = _account_profile()
    exact = selected_profile_authority((binding,), context, None)
    document = normalize_realization_literal(
        binding.value,
        semantic_profile=binding.coordinate.definition_digest,
        default_closure=RealizationClosure(posture="closed", universe="profile-value", profile="test/v1"),
        metadata=RealizationNormalizationMetadata(
            leaf_constraints={
                "/mailbox_ref": RealizationDomainValue(
                    kind="domain", domain=EnumDomain(values=[binding.value["mailbox_ref"], "another"])
                )
            }
        ),
    ).document
    wider = exact.model_copy(
        update={
            "constraints": (
                ProfileBindingConstraint(
                    binding_path=(binding.binding_id,),
                    document=document,
                    source_binding=realization_constraint_binding(document, binding.value),
                ),
            )
        }
    )
    assert selected_profile_authority((binding,), None, exact) == exact
    with pytest.raises(ValueError, match="constraint"):
        selected_profile_authority((binding,), None, wider)


def test_mailbox_target_refuses_credentials_without_materialization_before_driver_mutation():
    from raes.scenario import Scenario
    from test_issue_673_account_credential_bindings import _account_payload

    _, _, _, manager, _, driver = _mailbox_case()
    account = _account_payload()
    account["node"] = "mail"
    scenario = Scenario.model_validate(
        {"name": "unbound", "nodes": {"mail": {"type": "compute"}}, "accounts": {"admin": account}}
    )
    execution = manager.plan(scenario)
    before = list(driver.recorded_ops)
    result = manager.apply(execution)
    assert not result.success
    assert driver.recorded_ops == before


def test_exact_source_constraint_preserves_unrelated_programmatic_authority():
    binding, context = _account_profile()
    unrelated = binding.model_copy(update={"binding_id": "unrelated"})
    combined = selected_profile_authority((binding, unrelated), context, None)
    assert selected_profile_authority((binding,), None, combined) == combined


def test_nested_authored_binding_also_requires_its_exact_constraint():
    binding, context = _account_profile()
    nested = binding.model_copy(update={"binding_id": "nested"})
    parent = binding.model_copy(update={"children": (nested,)})
    exact = selected_profile_authority((parent,), context, None)
    altered = exact.model_copy(update={"constraints": tuple(c for c in exact.constraints if len(c.binding_path) == 1)})
    with pytest.raises(ValueError, match="constraint"):
        selected_profile_authority((parent,), None, altered)
