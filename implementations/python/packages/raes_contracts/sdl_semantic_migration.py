"""Explicit author decisions for the legacy-to-progressive SDL version pair."""

from typing import Literal

from pydantic import ConfigDict, Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes import VARIABLE_TOKEN_PATTERN
from raes.value_parsing import is_variable_ref, normalize_enum_value

from ._base import ContractModel

# Match the incumbent parser's case normalization, including Kelvin-sign K.
_SENTINEL_ALIAS_PATTERN = r"^(?:[uU][nN][kK\u212a][nN][oO][wW][nN]|[oO][tT][hH][eE][rR])$"


class SDLSentinelDecision(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pointer: str = Field(min_length=1, max_length=4096, pattern=r"^(?:/(?:[^~/]|~[01])*)+$")
    interpretation: Literal["knowledge", "exact-identity", "delegated"]
    identity: str | None = Field(default=None, min_length=1, max_length=256)
    rationale: str = Field(min_length=1, max_length=512, pattern=r"\S")

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        schema["allOf"] = [
            {
                "if": {"properties": {"interpretation": {"const": "exact-identity"}}},
                "then": {
                    "required": ["identity"],
                    "properties": {
                        "identity": {
                            "type": "string",
                            "not": {
                                "anyOf": [
                                    {"pattern": _SENTINEL_ALIAS_PATTERN},
                                    {"pattern": "^" + VARIABLE_TOKEN_PATTERN + "$"},
                                ]
                            },
                        }
                    },
                },
                "else": {"properties": {"identity": {"type": "null"}}},
            }
        ]
        return schema

    @model_validator(mode="after")
    def _identity_matches_decision(self) -> "SDLSentinelDecision":
        if (self.interpretation == "exact-identity") != (self.identity is not None):
            raise ValueError("only an exact-identity decision supplies an identity")
        if self.identity is not None and (
            normalize_enum_value(self.identity) in {"unknown", "other"} or is_variable_ref(self.identity)
        ):
            raise ValueError("an exact identity cannot be a sentinel alias or variable reference")
        if not self.rationale.strip():
            raise ValueError("an exact identity and a nonempty author rationale are required")
        return self


class SDLSemanticMigrationContext(ContractModel):
    """Adoption is explicit; no default silently waives old evidence obligations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_revision: Literal["raes-legacy-semantics/384e8b19"] = "raes-legacy-semantics/384e8b19"
    target_revision: Literal["raes-progressive-semantics/v1"] = "raes-progressive-semantics/v1"
    adopt_recursive_constraints: Literal[True]
    admission_contract: Literal["backend-realization-preparation-v1"]
    observation_contract: Literal["observation-demand-v1"]
    rationale: str = Field(min_length=1, max_length=512, pattern=r"\S")
    sentinel_decisions: tuple[SDLSentinelDecision, ...] = Field(default=(), max_length=256)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        schema["x-raes-invariants"] = [
            {
                "id": "unique-sentinel-decision-pointers",
                "description": "Each source sentinel pointer has at most one author decision.",
                "level": "error",
                "validator": "raes_contracts.sdl_semantic_migration.SDLSemanticMigrationContext.model_validate",
                "inputs": [{"contract_id": "sdl-semantic-migration-context-v1", "instance_path": "#"}],
            }
        ]
        return schema

    @model_validator(mode="before")
    @classmethod
    def _explicit_boolean_adoption(cls, value: object) -> object:
        if isinstance(value, dict) and value.get("adopt_recursive_constraints") is not True:
            raise ValueError("recursive semantic adoption must be explicitly true")
        return value

    @model_validator(mode="after")
    def _unique_decisions(self) -> "SDLSemanticMigrationContext":
        pointers = [decision.pointer for decision in self.sentinel_decisions]
        if len(pointers) != len(set(pointers)) or not self.rationale.strip():
            raise ValueError("migration decisions require unique pointers and a nonempty rationale")
        return self
