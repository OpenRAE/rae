"""SDL adapters for canonical recursive-realization semantic addresses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.errors import InvalidInputError
from raes_contracts.json_pointer import pointer_from_tokens, unescape_token
from raes_contracts.lexical_scope import select_lexical_scope
from raes_contracts.realization_structure import (
    RealizationClosure,
    RealizationCollectionProfile,
    canonical_semantic_address,
    semantic_address_contains,
    validate_realization_value,
)
from raes_contracts.runtime_value_limits import PLAN_VALUE_LIMITS
from raes_contracts.safe_state import ResolvedSafeState, SafeStateDocument, SafeStateProof, SafeStateScope

from ._declarations import DeclarationIndex, build_declaration_index
from ._reference_targetability import ReferencePurpose, declaration_eligible

if TYPE_CHECKING:
    from .scenario import ScenarioContent


def canonical_observation_reference(index: DeclarationIndex, reference: str) -> str:
    """Resolve one observation-subject spelling to exactly one canonical declaration address."""

    candidates = index.reference_aliases(ReferencePurpose.OBSERVATION_SUBJECT).get(reference, set())
    if not candidates:
        raise ValueError(f"observation component reference '{reference}' is not an eligible observation subject")
    if len(candidates) != 1:
        choices = ", ".join(sorted(candidates))
        raise ValueError(f"observation component reference '{reference}' is ambiguous; use one of: {choices}")
    return next(iter(candidates))


def observation_reference_scope(
    index: DeclarationIndex,
    address: str,
    root: object,
    *,
    collection_profiles: tuple[RealizationCollectionProfile, ...] = (),
) -> str:
    """Project one canonical declaration through the shared semantic-address owner."""

    declaration = index.declaration_for(address)
    if declaration is None:
        raise ValueError(f"observation declaration '{address}' is not indexed")
    # A composed declaration key contains dots; they are not path separators.
    tokens = list(declaration.model_tokens)
    if not tokens:
        raise ValueError(f"observation declaration '{address}' has no structural path")
    profile = _declaration_collection_profile(tokens)
    if profile is not None:
        tokens = tokens[:-1]
        if not any(item.field_pointer == profile.field_pointer for item in collection_profiles):
            collection_profiles = (*collection_profiles, profile)
    source_pointer = pointer_from_tokens(tokens)
    if declaration.kind == "service" and profile is not None:
        # Only named ports are declarations. Adjacent unnamed ports must not
        # collide as duplicate empty names in the declaration collection.
        payload = root.model_dump(mode="python") if hasattr(root, "model_dump") else root
        node = payload["nodes"][tokens[1]]
        service = node["services"][int(declaration.model_tokens[-2])]
        isolated = {"nodes": {tokens[1]: {"services": [service]}}}
        source_pointer = pointer_from_tokens([*tokens[:-1], "0"])
        return canonical_semantic_address(source_pointer, isolated, collection_profiles=collection_profiles)
    return canonical_semantic_address(source_pointer, root, collection_profiles=collection_profiles)


def resolve_observation_scope(
    root: object,
    pointer: str,
    *,
    collection_profiles: tuple[RealizationCollectionProfile, ...] = (),
) -> tuple[bool, str | None]:
    """Resolve an observation pointer through the shared semantic-address owner."""

    try:
        canonical = canonical_semantic_address(
            pointer, root, collection_profiles=_scenario_collection_profiles(collection_profiles)
        )
    except ValueError:
        return False, None
    return True, canonical


def _scenario_collection_profiles(
    profiles: tuple[RealizationCollectionProfile, ...],
) -> tuple[RealizationCollectionProfile, ...]:
    """Top-level list declarations retain their native identity across imports."""
    profile = _declaration_collection_profile(["forwarding_agents", "0", "forwarding_agent_id"])
    return profiles if any(item.field_pointer == profile.field_pointer for item in profiles) else (*profiles, profile)


def semantic_scope_namespace(root: dict[str, object], pointer: str) -> tuple[str, ...]:
    """Find the owning module using the declaration identity, never its list index."""
    tokens = pointer.split("/")
    if len(tokens) < 3:
        return ()
    identity = unescape_token(tokens[2])
    if tokens[1] == "forwarding_agents":
        for index, agent in enumerate(root.get("forwarding_agents", ())):
            found, candidate = resolve_observation_scope(root, f"/forwarding_agents/{index}")
            if found and semantic_address_contains(candidate, pointer):
                identity = agent["forwarding_agent_id"]
                break
        else:
            raise ValueError("scope has no admitted declaration owner")
    return tuple(identity.split(".")[:-1])


def _declaration_collection_profile(tokens: list[str]) -> RealizationCollectionProfile | None:
    if len(tokens) < 3 or not tokens[-2].isdigit():
        return None
    parent = pointer_from_tokens(tokens[:-2])
    return RealizationCollectionProfile(
        field_pointer=parent,
        collection_kind="sdl-declaration",
        identity_fields=(tokens[-1],),
        closure=RealizationClosure(
            posture="closed",
            universe="sdl-declarations/v1",
            profile="recursive-realization-constraint/v1",
        ),
    )


__all__ = [
    "canonical_observation_reference",
    "observation_reference_scope",
    "resolve_observation_scope",
    "resolve_safe_states",
]


def _canonical_safe_state_refs(index: DeclarationIndex, refs: list[str]) -> list[str]:
    canonical = []
    for ref in refs:
        matches = index.resolve_for(ref, ReferencePurpose.OBSERVATION_SUBJECT)
        if len(matches) != 1:
            raise ValueError("Safe-state proof reference does not resolve uniquely")
        canonical.append(next(iter(matches)))
    return canonical


def _safe_state_proof_inputs(scenario: ScenarioContent, refs: set[str]) -> dict:
    proofs = {}
    propositions = {}
    for ref in sorted(refs):
        assertion = scenario.assertions.get(ref)
        if assertion is None:
            raise ValueError("Safe-state assertion reference does not resolve")
        if assertion.proposition not in propositions:
            proposition = scenario.propositions.get(assertion.proposition)
            if proposition is None:
                raise ValueError("Safe-state proposition reference does not resolve")
            evidence = {}
            for name in proposition.evidence_requirements:
                requirement = scenario.evidence_requirements.get(name)
                if requirement is None:
                    raise ValueError("Safe-state evidence reference does not resolve")
                evidence[name] = requirement
            # Share source objects; do not clone a proposition for each assertion.
            propositions[assertion.proposition] = {"proposition": proposition, "evidence_requirements": evidence}
        proofs[ref] = {"assertion": assertion, **propositions[assertion.proposition]}
    return proofs


def _safe_state_proof(index: DeclarationIndex, inputs: dict) -> SafeStateProof:
    proposition = inputs["proposition"]
    value = proposition.model_dump(mode="json")
    value["subjects"] = _canonical_safe_state_refs(index, proposition.subjects)
    evidence = {}
    for name, requirement in inputs["evidence_requirements"].items():
        data = requirement.model_dump(mode="json")
        for field in ("source_refs", "scope_refs"):
            data[field] = _canonical_safe_state_refs(index, data[field])
        evidence[name] = data
    return SafeStateProof(
        assertion=inputs["assertion"].model_dump(mode="json"), proposition=value, evidence_requirements=evidence
    )


def resolve_safe_states(scenario: ScenarioContent) -> tuple[ResolvedSafeState, ...]:
    """Resolve all current targets without effects or live-state claims."""
    if scenario.safe_state is None:
        return ()
    document = SafeStateDocument.model_validate(scenario.safe_state.model_dump(mode="json"))
    index = build_declaration_index(scenario)
    payload = scenario.model_dump(mode="json")
    targets = [
        declaration
        for declaration in index.declarations
        if declaration_eligible(declaration, ReferencePurpose.SAFE_STATE_TARGET)
    ]
    scopes = {target.address: observation_reference_scope(index, target.address, payload) for target in targets}
    rules = list(document.scopes)
    if document.default is not None:
        rules.append(SafeStateScope(state=document.default))
    for rule in rules:
        matches = [
            target
            for target in targets
            if semantic_address_contains(rule.scope, scopes[target.address])
            and semantic_scope_namespace(payload, scopes[target.address])[: len(rule.namespace)] == rule.namespace
        ]
        # A defining scope must be a real ancestor, never a field or positional alias.
        if not matches:
            raise ValueError("Safe-state scope or namespace does not resolve to eligible targets")
    inputs = _safe_state_proof_inputs(scenario, {ref for rule in rules for ref in rule.state.assertion_refs})
    bindings = []
    for target in sorted(targets, key=lambda target: target.address):
        scope = scopes[target.address]
        namespace = semantic_scope_namespace(payload, scope)
        rule = select_lexical_scope(rules, scope, namespace)
        if rule is None:
            continue
        if len(bindings) >= 4096:
            raise ValueError("Safe-state resolved target limit exceeded")
        bindings.append(
            {
                "target_ref": target.address,
                "scope": scope,
                "namespace": rule.namespace,
                "governing_scope": ".".join(rule.namespace) + "#" + (rule.scope or "/"),
                "state": rule.state,
                "proofs": {ref: inputs[ref] for ref in rule.state.assertion_refs},
            }
        )
    if not validate_realization_value(
        {"definitions": inputs, "targets": bindings}, limits=PLAN_VALUE_LIMITS, python_carriers=True
    ).conformant:
        raise InvalidInputError("Safe-state proof exceeds aggregate plan limits")
    proofs = {ref: _safe_state_proof(index, value).model_dump(mode="json") for ref, value in inputs.items()}
    for binding in bindings:
        binding["state"] = binding["state"].model_dump(mode="json")
        binding["proofs"] = {ref: proofs[ref] for ref in binding["proofs"]}
    if not validate_realization_value(bindings, limits=PLAN_VALUE_LIMITS, python_carriers=True).conformant:
        raise InvalidInputError("Safe-state proof exceeds aggregate plan limits")
    return tuple(ResolvedSafeState.model_validate(binding) for binding in bindings)
