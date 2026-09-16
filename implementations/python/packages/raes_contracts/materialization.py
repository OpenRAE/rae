"""Dependency-neutral carriers for negotiated backend materialization reporting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal, Protocol

from pydantic import ConfigDict, Field, model_validator

from ._base import ContractModel
from .canonical import canonical_json_digest
from .json_ingress import parse_bounded_json_object
from .realization_structure import validate_realization_value
from .runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

if TYPE_CHECKING:
    from .contracts.materialization_attestation import MaterializationArchiveRecord

MATERIALIZATION_ATTESTATION_CONTRACT = "backend-materialization-attestation-v1"
MATERIALIZATION_MAX_BYTES = 1048576
MaterializationDigest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


class MaterializationSource(ContractModel):
    """Trusted full source context sealed into the exact operation plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_id: Literal["backend-materialization-attestation-v1"] = MATERIALIZATION_ATTESTATION_CONTRACT
    snapshot: str = Field(min_length=1, max_length=MATERIALIZATION_MAX_BYTES)
    authored_digest: MaterializationDigest
    instantiated_digest: MaterializationDigest
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

    @property
    def augmentation_scope_required(self) -> bool:
        """Derive the permission obligation from bound SDL, not a plan's convenience flag."""
        payload = parse_bounded_json_object(self.snapshot, max_bytes=MATERIALIZATION_MAX_BYTES)
        return payload["scenario"].get("augmentation_scope") is not None

    @model_validator(mode="after")
    def _validate_source_identity(self) -> MaterializationSource:
        payload = parse_bounded_json_object(self.snapshot, max_bytes=MATERIALIZATION_MAX_BYTES)
        if not validate_realization_value(payload, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant:
            raise ValueError("materialization source exceeds portable bounds")
        if payload.get("profile") != "raes-sdl-instantiated-snapshot/v2" or set(payload) != {"profile", "scenario"}:
            raise ValueError("materialization source requires the admitted instantiated snapshot profile")
        if canonical_json_digest(payload) != self.instantiated_digest:
            raise ValueError("materialization source does not match its instantiated identity")
        scenario = payload.get("scenario")
        provenance = scenario.get("instantiation_provenance") if isinstance(scenario, dict) else None
        authored = provenance.get("authored_digest") if isinstance(provenance, dict) else None
        if not isinstance(authored, dict) or authored.get("value") != self.authored_digest:
            raise ValueError("materialization source does not match its authored identity")
        return self


class MaterializationSubmission(ContractModel):
    """A producer's bounded SDL bytes; admission is owned by the SDL consumer."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_id: Literal["backend-materialization-attestation-v1"] = MATERIALIZATION_ATTESTATION_CONTRACT
    sdl: str = Field(min_length=1, max_length=MATERIALIZATION_MAX_BYTES)

    @model_validator(mode="after")
    def _validate_size(self) -> MaterializationSubmission:
        if len(self.sdl.encode("utf-8")) > MATERIALIZATION_MAX_BYTES:
            raise ValueError("materialization submission exceeds the byte limit")
        return self


class MaterializationArchive(Protocol):
    """The incumbent run archive supplied by the runtime's operational owner."""

    def publish(self, content: str) -> MaterializationArchiveRecord: ...

    def read(self, record: MaterializationArchiveRecord) -> MaterializationSubmission: ...


def require_materialization_records(records: object) -> None:
    """Validate the bounded runtime-owned archive-reference collection."""
    if not isinstance(records, tuple):
        raise TypeError("materialization attestations must be a tuple")
    if not records:
        return
    from .contracts.materialization_attestation import MaterializationArchiveRecord

    if not validate_realization_value(records, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True).conformant:
        raise ValueError("materialization attestations exceed portable bounds")
    identities = set()
    for record in records:
        if not isinstance(record, MaterializationArchiveRecord):
            raise TypeError("materialization attestations require typed archive references")
        MaterializationArchiveRecord.model_validate(record.model_dump(mode="json"))
        identity = (record.run_id, record.reference.ref_id)
        if identity in identities:
            raise ValueError("materialization attestations must have unique run and artifact identities")
        identities.add(identity)


__all__ = [
    "MATERIALIZATION_ATTESTATION_CONTRACT",
    "MaterializationArchive",
    "MaterializationSource",
    "MaterializationSubmission",
]
