"""RUN-320 binds admitted selections to exact operator-created providers.

The binding is the only provider seam. It accepts already-constructed instances
and never discovers, imports, or names executable code.
"""

import pytest
from participant_control_contract_fixtures import evaluation_payload
from participant_control_runtime_fixtures import (
    INSTANCE,
    MONITOR,
    SyntheticControlProvider,
    SyntheticControlResolver,
    advisory_monitor_payload,
    control_binding,
)
from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel
from raes_runtime.participant_control_binding import ParticipantControlRuntimeBinding


def _selection(payload=None):
    return ParticipantControlSelectionModel.model_validate((payload or evaluation_payload())["request"]["selection"])


def _resolver(payload=None):
    return SyntheticControlResolver(payload=payload or evaluation_payload())


def test_binding_accepts_the_admitted_selection_and_its_exact_providers():
    binding = control_binding()
    assert set(binding.providers) == {INSTANCE}
    assert binding.selection.semantic_revision == "sem-235/rev1"


def test_binding_rejects_a_provider_set_that_differs_from_the_selection():
    selection, resolver = _selection(), _resolver()
    providers = {"unselected": SyntheticControlProvider(instance_id="unselected")}
    with pytest.raises(ValueError, match="participant control providers"):
        ParticipantControlRuntimeBinding(selection=selection, providers=providers, resolver=resolver)


def test_binding_rejects_a_missing_provider_for_a_selected_instance():
    payload = advisory_monitor_payload()
    selection, resolver = _selection(payload), _resolver(payload)
    providers = {INSTANCE: SyntheticControlProvider()}
    with pytest.raises(ValueError, match="participant control providers"):
        ParticipantControlRuntimeBinding(selection=selection, providers=providers, resolver=resolver)


def test_binding_rejects_a_provider_without_the_published_protocol_method():
    selection, resolver = _selection(), _resolver()
    with pytest.raises(TypeError, match="participant control provider"):
        ParticipantControlRuntimeBinding(selection=selection, providers={INSTANCE: object()}, resolver=resolver)


def test_binding_rejects_a_resolver_without_the_declared_runtime_protocol():
    selection, providers = _selection(), {INSTANCE: SyntheticControlProvider()}
    with pytest.raises(TypeError, match="participant control resolver"):
        ParticipantControlRuntimeBinding(selection=selection, providers=providers, resolver=object())


def test_binding_rejects_a_resolver_that_leaves_the_effect_owner_hook_undeclared():
    """Every resolver member is declared at binding, never discovered per effect."""

    class _WithoutEffectOwner:
        def resolve(self, **coordinates: object) -> None:
            return None

        def validation_context(self, evaluation: object) -> None:
            return None

    selection, providers = _selection(), {INSTANCE: SyntheticControlProvider()}
    resolver = _WithoutEffectOwner()
    with pytest.raises(TypeError, match="participant control resolver"):
        ParticipantControlRuntimeBinding(selection=selection, providers=providers, resolver=resolver)


def test_binding_freezes_its_provider_map_against_later_mutation():
    binding = control_binding()
    late = SyntheticControlProvider(instance_id="late")
    with pytest.raises(TypeError):
        binding.providers["late"] = late


def test_binding_revalidates_a_selection_mutated_past_its_validators():
    """``model_copy`` skips validation; the binding rebuilds from the projection."""

    model = _selection()
    mutated = model.model_copy(
        update={
            "bindings": (model.bindings[0].model_copy(update={"protocol_revision": "participant-control-provider/v2"}),)
        }
    )
    assert mutated.bindings[0].protocol_revision == "participant-control-provider/v2"
    providers, resolver = {INSTANCE: SyntheticControlProvider()}, _resolver()
    with pytest.raises(ValueError, match="protocol_revision"):
        ParticipantControlRuntimeBinding(selection=mutated, providers=providers, resolver=resolver)


def test_two_mechanisms_bind_two_published_profiles():
    binding = control_binding(advisory_monitor_payload())
    assert set(binding.providers) == {INSTANCE, MONITOR}
    profiles = {profile.ref for item in binding.selection.bindings for profile in item.profiles}
    assert profiles == {"teaching-influence", "participant-boundary-flow-policy-v1"}
