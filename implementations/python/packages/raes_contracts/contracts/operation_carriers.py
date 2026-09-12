"""Closed portable operation receipt and status carriers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, StrictBool, model_validator

from ..addressing import CompiledAddress
from ..diagnostics import Diagnostic, DiagnosticModel
from ..operation_lifecycle import (
    OperationAdmissionContext,
    OperationState,
    operation_terminal_diagnostic,
    require_operation_terminal_diagnostics,
)
from ..planning import RuntimeDomain
from ..versions import OPERATION_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString


class OperationReceiptModel(ContractModel):
    schema_version: Literal[OPERATION_SCHEMA_VERSION] = OPERATION_SCHEMA_VERSION
    operation_id: NonEmptyString
    domain: RuntimeDomain
    submitted_at: Rfc3339DateTimeString
    accepted: StrictBool
    context: OperationAdmissionContext
    diagnostics: list[DiagnosticModel] = Field(default_factory=list)


_NON_SUCCESS_OPERATION_STATES = (
    OperationState.FAILED,
    OperationState.CANCELLED,
    OperationState.INDETERMINATE,
)


def _terminal_diagnostic_schema(state: OperationState) -> dict[str, Any]:
    diagnostic = operation_terminal_diagnostic(state)
    return {
        "properties": {
            "code": {"const": diagnostic.code},
            "domain": {"const": diagnostic.domain},
            "address": {"const": diagnostic.address},
            "message": {"const": diagnostic.message},
            "severity": {"const": diagnostic.severity.value},
        },
        "required": ["code", "domain", "address", "message", "severity"],
    }


class OperationStatusModel(ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "allOf": [
                *[
                    {
                        "if": {"properties": {"state": {"const": state.value}}, "required": ["state"]},
                        "then": {
                            "properties": {
                                "diagnostics": {
                                    "contains": _terminal_diagnostic_schema(state),
                                    "maxContains": 1,
                                }
                            }
                        },
                    }
                    for state in _NON_SUCCESS_OPERATION_STATES
                ],
                *[
                    {
                        "if": {
                            "properties": {
                                "diagnostics": {
                                    "contains": {
                                        "properties": {"code": {"const": operation_terminal_diagnostic(state).code}},
                                        "required": ["code"],
                                    }
                                }
                            },
                            "required": ["diagnostics"],
                        },
                        "then": {"properties": {"state": {"const": state.value}}},
                    }
                    for state in _NON_SUCCESS_OPERATION_STATES
                ],
                {
                    "properties": {
                        "diagnostics": {
                            "items": {
                                "allOf": [
                                    {
                                        "if": {
                                            "properties": {
                                                "code": {"const": operation_terminal_diagnostic(state).code}
                                            },
                                            "required": ["code"],
                                        },
                                        "then": _terminal_diagnostic_schema(state),
                                    }
                                    for state in _NON_SUCCESS_OPERATION_STATES
                                ]
                            }
                        }
                    }
                },
            ]
        },
    )

    schema_version: Literal[OPERATION_SCHEMA_VERSION] = OPERATION_SCHEMA_VERSION
    operation_id: NonEmptyString
    domain: RuntimeDomain
    state: OperationState
    submitted_at: Rfc3339DateTimeString
    updated_at: Rfc3339DateTimeString
    context: OperationAdmissionContext
    diagnostics: list[DiagnosticModel] = Field(default_factory=list)
    changed_addresses: list[CompiledAddress] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_status(self) -> OperationStatusModel:
        if len(self.changed_addresses) != len(set(self.changed_addresses)):
            raise ValueError("changed addresses must be unique")
        require_operation_terminal_diagnostics(
            self.state,
            [
                Diagnostic(
                    code=diagnostic.code,
                    domain=diagnostic.domain,
                    address=diagnostic.address,
                    message=diagnostic.message,
                    severity=diagnostic.severity,
                )
                for diagnostic in self.diagnostics
            ],
        )
        return self


__all__ = ("OperationReceiptModel", "OperationStatusModel")
