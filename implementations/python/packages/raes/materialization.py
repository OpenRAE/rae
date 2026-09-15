"""Descriptive SDL phase and its ordinary semantic admission."""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field, model_validator
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

from ._scenario_instantiation import collect_variable_tokens, resolve_json_pointer
from .materialization_provenance import MaterializationProvenance
from .scenario import ScenarioContent


class MaterializedScenario(ScenarioContent):
    """What one backend materialized; parsing this document grants no authority."""

    _allows_qualified_declaration_keys: ClassVar[bool] = True

    model_config = ConfigDict(
        title="SDL Materialization Attestation v1",
        json_schema_extra={"x-raes-document-phase": "materialized-scenario"},
    )

    materialization_provenance: MaterializationProvenance = Field(
        json_schema_extra={"x-raes-realization-dimension": False},
    )

    @model_validator(mode="after")
    def _validate_materialized_content(self) -> MaterializedScenario:
        content = self.model_dump(mode="json", exclude_unset=True)
        if collect_variable_tokens(content):
            raise ValueError("materialized SDL must not contain unresolved substitution tokens")
        content.pop("materialization_provenance")
        for origin in self.materialization_provenance.origins:
            if origin.change == "removed":
                continue
            try:
                resolve_json_pointer(content, origin.field_pointer)
            except (KeyError, IndexError, TypeError, ValueError):
                raise ValueError("materialization origin must resolve to supplied SDL content") from None
        if any(binding.node_name not in self.nodes for binding in self.materialization_provenance.resource_bindings):
            raise ValueError("materialization resource binding must resolve to a node")
        return self


def admit_materialized_scenario(scenario: MaterializedScenario) -> MaterializedScenario:
    """Reconstruct and semantically admit a direct or deserialized description."""

    from .validator import SemanticValidator

    content = {name: getattr(scenario, name) for name in ScenarioContent.model_fields}
    if not validate_realization_value(content, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True).conformant:
        raise ValueError("materialized SDL exceeds portable bounds")
    admitted = MaterializedScenario.model_validate(scenario.model_dump(mode="json", exclude_unset=True))
    validator = SemanticValidator(admitted)
    validator.validate()
    admitted._set_advisories(validator.warnings)
    admitted._set_semantic_validated(True)
    return admitted
