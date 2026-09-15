#!/usr/bin/env python3
"""Render the release evidence documents for one set of output subjects.

Two documents are produced, deliberately kept apart:

* a CycloneDX runtime SBOM per distribution subject, describing what the
  distribution depends on at run time;
* a build/tool/native input inventory, describing what produced it.

Conflating them is the failure issue #1226 exists to prevent, so the inventory
never carries runtime components and the SBOM never carries build inputs. Both
bind the exact output subject digest: a filename or a matching version does not
establish which bytes a document describes.

The CycloneDX document is emitted directly rather than through a generator
dependency. The risk-bearing work — parsing wheel metadata and evaluating
markers — is done by the maintained `packaging` library in
`tools/release_evidence_sbom.py`; what remains here is serializing already
validated in-memory data into a published, stable schema. Keeping that
dependency-free is what lets the acceptance tests run in the project
environment, where a tool-closure-only dependency would be unimportable.

No timestamp or serial number is emitted, so the same inputs always produce the
same bytes and the evidence digest is stable across retries.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from tools.release_evidence_sbom import ReconciledClosure

CYCLONEDX_SPEC_VERSION = "1.6"
BUILD_INVENTORY_SCHEMA_VERSION = "raes-build-inventory/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXTRA_PROPERTY = "raes:extra"


class EvidenceDocumentError(Exception):
    """An evidence rendering failure carrying a stable, publishable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _require_digest(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise EvidenceDocumentError(
            "evidence-subject-digest-invalid",
            f"{subject} must carry a lowercase SHA-256 digest",
        )
    return value


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{name}@{version}"


def render_runtime_sbom(
    *,
    closure: ReconciledClosure,
    subject_name: str,
    subject_version: str,
    subject_filename: str,
    subject_digest: str,
    subject_role: str,
) -> dict[str, Any]:
    """Render one CycloneDX document bound to one exact output subject."""

    digest = _require_digest(subject_digest, subject=subject_filename)
    root_ref = _purl(subject_name, subject_version)

    components: list[dict[str, Any]] = []
    for component in closure.components:
        record: dict[str, Any] = {
            "type": "library",
            "bom-ref": _purl(component.name, component.version),
            "name": component.name,
            "version": component.version,
            "purl": _purl(component.name, component.version),
            "scope": component.scope,
        }
        if component.extra is not None:
            record["properties"] = [{"name": _EXTRA_PROPERTY, "value": component.extra}]
        components.append(record)

    by_name = {component.name: component for component in closure.components}
    dependencies: list[dict[str, Any]] = [
        {
            "ref": root_ref,
            "dependsOn": sorted(_purl(component.name, component.version) for component in closure.components),
        }
    ]
    for name in sorted(closure.edges):
        component = by_name.get(name)
        if component is None:
            continue
        children = []
        for child in closure.edges[name]:
            target = by_name.get(child)
            if target is not None:
                children.append(_purl(target.name, target.version))
        dependencies.append(
            {
                "ref": _purl(component.name, component.version),
                "dependsOn": sorted(children),
            }
        )

    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "version": 1,
        "metadata": {
            "component": {
                "type": "library",
                "bom-ref": root_ref,
                "name": subject_name,
                "version": subject_version,
                "purl": root_ref,
                "hashes": [{"alg": "SHA-256", "content": digest}],
                "properties": [
                    {"name": "raes:subject-filename", "value": subject_filename},
                    {"name": "raes:subject-role", "value": subject_role},
                ],
            }
        },
        "components": components,
        "dependencies": dependencies,
    }


def render_build_inventory(
    *,
    subjects: Sequence[Mapping[str, Any]],
    interpreter: Mapping[str, Any],
    build_backend: Mapping[str, Any],
    tool_inputs: Sequence[Mapping[str, Any]],
    native_inputs: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
    runner: Mapping[str, Any],
    lock_hashes: Mapping[str, str],
    policy_hashes: Mapping[str, str],
    release: Mapping[str, Any],
    profile_id: str,
) -> dict[str, Any]:
    """Render the build/tool/native input inventory for one release.

    `runner` records the selected runner image and whether the host was actually
    observed; a runner label alone is a selection, not a host inventory, and is
    never recorded as one. Lock and policy hashes stay in separate maps so an
    aggregate policy identity is never mistaken for a raw file hash.
    """

    if not subjects:
        raise EvidenceDocumentError(
            "evidence-subjects-absent",
            "build inventory must record at least one output subject",
        )
    recorded = []
    for subject in subjects:
        filename = str(subject.get("filename", ""))
        recorded.append(
            {
                "role": str(subject.get("role", "")),
                "filename": filename,
                "sha256": _require_digest(subject.get("sha256"), subject=filename or "subject"),
            }
        )

    return {
        "schema_version": BUILD_INVENTORY_SCHEMA_VERSION,
        "subjects": recorded,
        "profile": {"python_closure_profile_id": profile_id},
        "interpreter": dict(interpreter),
        "build_backend": dict(build_backend),
        "tool_inputs": [dict(item) for item in tool_inputs],
        "native_inputs": [dict(item) for item in native_inputs],
        "actions": [dict(item) for item in actions],
        "runner": dict(runner),
        "lock_hashes": dict(lock_hashes),
        "policy_hashes": dict(policy_hashes),
        "release": dict(release),
    }


__all__ = [
    "BUILD_INVENTORY_SCHEMA_VERSION",
    "CYCLONEDX_SPEC_VERSION",
    "EvidenceDocumentError",
    "render_build_inventory",
    "render_runtime_sbom",
]
