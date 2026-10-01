"""Exact output-affecting semantics of the SCE-002 v1 compiler profiles."""

from __future__ import annotations

import hashlib
from typing import Final

from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.contracts import (
    RANDOM_STREAM_PROFILE_SCHEMA_VERSION,
    AdmittedTrialPlanProfilesModel,
    TrialCoordinateModel,
)
from raes_contracts.contracts.trial_coordinate_order import (
    REPLICATE_ID_WIDTH,
    canonical_coordinate_sort_key,
    replicate_ordinal,
)

IDENTITY_DOMAIN: Final = "raes-trial-compiler-identity-v1"
MIXED_IDENTITY_DOMAIN: Final = "raes-trial-compiler-mixed-composition-identity-v1"
RANDOM_STREAM_PROFILE_ID: Final = "blake3-xof-v1"
RANDOM_STREAM_PROFILE_VERSION: Final = RANDOM_STREAM_PROFILE_SCHEMA_VERSION


def admitted_profiles(*, mixed_composition: bool = False) -> AdmittedTrialPlanProfilesModel:
    """Return the single exact profile set implemented by this compiler."""

    return AdmittedTrialPlanProfilesModel(
        coordinate_profile="trial-coordinate-v1",
        entry_identity_profile=(
            "trial-entry-identity-mixed-composition-v1" if mixed_composition else "trial-entry-identity-v1"
        ),
        run_identity_profile=(
            "archival-run-identity-mixed-composition-v1" if mixed_composition else "archival-run-identity-v1"
        ),
        canonicalization_profile="jcs-sha256-v1",
        integrity_profile="acyclic-digest-chain-v1",
        compiler_profile=("trial-compiler-mixed-composition-v1" if mixed_composition else "trial-compiler-v1"),
        selection_policy_profile="experiment-selection-v1",
        random_stream_profile=RANDOM_STREAM_PROFILE_ID,
        execution_control_profile="attempt-control-v1",
        cleanup_profile="trial-cleanup-v1",
        isolation_profile="scheduler-isolation-v1",
    )


def replicate_id(ordinal: int) -> str:
    """Encode a one-based replicate ordinal under ``trial-coordinate-v1``."""

    if ordinal < 1 or ordinal >= 10**REPLICATE_ID_WIDTH:
        raise ValueError("replicate ordinal is outside trial-coordinate-v1")
    return f"replicate-{ordinal:0{REPLICATE_ID_WIDTH}d}"


def coordinate_projection(coordinate: TrialCoordinateModel) -> dict[str, str]:
    """Canonical projection with absent optional dimensions omitted."""

    return coordinate.model_dump(mode="json", exclude_none=True)


def realization_assignment_key(coordinate: TrialCoordinateModel) -> str:
    """Return the stable key used for an exact coordinate realization assignment."""

    return canonical_json_bytes(coordinate_projection(coordinate)).decode("utf-8")


def derive_identity(kind: str, projection: object, *, mixed_composition: bool = False) -> str:
    """Derive one domain-separated JCS/SHA-256 portable identity."""

    material = {
        "domain": MIXED_IDENTITY_DOMAIN if mixed_composition else IDENTITY_DOMAIN,
        "kind": kind,
        "projection": projection,
    }
    digest = hashlib.sha256(canonical_json_bytes(material)).hexdigest()
    return f"{kind}-{digest}"


__all__ = [
    "admitted_profiles",
    "canonical_coordinate_sort_key",
    "coordinate_projection",
    "derive_identity",
    "RANDOM_STREAM_PROFILE_ID",
    "RANDOM_STREAM_PROFILE_VERSION",
    "realization_assignment_key",
    "replicate_id",
    "replicate_ordinal",
]
