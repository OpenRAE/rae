"""Trusted admission and one-shot dispatch boundary for runtime facts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from raes_contracts.contracts.runtime_facts import (
    RuntimeFactBindingDisposition,
    RuntimeFactBindingSelectionModel,
    RuntimeFactSinkModel,
)
from raes_contracts.errors import RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger

_LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class RuntimeFactBindingAdmission:
    """Trusted control-plane authorization for one action instance."""

    run_id: str
    participant_address: str
    episode_id: str
    workflow_address: str | None
    action_instance_id: str
    action_contract_address: str
    requested_at: str
    authority_refs: frozenset[str]
    selections: tuple[RuntimeFactBindingSelectionModel, ...]

    def __post_init__(self) -> None:
        if not self.authority_refs:
            raise ValueError("trusted binding admission requires authority_refs")
        if not self.selections:
            raise ValueError("trusted binding admission requires compiled selections")
        _parse_datetime(self.requested_at, "requested_at")
        sink_ids = [selection.sink.sink_id for selection in self.selections]
        target_fields = [selection.sink.target_field for selection in self.selections]
        if len(sink_ids) != len(set(sink_ids)):
            raise ValueError("trusted binding admission sink ids must be unique")
        if len(target_fields) != len(set(target_fields)):
            raise ValueError("trusted binding admission target fields must be unique")
        if any(selection.sink.action_contract_address != self.action_contract_address for selection in self.selections):
            raise ValueError("trusted binding admission action contract must match every compiled sink")

    @property
    def action_key(self) -> tuple[str, str, str, str | None, str, str]:
        """Return the exact admitted action context."""

        return (
            self.run_id,
            self.participant_address,
            self.episode_id,
            self.workflow_address,
            self.action_instance_id,
            self.action_contract_address,
        )


@dataclass(frozen=True)
class _RuntimeFactDispatchBinding:
    sink: RuntimeFactSinkModel
    value: object | None
    secret_ref: str | None


class _RuntimeFactDispatchFailure(RaesError):
    def __init__(self, disposition: RuntimeFactBindingDisposition) -> None:
        super().__init__(disposition.value)
        self.disposition = disposition


class RuntimeFactDispatchCommand:
    """One-shot command delivered only to the trusted action dispatcher."""

    __slots__ = ("_bindings", "_completed")

    def __init__(self, bindings: tuple[_RuntimeFactDispatchBinding, ...]) -> None:
        self._bindings = bindings
        self._completed = False

    @property
    def completed(self) -> bool:
        """Report whether the trusted adapter consumed the command."""

        return self._completed

    def dispatch(
        self,
        *,
        send: Callable[[Mapping[str, object]], None],
        secret_resolver: Callable[[str], object] | None = None,
    ) -> None:
        """Resolve protected references and synchronously deliver action inputs."""

        if self._completed:
            raise RuntimeError("runtime fact dispatch command was already consumed")
        inputs: dict[str, object] = {}
        try:
            for binding in self._bindings:
                inputs[binding.sink.target_field] = _materialize_binding(binding, secret_resolver)
            send(MappingProxyType(inputs))
            self._completed = True
        except _RuntimeFactDispatchFailure:
            raise
        except Exception as exc:
            # Isolation of the trusted send callback: the disposition replaces its failure.
            _LOGGER.exception("runtime fact dispatch callback failed", exc_info=foreign_failure_record(exc))
            raise _RuntimeFactDispatchFailure(RuntimeFactBindingDisposition.DISPATCH_FAILED) from exc
        finally:
            inputs.clear()

    def __repr__(self) -> str:
        return "RuntimeFactDispatchCommand(<protected>)"


def _parse_datetime(value: object, field_name: str = "timestamp") -> datetime:
    """Parse an ISO 8601 date-time that carries an explicit UTC offset.

    Naive and date-only values have no defined instant and would make later
    order comparisons raise ``TypeError``, so they are rejected here. The
    message names the field and the rule, never the rejected value.
    """

    message = f"{field_name} must be an ISO 8601 date-time with an explicit UTC offset"
    if not isinstance(value, str):
        raise ValueError(message)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise ValueError(message) from None
    if parsed.utcoffset() is None:
        raise ValueError(message)
    return parsed


def _value_matches_type(value: object, value_type: str) -> bool:
    if value_type in {"string", "reference"}:
        matches = isinstance(value, str)
    elif value_type == "boolean":
        matches = isinstance(value, bool)
    elif value_type == "integer":
        matches = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == "number":
        matches = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        matches = False
    return matches


def _materialize_binding(
    binding: _RuntimeFactDispatchBinding,
    secret_resolver: Callable[[str], object] | None,
) -> object:
    value = binding.value
    if binding.secret_ref is not None:
        if secret_resolver is None:
            raise _RuntimeFactDispatchFailure(RuntimeFactBindingDisposition.SECRET_UNAVAILABLE)
        try:
            value = secret_resolver(binding.secret_ref)
        except Exception as exc:
            # Isolation of the secret resolver: the record stays value-free, and the disposition replaces it.
            _LOGGER.exception("runtime fact secret resolution failed", exc_info=foreign_failure_record(exc))
            raise _RuntimeFactDispatchFailure(RuntimeFactBindingDisposition.SECRET_UNAVAILABLE) from exc
    if value is None:
        raise _RuntimeFactDispatchFailure(RuntimeFactBindingDisposition.SECRET_UNAVAILABLE)
    if not _value_matches_type(value, binding.sink.value_type.value):
        raise _RuntimeFactDispatchFailure(RuntimeFactBindingDisposition.WRONG_TYPE)
    return value


__all__ = ("RuntimeFactBindingAdmission", "RuntimeFactDispatchCommand")
