"""Dependency-neutral carriers for negotiated backend materialization reporting."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from ._base import ContractModel
from .canonical import canonical_json_digest
from .json_ingress import StrictJsonIngressError, parse_bounded_json_object
from .materialization_inventory import InventoryTargetScope
from .realization_structure import DOCUMENT_SCALAR, validate_realization_value
from .runtime_value_limits import MATERIALIZATION_MAX_BYTES, RUNTIME_SNAPSHOT_VALUE_LIMITS

MATERIALIZATION_ATTESTATION_CONTRACT = "backend-materialization-attestation-v1"
MATERIALIZATION_LIMIT_ERROR = "materialization_limit_exceeded"
MaterializationDigest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
# One admitted SDL document body. ``max_length`` counts characters; validators also check UTF-8 bytes.
MaterializationDocument = Annotated[str, Field(min_length=1, max_length=MATERIALIZATION_MAX_BYTES), DOCUMENT_SCALAR]


def require_materialization_document_bytes(value: str, subject: str) -> None:
    """Refuse a document whose UTF-8 encoding exceeds the shared materialization ceiling."""
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError(f"{subject} is not valid UTF-8 text") from None
    if size > MATERIALIZATION_MAX_BYTES:
        raise PydanticCustomError(MATERIALIZATION_LIMIT_ERROR, f"{subject} exceeds the byte limit")


class MaterializationSource(ContractModel):
    """Trusted full source context sealed into the exact operation plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_id: Literal["backend-materialization-attestation-v1"] = MATERIALIZATION_ATTESTATION_CONTRACT
    snapshot: MaterializationDocument
    authored_digest: MaterializationDigest
    instantiated_digest: MaterializationDigest
    run_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    target_scope: InventoryTargetScope | None = Field(default=None, exclude_if=lambda value: value is None)

    @property
    def augmentation_scope_required(self) -> bool:
        """Derive the permission obligation from bound SDL, not a plan's convenience flag."""
        payload = parse_bounded_json_object(self.snapshot, max_bytes=MATERIALIZATION_MAX_BYTES)
        return payload["scenario"].get("augmentation_scope") is not None

    @model_validator(mode="after")
    def _validate_source_identity(self) -> MaterializationSource:
        require_materialization_document_bytes(self.snapshot, "materialization source")
        try:
            payload = parse_bounded_json_object(self.snapshot, max_bytes=MATERIALIZATION_MAX_BYTES)
        except StrictJsonIngressError as exc:
            raise ValueError(f"materialization source snapshot failed strict JSON ingress ({exc.code})") from exc
        if not validate_realization_value(payload, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS).conformant:
            raise PydanticCustomError(MATERIALIZATION_LIMIT_ERROR, "materialization source exceeds portable bounds")
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
    sdl: MaterializationDocument

    @model_validator(mode="after")
    def _validate_size(self) -> MaterializationSubmission:
        require_materialization_document_bytes(self.sdl, "materialization submission")
        return self


__all__ = [
    "MATERIALIZATION_ATTESTATION_CONTRACT",
    "MATERIALIZATION_LIMIT_ERROR",
    "MATERIALIZATION_MAX_BYTES",
    "MaterializationDocument",
    "MaterializationSource",
    "MaterializationSubmission",
    "require_materialization_document_bytes",
]
