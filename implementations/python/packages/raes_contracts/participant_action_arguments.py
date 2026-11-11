"""Portable normalized participant action-argument carriers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

_ACTION_CONTRACT_PREFIX = "participant.action-contract."

type ParticipantActionArgumentScalar = str | int | float | bool
type ParticipantActionArgumentValue = ParticipantActionArgumentScalar | tuple[ParticipantActionArgumentScalar, ...]


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")


def _string_tuple(value: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    values = tuple(value)
    if any(not isinstance(item, str) or not item for item in values):
        raise TypeError(f"{field_name} entries must be non-empty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} entries must be unique")
    return values


@dataclass(frozen=True)
class ParticipantValidatedActionSelection:
    """Portable normalized action meaning supplied to every backend."""

    action_contract_address: str
    argument_shape_ref: str
    proposal_ref: str
    normalized_arguments: tuple[tuple[str, ParticipantActionArgumentValue], ...]
    defaulted_argument_names: tuple[str, ...] = ()
    omitted_argument_names: tuple[str, ...] = ()
    normalization_disclosure_refs: tuple[str, ...] = ()
    omission_disclosure_refs: tuple[str, ...] = ()
    default_disclosure_refs: tuple[str, ...] = ()
    loss_disclosure_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.action_contract_address, "action_contract_address")
        if not self.action_contract_address.startswith(_ACTION_CONTRACT_PREFIX):
            raise ValueError("action_contract_address must be a compiled participant action-contract address")
        _require_non_empty(self.argument_shape_ref, "argument_shape_ref")
        _require_non_empty(self.proposal_ref, "proposal_ref")
        names = tuple(name for name, _ in self.normalized_arguments)
        if any(not isinstance(name, str) or not name for name in names):
            raise TypeError("normalized argument names must be non-empty strings")
        if len(set(names)) != len(names):
            raise ValueError("normalized argument names must be unique")
        if names != tuple(sorted(names)):
            raise ValueError("normalized arguments must use canonical name order")
        for field_name in (
            "defaulted_argument_names",
            "omitted_argument_names",
            "normalization_disclosure_refs",
            "omission_disclosure_refs",
            "default_disclosure_refs",
            "loss_disclosure_refs",
        ):
            object.__setattr__(self, field_name, _string_tuple(getattr(self, field_name), field_name))

    @property
    def argument_map(self) -> dict[str, ParticipantActionArgumentValue]:
        """Return a defensive mapping view of the canonical normalized values."""

        return dict(self.normalized_arguments)


__all__ = (
    "ParticipantActionArgumentScalar",
    "ParticipantActionArgumentValue",
    "ParticipantValidatedActionSelection",
)
