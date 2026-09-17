"""Issue #1203 recursive realization-constraint normal form."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.bounded_domains import EnumDomain, GovernedReferenceDomain, NullDomain
from raes_contracts.contracts import schema_bundle
from raes_contracts.realization_structure import (
    ExactRealizationValue,
    OpenRealizationValue,
    RealizationAllOf,
    RealizationClosure,
    RealizationCollection,
    RealizationCollectionMember,
    RealizationCollectionProfile,
    RealizationConstraintDocument,
    RealizationConstraintLimits,
    RealizationDefinitionReference,
    RealizationDelegatedValue,
    RealizationDomainValue,
    RealizationGraphReference,
    RealizationIdentityAlias,
    RealizationKeyedCollectionConstraint,
    RealizationKnowledgeValue,
    RealizationLiteral,
    RealizationNormalizationMetadata,
    RealizationRecord,
    RealizationRecordConstraint,
    RealizationRelationStatus,
    RealizationScope,
    RealizationSequenceConstraint,
    compose_realization_constraints,
    downgrade_recursive_realization_structure,
    evaluate_realization_constraint,
    normalize_realization_literal,
    realization_constraint_refines,
    realization_member_identity,
    structure_matches,
    upgrade_legacy_realization_structure,
)


def _closed() -> RealizationClosure:
    return RealizationClosure(
        posture="closed",
        universe="scenario-fields/v1",
        profile="raes-recursive-realization/v1",
    )


def test_inherited_open_scope_preserves_exact_descendants_and_closed_siblings() -> None:
    rule = RealizationConstraintDocument(
        semantic_profile="raes-recursive-realization/v1",
        default_closure=_closed(),
        scopes=(
            RealizationScope(
                field_pointer="/nodes/host/runtime",
                closure=RealizationClosure(
                    posture="open",
                    universe="node-runtime/v1",
                    profile="raes-recursive-realization/v1",
                ),
            ),
        ),
        root=RealizationRecordConstraint(
            kind="recursive-record",
            fields={
                "nodes": RealizationRecordConstraint(
                    kind="recursive-record",
                    fields={
                        "host": RealizationRecordConstraint(
                            kind="recursive-record",
                            fields={
                                "runtime": RealizationRecordConstraint(
                                    kind="recursive-record",
                                    fields={
                                        "kernel": RealizationLiteral(kind="literal", value="6.12"),
                                        "security": RealizationRecordConstraint(
                                            kind="recursive-record",
                                            closure=_closed(),
                                            fields={"selinux": RealizationLiteral(kind="literal", value=True)},
                                        ),
                                    },
                                )
                            },
                        )
                    },
                )
            },
        ),
    )

    conforming = {
        "nodes": {
            "host": {
                "runtime": {
                    "kernel": "6.12",
                    "backend_extension": {"choice": "delegated"},
                    "security": {"selinux": True},
                }
            }
        }
    }
    assert evaluate_realization_constraint(rule, conforming).status is RealizationRelationStatus.CONFORMANT

    wrong_exact = conforming | {
        "nodes": {
            "host": {
                "runtime": {
                    **conforming["nodes"]["host"]["runtime"],
                    "kernel": "6.11",
                }
            }
        }
    }
    assert evaluate_realization_constraint(rule, wrong_exact).status is RealizationRelationStatus.NONCONFORMANT

    closed_child_extra = conforming | {
        "nodes": {
            "host": {
                "runtime": {
                    **conforming["nodes"]["host"]["runtime"],
                    "security": {"selinux": True, "unconfined": True},
                }
            }
        }
    }
    assert evaluate_realization_constraint(rule, closed_child_extra).status is RealizationRelationStatus.NONCONFORMANT


def test_presence_null_empty_and_unknown_are_independent() -> None:
    rule = RealizationConstraintDocument(
        semantic_profile="raes-recursive-realization/v1",
        default_closure=_closed(),
        root=RealizationRecordConstraint(
            kind="recursive-record",
            fields={
                "required_null": RealizationLiteral(kind="literal", value=None),
                "optional_empty": RealizationLiteral(kind="literal", value="", presence="optional"),
                "forbidden": RealizationLiteral(kind="literal", value="unused", presence="forbidden"),
                "knowledge": RealizationKnowledgeValue(kind="knowledge", state="unknown"),
            },
        ),
    )

    unresolved = evaluate_realization_constraint(rule, {"required_null": None, "knowledge": "anything"})
    assert unresolved.status is RealizationRelationStatus.UNRESOLVED
    assert (
        evaluate_realization_constraint(rule, {"required_null": ""}).status is RealizationRelationStatus.NONCONFORMANT
    )
    assert (
        evaluate_realization_constraint(rule, {"required_null": None, "forbidden": "unused"}).status
        is RealizationRelationStatus.NONCONFORMANT
    )


def _package_rule(*, additional: bool = True) -> RealizationConstraintDocument:
    posture = "open" if additional else "closed"
    collection_closure = RealizationClosure(
        posture=posture,
        universe="modeled-software/v1",
        profile="raes-recursive-realization/v1",
    )
    package = RealizationRecordConstraint(
        kind="recursive-record",
        presence="optional",
        closure=RealizationClosure(
            posture="open",
            universe="software-component-fields/v1",
            profile="raes-recursive-realization/v1",
        ),
        fields={
            "manager": RealizationLiteral(kind="literal", value="apt"),
            "name": RealizationLiteral(kind="literal", value="nmap"),
            "version": RealizationLiteral(kind="literal", value="7.95"),
            "repository": RealizationDomainValue(kind="domain", domain=NullDomain(), presence="optional"),
        },
    )
    return RealizationConstraintDocument(
        semantic_profile="raes-recursive-realization/v1",
        default_closure=_closed(),
        root=RealizationKeyedCollectionConstraint(
            kind="keyed-collection",
            collection_kind="runtime-packages",
            identity_fields=("manager", "name"),
            closure=collection_closure,
            members=(RealizationCollectionMember(identity=("apt", "nmap"), constraint=package),),
        ),
    )


def test_optional_keyed_member_is_absent_or_present_and_conforming() -> None:
    rule = _package_rule()
    assert evaluate_realization_constraint(rule, []).status is RealizationRelationStatus.CONFORMANT
    assert (
        evaluate_realization_constraint(
            rule,
            [{"manager": "apt", "name": "curl", "version": "8"}],
        ).status
        is RealizationRelationStatus.CONFORMANT
    )
    assert (
        evaluate_realization_constraint(
            rule,
            [
                {"manager": "apt", "name": "curl", "version": "8"},
                {"manager": "apt", "name": "nmap", "version": "7.95", "repository": None},
            ],
        ).status
        is RealizationRelationStatus.CONFORMANT
    )
    assert (
        evaluate_realization_constraint(
            rule,
            [{"manager": "apt", "name": "nmap", "version": "7.94"}],
        ).status
        is RealizationRelationStatus.NONCONFORMANT
    )


def test_keyed_collection_reorders_but_rejects_duplicates_ambiguity_and_closed_extras() -> None:
    required = _package_rule().model_copy(
        update={
            "root": _package_rule().root.model_copy(
                update={
                    "members": (
                        RealizationCollectionMember(
                            identity=("apt", "nmap"),
                            constraint=_package_rule()
                            .root.members[0]
                            .constraint.model_copy(update={"presence": "required"}),
                        ),
                    )
                }
            )
        }
    )
    reordered = [
        {"manager": "apt", "name": "curl", "version": "8"},
        {"manager": "apt", "name": "nmap", "version": "7.95"},
    ]
    assert evaluate_realization_constraint(required, reordered).status is RealizationRelationStatus.CONFORMANT
    duplicate = [reordered[1], reordered[1]]
    assert evaluate_realization_constraint(required, duplicate).status is RealizationRelationStatus.INVALID
    assert (
        evaluate_realization_constraint(required, [{"manager": "apt", "version": "7.95"}]).status
        is RealizationRelationStatus.INVALID
    )
    assert (
        evaluate_realization_constraint(_package_rule(additional=False), reordered).status
        is RealizationRelationStatus.NONCONFORMANT
    )


def test_keyed_collection_aliases_are_explicit_and_collision_free() -> None:
    base = _package_rule()
    root = base.root.model_copy(
        update={"aliases": (RealizationIdentityAlias(identity=("debian", "nmap"), target=("apt", "nmap")),)}
    )
    aliased = base.model_copy(update={"root": root})
    assert evaluate_realization_constraint(
        aliased,
        [{"manager": "debian", "name": "nmap", "version": "7.95"}],
    ).conformant

    colliding_alias = RealizationIdentityAlias(identity=("apt", "nmap"), target=("apt", "nmap"))
    with pytest.raises(ValueError, match="alias identities must not collide"):
        RealizationKeyedCollectionConstraint(
            kind="keyed-collection",
            collection_kind=root.collection_kind,
            identity_fields=root.identity_fields,
            members=root.members,
            closure=root.closure,
            aliases=(colliding_alias,),
        )


def test_ordered_sequences_preserve_order_and_permitted_duplicates() -> None:
    rule = RealizationConstraintDocument(
        semantic_profile="raes-recursive-realization/v1",
        default_closure=_closed(),
        root=RealizationSequenceConstraint(
            kind="sequence",
            closure=RealizationClosure(
                posture="closed",
                universe="declared-actions/v1",
                profile="raes-recursive-realization/v1",
            ),
            items=(
                RealizationLiteral(kind="literal", value="send"),
                RealizationLiteral(kind="literal", value="send"),
                RealizationLiteral(kind="literal", value="receive"),
            ),
        ),
    )
    assert evaluate_realization_constraint(rule, ["send", "send", "receive"]).conformant
    assert (
        evaluate_realization_constraint(rule, ["send", "receive", "send"]).status
        is RealizationRelationStatus.NONCONFORMANT
    )


def _document(root, **changes) -> RealizationConstraintDocument:
    values = {
        "semantic_profile": "raes-recursive-realization/v1",
        "default_closure": _closed(),
        "root": root,
        **changes,
    }
    return RealizationConstraintDocument(**values)


def test_constraint_definition_references_are_bounded_and_acyclic() -> None:
    literal = RealizationLiteral(kind="literal", value="linux")
    direct = _document(
        RealizationDefinitionReference(kind="definition-reference", target="os"),
        definitions={"os": literal},
    )
    assert evaluate_realization_constraint(direct, "linux").conformant

    missing = _document(RealizationDefinitionReference(kind="definition-reference", target="missing"))
    assert evaluate_realization_constraint(missing, "linux").status is RealizationRelationStatus.INVALID

    cyclic = _document(
        RealizationDefinitionReference(kind="definition-reference", target="a"),
        definitions={
            "a": RealizationDefinitionReference(kind="definition-reference", target="b"),
            "b": RealizationDefinitionReference(kind="definition-reference", target="a"),
        },
    )
    assert evaluate_realization_constraint(cyclic, "linux").status is RealizationRelationStatus.INVALID

    hops = evaluate_realization_constraint(
        cyclic,
        "linux",
        limits=RealizationConstraintLimits(max_reference_hops=1),
    )
    assert hops.status is RealizationRelationStatus.LIMIT_EXCEEDED


def test_graph_references_are_identity_edges_with_explicit_cycle_policy() -> None:
    peer = RealizationGraphReference(
        kind="graph-reference",
        domain=GovernedReferenceDomain(authority="scenario-nodes/v1", allowed_refs=["a", "b"]),
        cycle_policy="allow",
    )
    rule = _document(
        RealizationRecordConstraint(
            kind="recursive-record",
            fields={
                "a": RealizationRecordConstraint(kind="recursive-record", fields={"peer": peer}),
                "b": RealizationRecordConstraint(kind="recursive-record", fields={"peer": peer}),
            },
        )
    )
    assert evaluate_realization_constraint(rule, {"a": {"peer": "b"}, "b": {"peer": "a"}}).conformant
    assert (
        evaluate_realization_constraint(rule, {"a": {"peer": "c"}, "b": {"peer": "a"}}).status
        is RealizationRelationStatus.NONCONFORMANT
    )
    assert rule.model_validate_json(rule.model_dump_json()) == rule


def test_relation_limits_are_explicit_and_diagnostics_are_bounded() -> None:
    nested = RealizationLiteral(kind="literal", value="leaf")
    for index in range(4):
        nested = RealizationRecordConstraint(kind="recursive-record", fields={f"level-{index}": nested})
    depth_result = evaluate_realization_constraint(
        _document(nested),
        {"level-3": {"level-2": {"level-1": {"level-0": "leaf"}}}},
        limits=RealizationConstraintLimits(max_depth=2),
    )
    assert depth_result.status is RealizationRelationStatus.LIMIT_EXCEEDED
    assert depth_result.conformant is False
    assert depth_result.diagnostics[0].code == "realization.limit-exceeded"

    scalar_result = evaluate_realization_constraint(
        _document(RealizationDelegatedValue(kind="delegated")),
        "oversized",
        limits=RealizationConstraintLimits(max_scalar_bytes=4),
    )
    assert scalar_result.status is RealizationRelationStatus.LIMIT_EXCEEDED
    assert len(scalar_result.diagnostics) == 1

    assert (
        evaluate_realization_constraint(_document(RealizationDelegatedValue(kind="delegated")), math.nan).status
        is RealizationRelationStatus.INVALID
    )
    assert (
        normalize_realization_literal(
            math.inf,
            semantic_profile="raes-recursive-realization/v1",
            default_closure=_closed(),
        ).status
        is RealizationRelationStatus.INVALID
    )
    missing = _document(
        RealizationRecordConstraint(
            kind="recursive-record",
            fields={name: RealizationLiteral(kind="literal", value=name) for name in ("first", "second", "third")},
        )
    )
    bounded_diagnostics = evaluate_realization_constraint(
        missing,
        {},
        limits=RealizationConstraintLimits(max_diagnostics=2),
    )
    assert len(bounded_diagnostics.diagnostics) == 2


def test_limits_admit_optional_constraints_and_profiled_identity_work() -> None:
    optional_fields = RealizationRecordConstraint(
        kind="recursive-record",
        fields={
            f"optional-{index}": RealizationLiteral(kind="literal", value=index, presence="optional")
            for index in range(4)
        },
    )
    assert (
        evaluate_realization_constraint(
            _document(optional_fields),
            {},
            limits=RealizationConstraintLimits(max_nodes=2),
        ).status
        is RealizationRelationStatus.LIMIT_EXCEEDED
    )

    normalized = normalize_realization_literal(
        {"packages": [{"id": "a"}, {"id": "b"}]},
        semantic_profile="x-example:recursive/v1",
        default_closure=_closed(),
        limits=RealizationConstraintLimits(max_identity_checks=1),
        metadata=RealizationNormalizationMetadata(
            collection_profiles=(
                RealizationCollectionProfile(
                    field_pointer="/packages",
                    collection_kind="packages",
                    identity_fields=("id",),
                    closure=_closed(),
                ),
            ),
        ),
    )
    assert normalized.status is RealizationRelationStatus.LIMIT_EXCEEDED

    metadata_heavy = _document(
        RealizationDomainValue(
            kind="domain",
            domain=EnumDomain(values=[f"value-{index}" for index in range(32)]),
        )
    )
    assert (
        evaluate_realization_constraint(
            metadata_heavy,
            "value-0",
            limits=RealizationConstraintLimits(max_operations=32),
        ).status
        is RealizationRelationStatus.LIMIT_EXCEEDED
    )

    aliased = _package_rule().model_copy(
        update={
            "root": _package_rule().root.model_copy(
                update={
                    "aliases": (
                        RealizationIdentityAlias(
                            identity=("debian", "nmap"),
                            target=("apt", "nmap"),
                        ),
                    )
                }
            )
        }
    )
    assert (
        evaluate_realization_constraint(
            aliased,
            [{"manager": "debian", "name": "nmap", "version": "7.95"}],
            limits=RealizationConstraintLimits(max_identity_checks=2),
        ).status
        is RealizationRelationStatus.LIMIT_EXCEEDED
    )


def test_scopes_apply_below_unmaterialized_delegated_and_keyed_children() -> None:
    closed_runtime = RealizationScope(field_pointer="/runtime", closure=_closed())
    unmaterialized = _document(
        RealizationRecordConstraint(kind="recursive-record", fields={}),
        default_closure=RealizationClosure(
            posture="open",
            universe="scenario-fields/v1",
            profile="raes-recursive-realization/v1",
        ),
        scopes=(closed_runtime,),
    )
    assert evaluate_realization_constraint(unmaterialized, {"runtime": {}}).conformant
    assert (
        evaluate_realization_constraint(unmaterialized, {"runtime": {"extra": 1}}).status
        is RealizationRelationStatus.NONCONFORMANT
    )
    nested_open = unmaterialized.model_copy(
        update={
            "scopes": (
                closed_runtime,
                RealizationScope(
                    field_pointer="/runtime/extensions",
                    closure=RealizationClosure(
                        posture="open",
                        universe="runtime-extensions/v1",
                        profile="raes-recursive-realization/v1",
                    ),
                ),
            )
        }
    )
    assert evaluate_realization_constraint(
        nested_open,
        {"runtime": {"extensions": {"backend": "permitted"}}},
    ).conformant

    delegated = _document(
        RealizationRecordConstraint(
            kind="recursive-record",
            fields={"runtime": RealizationDelegatedValue(kind="delegated")},
        ),
        scopes=(RealizationScope(field_pointer="/runtime/security", closure=_closed()),),
    )
    assert (
        evaluate_realization_constraint(delegated, {"runtime": {"security": {"extra": True}}}).status
        is RealizationRelationStatus.NONCONFORMANT
    )

    member = {"id": "extra", "settings": {"extra": True}}
    digest = realization_member_identity(member, ("id",))
    assert digest is not None
    keyed = _document(
        RealizationKeyedCollectionConstraint(
            kind="keyed-collection",
            collection_kind="nodes",
            identity_fields=("id",),
            members=(),
            closure=RealizationClosure(
                posture="open",
                universe="scenario-nodes/v1",
                profile="raes-recursive-realization/v1",
            ),
        ),
        scopes=(RealizationScope(field_pointer=f"/@{digest}/settings", closure=_closed()),),
    )
    assert evaluate_realization_constraint(keyed, [member]).status is RealizationRelationStatus.NONCONFORMANT

    sequence = _document(
        RealizationSequenceConstraint(
            kind="sequence",
            items=(),
            closure=RealizationClosure(
                posture="open",
                universe="actions/v1",
                profile="raes-recursive-realization/v1",
            ),
        ),
        scopes=(RealizationScope(field_pointer="/0", closure=_closed()),),
    )
    assert evaluate_realization_constraint(sequence, [{}]).conformant
    assert (
        evaluate_realization_constraint(sequence, [{"extra": True}]).status is RealizationRelationStatus.NONCONFORMANT
    )


def test_literal_normalization_preserves_null_empty_and_origin_round_trip() -> None:
    normalized = normalize_realization_literal(
        {"null": None, "empty-record": {}, "empty-sequence": [], "defaulted": 3},
        semantic_profile="x-example:recursive/v1",
        default_closure=_closed(),
        metadata=RealizationNormalizationMetadata(
            origins={"/defaulted": "default"},
        ),
    )
    assert normalized.status is RealizationRelationStatus.CONFORMANT
    assert normalized.document is not None
    fields = normalized.document.root.fields
    assert fields["null"] == RealizationLiteral(kind="literal", value=None)
    assert isinstance(fields["empty-record"], RealizationRecordConstraint)
    assert isinstance(fields["empty-sequence"], RealizationSequenceConstraint)
    assert fields["defaulted"].origin.value == "default"
    assert normalized.document.model_validate_json(normalized.document.model_dump_json()) == normalized.document


def test_profile_driven_literal_normalization_uses_stable_collection_identity() -> None:
    collection = RealizationCollectionProfile(
        field_pointer="/packages",
        collection_kind="runtime-packages",
        identity_fields=("manager", "name"),
        closure=RealizationClosure(
            posture="closed",
            universe="modeled-software/v1",
            profile="x-example:recursive/v1",
        ),
    )
    normalized = normalize_realization_literal(
        {
            "packages": [
                {"manager": "apt", "name": "nmap", "version": "7.95", "x-acme:channel": "private"},
                {"manager": "apt", "name": "curl", "version": "8"},
            ]
        },
        semantic_profile="x-example:recursive/v1",
        default_closure=_closed(),
        metadata=RealizationNormalizationMetadata(
            scopes=(
                RealizationScope(
                    field_pointer="/packages",
                    closure=RealizationClosure(
                        posture="open",
                        universe="software-component-fields/v1",
                        profile="x-example:recursive/v1",
                    ),
                ),
            ),
            collection_profiles=(collection,),
        ),
    )
    assert normalized.document is not None
    packages = normalized.document.root.fields["packages"]
    assert isinstance(packages, RealizationKeyedCollectionConstraint)
    actual = {
        "packages": [
            {"manager": "apt", "name": "curl", "version": "8"},
            {"manager": "apt", "name": "nmap", "version": "7.95", "x-acme:channel": "private"},
        ]
    }
    assert evaluate_realization_constraint(normalized.document, actual).conformant


def test_positional_author_scope_normalizes_to_semantic_member_identity() -> None:
    profile = "x-example:recursive/v1"
    normalized = normalize_realization_literal(
        {
            "packages": [
                {"manager": "apt", "name": "nmap", "version": "7.95"},
                {"manager": "apt", "name": "curl", "version": "8"},
            ]
        },
        semantic_profile=profile,
        default_closure=_closed(),
        metadata=RealizationNormalizationMetadata(
            scopes=(
                RealizationScope(
                    field_pointer="/packages",
                    closure=RealizationClosure(posture="open", universe="software-fields/v1", profile=profile),
                ),
                RealizationScope(
                    field_pointer="/packages/0",
                    closure=RealizationClosure(posture="closed", universe="software-fields/v1", profile=profile),
                ),
            ),
            collection_profiles=(
                RealizationCollectionProfile(
                    field_pointer="/packages",
                    collection_kind="runtime-packages",
                    identity_fields=("manager", "name"),
                    closure=RealizationClosure(posture="closed", universe="modeled-software/v1", profile=profile),
                ),
            ),
        ),
    )
    assert normalized.document is not None
    assert all("/0" not in scope.field_pointer for scope in normalized.document.scopes)
    reordered = {
        "packages": [
            {"manager": "apt", "name": "curl", "version": "8", "backend": "delegated"},
            {"manager": "apt", "name": "nmap", "version": "7.95"},
        ]
    }
    assert evaluate_realization_constraint(normalized.document, reordered).conformant
    reordered["packages"][1]["backend"] = "must-not-widen-nmap"
    assert (
        evaluate_realization_constraint(normalized.document, reordered).status
        is RealizationRelationStatus.NONCONFORMANT
    )


def test_nested_keyed_metadata_uses_source_addresses_and_semantic_output_addresses() -> None:
    profile = "x-example:recursive/v1"
    value = {
        "nodes": [
            {
                "name": "host",
                "version": "2026.3",
                "packages": [
                    {"manager": "apt", "name": "nmap", "version": "7.95"},
                    {"manager": "apt", "name": "curl", "version": "8"},
                ],
            }
        ]
    }
    normalized = normalize_realization_literal(
        value,
        semantic_profile=profile,
        default_closure=_closed(),
        metadata=RealizationNormalizationMetadata(
            origins={"/nodes/0/version": "backend"},
            scopes=(RealizationScope(field_pointer="/nodes/0/packages/0", closure=_closed()),),
            collection_profiles=(
                RealizationCollectionProfile(
                    field_pointer="/nodes",
                    collection_kind="nodes",
                    identity_fields=("name",),
                    closure=_closed(),
                ),
                RealizationCollectionProfile(
                    field_pointer="/nodes/0/packages",
                    collection_kind="runtime-packages",
                    identity_fields=("manager", "name"),
                    closure=_closed(),
                ),
            ),
        ),
    )
    assert normalized.document is not None
    nodes = normalized.document.root.fields["nodes"]
    assert isinstance(nodes, RealizationKeyedCollectionConstraint)
    host = nodes.members[0].constraint
    assert isinstance(host, RealizationRecordConstraint)
    assert host.fields["version"].origin.value == "backend"
    assert isinstance(host.fields["packages"], RealizationKeyedCollectionConstraint)
    assert all("/0" not in scope.field_pointer for scope in normalized.document.scopes)

    reordered = {
        "nodes": [
            {
                "name": "host",
                "version": "2026.3",
                "packages": [
                    {"manager": "apt", "name": "curl", "version": "8"},
                    {"manager": "apt", "name": "nmap", "version": "7.95"},
                ],
            }
        ]
    }
    assert evaluate_realization_constraint(normalized.document, reordered).conformant
    reordered["nodes"][0]["packages"][1]["extra"] = True
    assert (
        evaluate_realization_constraint(normalized.document, reordered).status
        is RealizationRelationStatus.NONCONFORMANT
    )


def test_five_linux_nodes_and_kali_refinement_use_one_open_descendant_scope() -> None:
    nodes = {
        f"linux-{index}": RealizationRecordConstraint(
            kind="recursive-record",
            fields={"os": RealizationLiteral(kind="literal", value="linux")},
        )
        for index in range(5)
    }
    rule = _document(
        RealizationRecordConstraint(
            kind="recursive-record",
            fields={
                "nodes": RealizationRecordConstraint(
                    kind="recursive-record",
                    closure=RealizationClosure(
                        posture="closed",
                        universe="scenario-nodes/v1",
                        profile="raes-recursive-realization/v1",
                    ),
                    fields=nodes,
                )
            },
        ),
        scopes=(
            RealizationScope(
                field_pointer="/nodes",
                closure=RealizationClosure(
                    posture="open",
                    universe="node-realization-fields/v1",
                    profile="raes-recursive-realization/v1",
                ),
            ),
        ),
    )
    actual = {
        "nodes": {
            f"linux-{index}": {
                "os": "linux",
                "distribution": "kali" if index == 0 else "debian",
                **({"release": "2026.3", "packages": [{"name": "nmap", "version": "7.95"}]} if index == 0 else {}),
            }
            for index in range(5)
        }
    }
    assert evaluate_realization_constraint(rule, actual).conformant
    actual["nodes"]["linux-extra"] = {"os": "linux"}
    assert evaluate_realization_constraint(rule, actual).status is RealizationRelationStatus.NONCONFORMANT
    del actual["nodes"]["linux-extra"]
    actual["nodes"]["linux-0"]["os"] = "windows"
    assert evaluate_realization_constraint(rule, actual).status is RealizationRelationStatus.NONCONFORMANT

    scope = (
        RealizationScope(
            field_pointer="/nodes/kali",
            closure=RealizationClosure(
                posture="open",
                universe="node-realization-fields/v1",
                profile="raes-recursive-realization/v1",
            ),
        ),
    )
    ladder = (
        {"os": "linux", "distribution": "kali"},
        {"os": "linux", "distribution": "kali", "nmap_version": "7.95"},
        {
            "os": "linux",
            "distribution": "kali",
            "release": "2026.3",
            "nmap_version": "7.95",
            "configuration": "hardened",
        },
    )
    for exact_fields in ladder:
        kali_rule = _document(
            RealizationRecordConstraint(
                kind="recursive-record",
                fields={
                    "nodes": RealizationRecordConstraint(
                        kind="recursive-record",
                        closure=RealizationClosure(
                            posture="closed",
                            universe="scenario-nodes/v1",
                            profile="raes-recursive-realization/v1",
                        ),
                        fields={
                            "kali": RealizationRecordConstraint(
                                kind="recursive-record",
                                fields={
                                    key: RealizationLiteral(kind="literal", value=value)
                                    for key, value in exact_fields.items()
                                },
                            )
                        },
                    )
                },
            ),
            scopes=scope,
        )
        candidate = {"nodes": {"kali": {**exact_fields, "backend_owned": "permitted"}}}
        assert evaluate_realization_constraint(kali_rule, candidate).conformant
        candidate["nodes"]["kali"]["distribution"] = "debian"
        assert evaluate_realization_constraint(kali_rule, candidate).status is RealizationRelationStatus.NONCONFORMANT


def test_complete_abstract_model_does_not_gain_concrete_machine_or_observation_detail() -> None:
    abstract = {
        "computers": {
            "a": {"actions": ["increment", "send", "receive"]},
            "b": {"actions": ["increment", "send", "receive"]},
        },
        "links": {"mailbox": {"source": "a", "target": "b"}},
    }
    normalized = normalize_realization_literal(
        abstract,
        semantic_profile="abstract-transition-system/v1",
        default_closure=RealizationClosure(
            posture="open",
            universe="abstract-model/v1",
            profile="abstract-transition-system/v1",
        ),
    )
    assert normalized.document is not None
    serialized = normalized.document.model_dump_json()
    assert all(term not in serialized for term in ("operating_system", "image", "packages", "observation"))
    assert evaluate_realization_constraint(normalized.document, abstract).conformant


def test_conjunction_is_canonical_and_refinement_is_transitive() -> None:
    exact = _document(RealizationLiteral(kind="literal", value=2))
    bounded = _document(RealizationDomainValue(kind="domain", domain=EnumDomain(values=[1, 2, 3])))
    delegated = _document(RealizationDelegatedValue(kind="delegated"))

    left = compose_realization_constraints(exact, bounded)
    right = compose_realization_constraints(bounded, exact)
    assert left.status is RealizationRelationStatus.CONFORMANT
    assert left.document == right.document == exact
    assert compose_realization_constraints(exact, exact).document == exact

    grouped_left = compose_realization_constraints(compose_realization_constraints(exact, bounded).document, delegated)
    grouped_right = compose_realization_constraints(exact, compose_realization_constraints(bounded, delegated).document)
    assert grouped_left.document == grouped_right.document == exact
    assert realization_constraint_refines(exact, bounded).conformant
    assert realization_constraint_refines(bounded, delegated).conformant
    assert realization_constraint_refines(exact, delegated).conformant

    conflict = compose_realization_constraints(
        _document(RealizationLiteral(kind="literal", value=True)),
        _document(RealizationLiteral(kind="literal", value=1)),
    )
    assert conflict.status is RealizationRelationStatus.NONCONFORMANT
    assert conflict.document is None

    conjunction = _document(
        RealizationAllOf(
            kind="all-of",
            constraints=(
                RealizationDomainValue(kind="domain", domain=EnumDomain(values=[1, 2])),
                RealizationDomainValue(kind="domain", domain=EnumDomain(values=[2, 3])),
            ),
        )
    )
    assert evaluate_realization_constraint(conjunction, 2).conformant
    assert evaluate_realization_constraint(conjunction, 1).status is RealizationRelationStatus.NONCONFORMANT

    authored = _document(RealizationLiteral(kind="literal", value="linux", origin="author"))
    defaulted = _document(RealizationLiteral(kind="literal", value="linux", origin="default"))
    authored_defaulted = compose_realization_constraints(authored, defaulted)
    defaulted_authored = compose_realization_constraints(defaulted, authored)
    assert authored_defaulted.document == defaulted_authored.document
    assert isinstance(authored_defaulted.document.root, RealizationAllOf)
    assert {constraint.origin.value for constraint in authored_defaulted.document.root.constraints} == {
        "author",
        "default",
    }
    assert (
        compose_realization_constraints(
            exact,
            bounded,
            limits=RealizationConstraintLimits(max_nodes=1),
        ).status
        is RealizationRelationStatus.LIMIT_EXCEEDED
    )


def test_conjunction_intersects_and_preserves_presence() -> None:
    optional_left = _document(
        RealizationDomainValue(
            kind="domain",
            domain=EnumDomain(values=[1, 2]),
            presence="optional",
        )
    )
    optional_right = _document(
        RealizationDomainValue(
            kind="domain",
            domain=EnumDomain(values=[2, 3]),
            presence="optional",
        )
    )
    optional = compose_realization_constraints(optional_left, optional_right)
    assert optional.document is not None
    assert optional.document.root.presence.value == "optional"

    required = _document(RealizationDomainValue(kind="domain", domain=EnumDomain(values=[2, 3])))
    required_optional = compose_realization_constraints(required, optional_left)
    assert required_optional.document is not None
    assert required_optional.document.root.presence.value == "required"

    forbidden = _document(RealizationLiteral(kind="literal", value=9, presence="forbidden"))
    forbidden_optional = compose_realization_constraints(forbidden, optional_left)
    assert forbidden_optional.document is not None
    assert forbidden_optional.document.root.presence.value == "forbidden"
    assert compose_realization_constraints(forbidden, required).status is RealizationRelationStatus.NONCONFORMANT

    grouped_left = compose_realization_constraints(optional.document, optional_left)
    grouped_right = compose_realization_constraints(
        optional_left,
        compose_realization_constraints(optional_right, optional_left).document,
    )
    assert grouped_left.document == grouped_right.document
    assert grouped_left.document is not None
    assert grouped_left.document.root.presence.value == "optional"

    optional_member = _document(
        RealizationRecordConstraint(
            kind="recursive-record",
            fields={"value": optional.document.root},
        )
    )
    assert evaluate_realization_constraint(optional_member, {}).conformant
    forbidden_member = _document(
        RealizationRecordConstraint(
            kind="recursive-record",
            fields={"value": forbidden_optional.document.root},
        )
    )
    assert evaluate_realization_constraint(forbidden_member, {}).conformant
    assert (
        evaluate_realization_constraint(forbidden_member, {"value": 9}).status
        is RealizationRelationStatus.NONCONFORMANT
    )


def test_existing_realization_structure_is_a_lossless_compatibility_subset() -> None:
    expected = [{"id": "nmap", "version": "7.95", "repository": None}]
    from raes_contracts.realization_structure import realization_member_identity

    identity = realization_member_identity(expected[0], ("id",))
    assert identity is not None
    legacy = RealizationCollection(
        kind="collection",
        identity_fields=("id",),
        additional=True,
        members={
            identity: RealizationRecord(
                kind="record",
                additional=True,
                fields={
                    "id": ExactRealizationValue(kind="exact"),
                    "version": ExactRealizationValue(kind="exact"),
                    "repository": OpenRealizationValue(kind="open"),
                },
            )
        },
    )
    upgraded = upgrade_legacy_realization_structure(
        legacy,
        expected,
        semantic_profile="raes-recursive-realization/v1",
    )
    assert upgraded.status is RealizationRelationStatus.CONFORMANT
    assert upgraded.document is not None
    alternatives = (
        expected,
        [{"id": "nmap", "version": "7.95", "repository": "private"}],
        [{"id": "nmap", "version": "7.94", "repository": "private"}],
        [{"id": "nmap", "version": "7.95"}],
        [*expected, {"id": "curl", "version": "8"}],
    )
    for alternative in alternatives:
        assert (
            structure_matches(legacy, expected, alternative)
            is evaluate_realization_constraint(
                upgraded.document,
                alternative,
            ).conformant
        )
    downgraded = downgrade_recursive_realization_structure(upgraded.document, expected)
    assert downgraded.status is RealizationRelationStatus.CONFORMANT
    assert downgraded.structure == legacy
    assert downgraded.structure is not None
    for alternative in alternatives:
        assert evaluate_realization_constraint(upgraded.document, alternative).conformant is structure_matches(
            downgraded.structure,
            expected,
            alternative,
        )


def test_compatibility_rejects_semantically_lossy_shapes() -> None:
    taxonomy = upgrade_legacy_realization_structure(
        OpenRealizationValue(kind="open", taxonomy_sentinel=True),
        "linux",
        semantic_profile="raes-recursive-realization/v1",
    )
    assert taxonomy.status is RealizationRelationStatus.UNSUPPORTED

    unbound_closed_record = upgrade_legacy_realization_structure(
        RealizationRecord(
            kind="record",
            fields={"id": ExactRealizationValue(kind="exact")},
            additional=False,
        ),
        {"id": "host", "defaulted": True},
        semantic_profile="raes-recursive-realization/v1",
    )
    assert unbound_closed_record.status is RealizationRelationStatus.UNSUPPORTED

    suffixed = upgrade_legacy_realization_structure(
        RealizationRecord(
            kind="record",
            fields={"enabled_present": ExactRealizationValue(kind="exact")},
            additional=True,
        ),
        {"enabled": True},
        semantic_profile="raes-recursive-realization/v1",
    )
    assert suffixed.status is RealizationRelationStatus.UNSUPPORTED

    open_sequence = _document(
        RealizationSequenceConstraint(
            kind="sequence",
            items=(),
            closure=RealizationClosure(
                posture="open",
                universe="actions/v1",
                profile="raes-recursive-realization/v1",
            ),
        )
    )
    assert downgrade_recursive_realization_structure(open_sequence, []).status is RealizationRelationStatus.UNSUPPORTED

    aliased = _package_rule().model_copy(
        update={
            "root": _package_rule().root.model_copy(
                update={
                    "aliases": (
                        RealizationIdentityAlias(
                            identity=("debian", "nmap"),
                            target=("apt", "nmap"),
                        ),
                    )
                }
            )
        }
    )
    assert downgrade_recursive_realization_structure(aliased, []).status is RealizationRelationStatus.UNSUPPORTED


def test_recursive_normal_form_has_a_closed_published_schema_and_fixtures() -> None:
    repo_root = Path(__file__).parents[3]
    generated = schema_bundle()["recursive-realization-constraint-v1"]
    published = json.loads(
        (repo_root / "contracts/schemas/realization-constraints/recursive-realization-constraint-v1.json").read_text()
    )
    assert generated == published
    validator = Draft202012Validator(published)
    fixture_root = repo_root / "contracts/fixtures/realization-constraints/recursive-realization-constraint-v1"
    valid = json.loads((fixture_root / "valid/nested-open.json").read_text())
    invalid = json.loads((fixture_root / "invalid/unnamed-closed-universe.json").read_text())
    assert not list(validator.iter_errors(valid))
    assert list(validator.iter_errors(invalid))
    assert RealizationConstraintDocument.model_validate(valid)
