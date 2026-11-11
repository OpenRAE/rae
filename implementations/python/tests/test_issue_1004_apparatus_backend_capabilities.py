"""Issue #1004 adversarial-control apparatus and backend capability declarations.

These tests pin the declaration-only extension of the API-407
``capabilities.participant_runtime.feature_support`` surface with five governed
behavior-feature terms: SEM-233 boundary flow resolution, RUN-319 final-sink
mediation, bounded quarantined processing, trusted/untrusted processing-role
declaration, and monitor-topology declaration.

A declaration is never proof of realization, isolation, monitor independence,
non-collusion, flow propagation, or sink enforcement. Missing, contradictory, or
evidence-free declarations are deny-equivalent, and a weakened claim never
retains the stronger effective level without an explicitly authorized downgrade.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pytest
from raes_backend_protocols.capabilities import (
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    PARTICIPANT_RUNTIME_POLICY_FEATURES,
    BackendManifest,
    ParticipantFeatureSupport,
    resolve_participant_feature_support,
)
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.controlled_vocabularies import load_controlled_vocabulary_catalog
from raes_contracts.errors import ConflictError
from raes_contracts.manifest_authority import BACKEND_SUPPORTED_CONTRACT_IDS
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

# The five governed apparatus/backend declaration terms and their exact
# backend-facing required contracts (all already published in
# BACKEND_SUPPORTED_CONTRACT_IDS; no SDL/authoring ids are smuggled in).
ADVERSARIAL_CONTROL_FEATURE_CONTRACTS = {
    "participant_boundary_flow_resolution": frozenset(
        {"participant-flow-control-relation-v1", "participant-crossing-occurrence-v1"}
    ),
    "participant_final_sink_mediation": frozenset(
        {"participant-flow-control-relation-v1", "participant-crossing-occurrence-v1"}
    ),
    "participant_quarantined_processing": frozenset(
        {"participant-flow-control-relation-v1", "participant-crossing-occurrence-v1"}
    ),
    "participant_processing_role_trust": frozenset(
        {"participant-control-occurrence-v1", "participant-crossing-occurrence-v1"}
    ),
    "participant_monitor_topology": frozenset({"experiment-evidence-record-v1"}),
}

_EVIDENCE_REFS = ("evidence.issue-1004.sem-233-rev1.conformance.v1",)
_DISCLOSURE_REFS = ("disclosures.issue-1004.apparatus.v1",)
_LIMITATION_REFS = ("limitations.issue-1004.apparatus.v1",)
_CONSTRAINT_REFS = ("constraints.issue-1004.apparatus.v1",)


def _exact_declaration(feature: str) -> ParticipantFeatureSupport:
    return ParticipantFeatureSupport(
        feature=feature,
        support_level=ParticipantFeatureSupportLevel.EXACT,
        evidence_refs=_EVIDENCE_REFS,
    )


def _manifest_declaring(
    declaration: ParticipantFeatureSupport,
    *,
    extra_contracts: frozenset[str] | None = None,
    drop_contracts: frozenset[str] = frozenset(),
) -> BackendManifest:
    manifest = create_stub_manifest()
    assert manifest.participant_runtime is not None
    required = ADVERSARIAL_CONTROL_FEATURE_CONTRACTS[declaration.feature]
    contracts = (manifest.supported_contract_versions | required) - drop_contracts
    if extra_contracts:
        contracts = contracts | extra_contracts
    # The stub honestly declares every evidence-required feature UNSUPPORTED by
    # default; replace that entry with the declaration under test.
    others = tuple(
        entry for entry in manifest.participant_runtime.feature_support if entry.feature != declaration.feature
    )
    participant_runtime = replace(
        manifest.participant_runtime,
        supported_behavior_features=manifest.participant_runtime.supported_behavior_features | {declaration.feature},
        feature_support=others + (declaration,),
    )
    capabilities = replace(manifest.capabilities, participant_runtime=participant_runtime)
    return BackendManifest(
        identity=manifest.identity,
        supported_contract_versions=contracts,
        compatibility=manifest.compatibility,
        realization_support=manifest.realization_support,
        concept_bindings=manifest.concept_bindings,
        constraints=manifest.constraints,
        capabilities=capabilities,
    )


def test_governed_terms_registered_in_behavior_feature_vocabulary():
    catalog = load_controlled_vocabulary_catalog()
    terms = catalog.vocabularies["participant-runtime-behavior-features"].terms
    for feature in ADVERSARIAL_CONTROL_FEATURE_CONTRACTS:
        assert feature in terms, feature
        assert terms[feature].title
        assert terms[feature].description


def test_terms_are_evidence_required_but_not_runtime_policy_features():
    # Declaration-only: the terms carry the full evidence/disclosure discipline
    # (like participant_predicate_opacity) but do NOT join the runtime policy
    # enforcement set, which #1003/RUN-319 and the reference backend own.
    for feature in ADVERSARIAL_CONTROL_FEATURE_CONTRACTS:
        assert feature in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES, feature
        assert feature not in PARTICIPANT_RUNTIME_POLICY_FEATURES, feature


def test_required_contracts_map_uses_backend_facing_published_ids():
    behavior_map = PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE]
    for feature, expected in ADVERSARIAL_CONTROL_FEATURE_CONTRACTS.items():
        assert behavior_map[feature] == expected, feature
        assert expected <= set(BACKEND_SUPPORTED_CONTRACT_IDS), feature


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_positive_claim_requires_evidence(feature: str):
    # A positive (non-unsupported) claim needs conformance evidence.
    with pytest.raises(ValueError, match="evidence_refs"):
        ParticipantFeatureSupport(feature=feature, support_level=ParticipantFeatureSupportLevel.EXACT)


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_below_exact_requires_disclosure_and_limitation(feature: str):
    with pytest.raises(ValueError, match="disclosure_refs"):
        ParticipantFeatureSupport(
            feature=feature,
            support_level=ParticipantFeatureSupportLevel.DISCLOSED_WEAK,
            evidence_refs=_EVIDENCE_REFS,
        )
    with pytest.raises(ValueError, match="limitation_refs"):
        ParticipantFeatureSupport(
            feature=feature,
            support_level=ParticipantFeatureSupportLevel.DISCLOSED_WEAK,
            evidence_refs=_EVIDENCE_REFS,
            disclosure_refs=_DISCLOSURE_REFS,
        )


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_bounded_requires_constraints(feature: str):
    with pytest.raises(ValueError, match="constraint_refs"):
        ParticipantFeatureSupport(
            feature=feature,
            support_level=ParticipantFeatureSupportLevel.BOUNDED,
            evidence_refs=_EVIDENCE_REFS,
            disclosure_refs=_DISCLOSURE_REFS,
            limitation_refs=_LIMITATION_REFS,
        )


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_honest_exact_declaration_resolves(feature: str):
    manifest = _manifest_declaring(_exact_declaration(feature))
    resolved = resolve_participant_feature_support(manifest, feature)
    assert resolved is not None
    assert resolved.support_level == ParticipantFeatureSupportLevel.EXACT


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_overclaiming_without_required_contract_is_deny_equivalent(feature: str):
    required = ADVERSARIAL_CONTROL_FEATURE_CONTRACTS[feature]
    manifest = _manifest_declaring(_exact_declaration(feature), drop_contracts=required)
    with pytest.raises(ConflictError, match="missing required contracts"):
        resolve_participant_feature_support(manifest, feature)


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_owning_contract_is_required_beyond_generic_occurrence(feature: str):
    # The sharp regression: a generic occurrence/evidence contract alone must not
    # satisfy an exact claim. Dropping only the owning realization contract while
    # leaving the generic crossing/occurrence carrier present still denies.
    required = ADVERSARIAL_CONTROL_FEATURE_CONTRACTS[feature]
    owning = required - {"participant-crossing-occurrence-v1"}
    assert owning, feature  # every term binds an owning contract beyond the crossing carrier
    manifest = _manifest_declaring(_exact_declaration(feature), drop_contracts=owning)
    with pytest.raises(ConflictError, match="missing required contracts"):
        resolve_participant_feature_support(manifest, feature)


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_evidence_free_declaration_is_deny_equivalent(feature: str):
    # A term declared in supported_behavior_features with no feature_support
    # entry fails closed for an evidence-required feature.
    manifest = create_stub_manifest()
    assert manifest.participant_runtime is not None
    without = tuple(entry for entry in manifest.participant_runtime.feature_support if entry.feature != feature)
    with pytest.raises(ValueError, match="feature_support declarations"):
        replace(
            manifest.participant_runtime,
            supported_behavior_features=manifest.participant_runtime.supported_behavior_features | {feature},
            feature_support=without,
        )


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_unsupported_cannot_coappear_with_supported_feature(feature: str):
    # The stub already declares the feature UNSUPPORTED; listing it as a
    # supported behavior feature must fail closed rather than silently upgrade.
    manifest = create_stub_manifest()
    assert manifest.participant_runtime is not None
    with pytest.raises(ValueError, match="supported feature unsupported"):
        replace(
            manifest.participant_runtime,
            supported_behavior_features=manifest.participant_runtime.supported_behavior_features | {feature},
        )


@pytest.mark.parametrize("feature", sorted(ADVERSARIAL_CONTROL_FEATURE_CONTRACTS))
def test_weakened_claim_needs_authorized_downgrade(feature: str):
    bounded = ParticipantFeatureSupport(
        feature=feature,
        support_level=ParticipantFeatureSupportLevel.BOUNDED,
        evidence_refs=_EVIDENCE_REFS,
        disclosure_refs=_DISCLOSURE_REFS,
        limitation_refs=_LIMITATION_REFS,
        constraint_refs=_CONSTRAINT_REFS,
    )
    manifest = _manifest_declaring(bounded)

    # A bounded claim never satisfies a required exact level on its own.
    with pytest.raises(ConflictError, match="requires exact support"):
        resolve_participant_feature_support(manifest, feature, required_level=ParticipantFeatureSupportLevel.EXACT)

    # A downgrade requires explicit policy and provenance references.
    with pytest.raises(ConflictError, match="downgrade authorization"):
        resolve_participant_feature_support(
            manifest,
            feature,
            required_level=ParticipantFeatureSupportLevel.EXACT,
            allowed_downgrade_level=ParticipantFeatureSupportLevel.BOUNDED,
        )

    resolved = resolve_participant_feature_support(
        manifest,
        feature,
        required_level=ParticipantFeatureSupportLevel.EXACT,
        allowed_downgrade_level=ParticipantFeatureSupportLevel.BOUNDED,
        downgrade_policy_ref="policy.issue-1004.downgrade.v1",
        downgrade_provenance_ref="provenance.issue-1004.downgrade.v1",
    )
    # The resolved claim retains the weaker level; it never regains exact.
    assert resolved is not None
    assert resolved.support_level == ParticipantFeatureSupportLevel.BOUNDED


def test_monitor_topology_declaration_is_not_independence_or_non_collusion_evidence():
    # A monitor-topology declaration is bounded apparatus evidence only. Distinct
    # evidence references (standing in for distinct model/process identities) do
    # not upgrade the claim or certify independence / non-collusion; resolution
    # returns the plain declared support entry with no independence property.
    declaration = ParticipantFeatureSupport(
        feature="participant_monitor_topology",
        support_level=ParticipantFeatureSupportLevel.BOUNDED,
        evidence_refs=("evidence.monitor.alpha.v1", "evidence.monitor.beta.v1"),
        disclosure_refs=_DISCLOSURE_REFS,
        limitation_refs=("limitations.monitor.no-independence-claim.v1",),
        constraint_refs=_CONSTRAINT_REFS,
    )
    manifest = _manifest_declaring(declaration)
    resolved = resolve_participant_feature_support(
        manifest,
        "participant_monitor_topology",
        required_level=ParticipantFeatureSupportLevel.BOUNDED,
    )
    assert resolved is not None
    assert resolved.support_level == ParticipantFeatureSupportLevel.BOUNDED
    # The resolved declaration is a plain ParticipantFeatureSupport with the
    # fixed closed field set — no independence / non-collusion coordinate exists
    # for the resolver to fabricate. This fails if a future field like
    # `independent` or `non_collusion` is added to the declaration model.
    assert {field.name for field in fields(resolved)} == {
        "feature",
        "support_level",
        "constraint_refs",
        "limitation_refs",
        "disclosure_refs",
        "evidence_refs",
    }
