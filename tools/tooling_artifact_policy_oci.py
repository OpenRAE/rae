"""OCI image-graph admission for export-bearing locked images.

An index-only record proves that *an* index was reviewed. It cannot prove that
the manifests, config and layers beneath that index survived a mirror copy, an
offline export or a daemon import, because nothing binds them. An image that
must move through those paths therefore opts into the graph-bearing admission
policy -- the one that accepts ``oci-platform-graph-digests`` evidence -- and is
then required to carry its complete platform graph here, before any client runs.

This module owns only the static coherence of that record. Verifying real bytes
against it is `tools.oci_image_layout` (offline) and `tools.oci_release_image`
(daemon readback); neither is reached until these checks pass.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    ARTIFACT_LOCK_PATH,
    as_list,
    as_mapping,
    failure,
    normalize_platform_id,
    string_set,
)

# The evidence class that distinguishes an export-bearing image from an
# index-only one. The admission policy, not this module, decides which images
# supply it; this module enforces that the claim and the record agree.
GRAPH_EVIDENCE = "oci-platform-graph-digests"

RULE_UNPOLICED = "tooling-oci-graph-unpoliced"
RULE_MISSING = "tooling-oci-graph-missing"
RULE_INDEX_IDENTITY = "tooling-oci-index-identity"
RULE_LAYER_ARITY = "tooling-oci-layer-arity"
RULE_LAYER_DUPLICATE = "tooling-oci-layer-duplicate"
RULE_PLATFORM_MISMATCH = "tooling-oci-platform-mismatch"
RULE_MANIFEST_DUPLICATE = "tooling-oci-manifest-duplicate"
RULE_DIGEST_DENIED = "tooling-digest-denied"

# Canonical platform id -> the OCI platform its objects must declare. A record
# that names one platform while carrying another's objects is exactly the
# wrong-platform substitution this table exists to reject.
_PLATFORM_IDENTITY = {
    "linux-x86_64": ("amd64", "linux"),
    "linux-arm64": ("arm64", "linux"),
    "macos-arm64": ("arm64", "darwin"),
}

_DIGEST_PREFIX = "sha256:"


def _lock_failure(rule: str, message: str) -> PolicyFailure:
    return failure(rule, message, ARTIFACT_LOCK_PATH)


def is_graph_bearing(artifact: Mapping[str, Any], policies: Mapping[str, Mapping[str, Any]]) -> bool:
    """Return whether every admission policy this artifact names admits a graph.

    The evidence join is conjunctive -- an artifact supplies one evidence set to
    all of its policies -- so a graph is admitted only when no referenced policy
    would reject it.
    """

    policy_refs = string_set(artifact.get("policy_refs"))
    return bool(policy_refs) and all(
        GRAPH_EVIDENCE in string_set(as_mapping(policies.get(policy_ref)).get("accepted_evidence"))
        for policy_ref in policy_refs
    )


def declares_graph(artifact: Mapping[str, Any]) -> bool:
    return any(as_mapping(platform).get("oci_graph") is not None for platform in as_list(artifact.get("platforms")))


def _bare_digests(graph: Mapping[str, Any]) -> list[str]:
    descriptors = [as_mapping(graph.get(name)).get("digest") for name in ("index", "manifest", "config")] + [
        as_mapping(layer).get("digest") for layer in as_list(graph.get("layers"))
    ]
    values = [value for value in (*descriptors, *as_list(graph.get("diff_ids"))) if isinstance(value, str)]
    return [value.removeprefix(_DIGEST_PREFIX) for value in values]


def _identity_failures(artifact_id: str, artifact: Mapping[str, Any], graph: Mapping[str, Any]) -> list[PolicyFailure]:
    release = as_mapping(artifact.get("source")).get("release")
    if as_mapping(graph.get("index")).get("digest") == release:
        return []
    return [
        _lock_failure(
            RULE_INDEX_IDENTITY,
            f"{artifact_id} platform graph does not retain the reviewed index identity",
        )
    ]


def _layer_failures(artifact_id: str, graph: Mapping[str, Any]) -> list[PolicyFailure]:
    layers = as_list(graph.get("layers"))
    digests = [as_mapping(layer).get("digest") for layer in layers]
    failures: list[PolicyFailure] = []
    if len(layers) != len(as_list(graph.get("diff_ids"))):
        failures.append(
            _lock_failure(
                RULE_LAYER_ARITY,
                f"{artifact_id} platform graph does not pair every layer with its uncompressed identity",
            )
        )
    if len(set(digests)) != len(digests):
        failures.append(
            _lock_failure(
                RULE_LAYER_DUPLICATE,
                f"{artifact_id} platform graph repeats a layer digest",
            )
        )
    return failures


def _platform_identity_failures(
    artifact_id: str,
    platform_id: str,
    graph: Mapping[str, Any],
) -> list[PolicyFailure]:
    expected = _PLATFORM_IDENTITY.get(normalize_platform_id(platform_id))
    observed = (graph.get("architecture"), graph.get("os"))
    if expected is not None and observed == expected:
        return []
    return [
        _lock_failure(
            RULE_PLATFORM_MISMATCH,
            f"{artifact_id} platform graph declares objects for another platform",
        )
    ]


def _denied_failures(artifact_id: str, graph: Mapping[str, Any], denied_digests: set[str]) -> list[PolicyFailure]:
    if not denied_digests.intersection(_bare_digests(graph)):
        return []
    return [_lock_failure(RULE_DIGEST_DENIED, f"{artifact_id} platform graph uses a denied digest")]


def _declaration_failures(
    artifact_id: str,
    platform_id: str,
    *,
    declared: bool,
    admitted: bool,
) -> list[PolicyFailure]:
    """Reject a graph and its admission policy disagreeing in either direction."""

    if admitted and not declared:
        return [
            _lock_failure(
                RULE_MISSING,
                f"{artifact_id} admits a platform graph but {platform_id} declares none",
            )
        ]
    if declared and not admitted:
        return [
            _lock_failure(
                RULE_UNPOLICED,
                f"{artifact_id} declares a platform graph its admission policy does not admit",
            )
        ]
    return []


def platform_graph_failures(
    artifact_id: str,
    artifact: Mapping[str, Any],
    platform: Mapping[str, Any],
    policies: Mapping[str, Mapping[str, Any]],
    denied_digests: set[str],
) -> list[PolicyFailure]:
    """Validate one platform's OCI graph against its artifact and admission policy."""

    graph = platform.get("oci_graph")
    platform_id = platform.get("platform_id")
    declaration = _declaration_failures(
        artifact_id,
        str(platform_id),
        declared=graph is not None,
        admitted=is_graph_bearing(artifact, policies),
    )
    if declaration or graph is None:
        return declaration
    graph = as_mapping(graph)
    return [
        *_identity_failures(artifact_id, artifact, graph),
        *_layer_failures(artifact_id, graph),
        *_platform_identity_failures(artifact_id, str(platform_id), graph),
        *_denied_failures(artifact_id, graph, denied_digests),
    ]


def artifact_graph_failures(artifact_id: str, platforms: Sequence[Any]) -> list[PolicyFailure]:
    """Reject two platforms of one image that claim the same selected manifest."""

    manifests = [
        digest
        for platform in platforms
        if (graph := as_mapping(platform).get("oci_graph")) is not None
        and isinstance(digest := as_mapping(as_mapping(graph).get("manifest")).get("digest"), str)
    ]
    if len(set(manifests)) == len(manifests):
        return []
    return [
        _lock_failure(
            RULE_MANIFEST_DUPLICATE,
            f"{artifact_id} selects one platform manifest for more than one platform",
        )
    ]


__all__ = [
    "GRAPH_EVIDENCE",
    "artifact_graph_failures",
    "declares_graph",
    "is_graph_bearing",
    "platform_graph_failures",
]
