"""Backend manifest capability declarations for shared time."""

from __future__ import annotations

from pydantic import Field, model_validator

from ..manifest_authority import validate_backend_supported_contract_versions
from .base import ContractModel, NonEmptyString
from .validators import validate_unique_string_values

_TIME_CAPABILITY_REQUIRED_CONTRACTS = {
    "time-model-v1",
    "time-runtime-state-v1",
    "realized-time-model-v1",
    "runtime-snapshot-v1",
    "experiment-run-v1",
}
_TIME_CAPABILITY_TERMS = {
    "supported_domain_kinds": {"wall_clock", "monotonic", "simulated", "logical", "external"},
    "supported_authority_kinds": {"runtime", "backend", "system", "external"},
    "supported_advancement_modes": {
        "real_time",
        "dilated",
        "stepped",
        "event_driven",
        "externally_paced",
    },
    "supported_synchronization_modes": {"none", "authority", "barrier", "conservative"},
    "supported_mapping_kinds": {"identity", "affine_rational"},
    "supported_constraint_kinds": {"precedence", "duration", "window", "deadline", "cadence"},
    "supported_reset_behaviors": {"unsupported", "new_segment_zero", "new_segment_preserve_value"},
    "supported_replay_behaviors": {"unsupported", "restart_from_anchor", "restore_recorded_advances"},
}


class TimeCapabilitiesModel(ContractModel):
    """Backend support for the API-421 portable shared-time contract family."""

    name: NonEmptyString
    supported_contract_versions: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_domain_kinds: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_authority_kinds: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_advancement_modes: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_synchronization_modes: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_mapping_kinds: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    supported_constraint_kinds: list[NonEmptyString] = Field(
        default_factory=list, json_schema_extra={"uniqueItems": True}
    )
    supported_reset_behaviors: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_replay_behaviors: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    max_time_domains: int | None = Field(default=None, ge=1)
    max_clocks: int | None = Field(default=None, ge=1)
    supports_pause: bool = False
    supports_jump: bool = False
    supports_exact_rational_mappings: bool = False
    supports_append_only_history: bool = False
    supports_run_provenance: bool = False
    supports_coordinated_participant_reset: bool = False
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_time_capability(self) -> TimeCapabilitiesModel:
        if set(self.supported_contract_versions) != _TIME_CAPABILITY_REQUIRED_CONTRACTS:
            raise ValueError("time capabilities require the complete time contract family")
        validate_backend_supported_contract_versions(self.supported_contract_versions)
        for field_name, allowed in _TIME_CAPABILITY_TERMS.items():
            values = getattr(self, field_name)
            validate_unique_string_values(f"time {field_name}", values)
            unknown = sorted(set(values) - allowed)
            if unknown:
                raise ValueError(f"time {field_name} contains unknown values: {', '.join(unknown)}")
        if self.supported_mapping_kinds and not self.supports_exact_rational_mappings:
            raise ValueError("time mapping support requires exact rational mappings")
        return self


__all__ = ["TimeCapabilitiesModel"]
