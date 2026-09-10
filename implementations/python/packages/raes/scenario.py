"""Top-level Scenario model — the root of the SDL.

The Scenario combines specification sections covering
who (entities, accounts, agents), what (nodes, features,
content), when (scripts, stories, events),
and declarative experiment semantics (objectives, conditions,
relationships, workflows, variables). Per ADR-073 the SDL no
longer carries the OCR scoring pipeline; graded scoring/reward
live in the experiment/evaluator plane (ADR-055/064/069).

Delivery-level concerns (Docker, Terraform, cloud APIs) are outside the SDL.
"""

from collections.abc import Mapping
from typing import ClassVar

from pydantic import ConfigDict, Field, PrivateAttr, model_validator

from ._base import SDLModel
from ._classification_guard import LegacyClassificationGuard
from ._errors import SDLParseDiagnostic
from ._identifiers import (
    PortableIdentifier,
    QualifiedName,
    require_module_identifier,
    require_portable_identifier,
)
from ._mapping_scopes import HASHMAP_SECTIONS
from ._scenario_instantiation import collect_variable_tokens, resolve_json_pointer
from .accounts import Account
from .agents import Agent
from .conditions import Condition
from .content import Content
from .deployment_tenancy import DeploymentCell, DeploymentTenant
from .enterprise_identity import IdentityFacade, IdentityForest
from .entities import Entity
from .evidence_requirements import EvidenceRequirement
from .explicitness import ExplicitnessRecord
from .features import Feature
from .identity_domains import IdentityDomain
from .infrastructure import InfraNode
from .nodes import Node
from .objectives import Objective
from .orchestration import Event, Inject, Script, Story, Workflow
from .participant_behavior import (
    ParticipantActionContract,
    ParticipantObservationBoundary,
)
from .participant_behavior_specification import ParticipantBehaviorSpecification
from .participant_outcome_semantics import OutcomeInterpretationRule
from .phase_contracts import (
    CapabilityConstraint,
    ExpansionProvenance,
    InstantiationProvenance,
    _json_value_equal,
)
from .propositions import Assertion, Proposition
from .realization_designation import RealizationDesignation
from .relationships import Relationship
from .runtime_forwarding_agent import RuntimeForwardingAgent
from .stateful_resources import GeneratedArtifact, PersistentVolume
from .time_model import (
    Clock,
    TemporalConstraint,
    TimeDomain,
    TimeDomainMapping,
    TimeProgressionPolicy,
)
from .variables import Variable
from .variation import VariationPoint

VariableName = PortableIdentifier
VariableDefinitions = dict[PortableIdentifier, Variable]


def _legacy_constraint_name(parameter: tuple[str, ...]) -> str:
    """Project a typed identity into the pre-#724 private planner key."""

    if len(parameter) == 1:
        return parameter[0]
    return ".".join((*parameter[:-1], "__private", parameter[-1]))


def _constraint_variable_specs(
    constraints: tuple[CapabilityConstraint, ...],
) -> dict[str, dict[str, object]]:
    return {
        _legacy_constraint_name(constraint.parameter): {
            "allowed_values": list(constraint.allowed_values),
        }
        for constraint in constraints
    }


def _constraint_node_refs(
    constraints: tuple[CapabilityConstraint, ...],
) -> dict[str, dict[str, str | None]]:
    refs: dict[str, dict[str, str | None]] = {}
    for constraint in constraints:
        parts = constraint.field_pointer.split("/")
        if len(parts) != 4 or parts[1] not in {"nodes", "infrastructure"}:
            continue
        field_name = parts[3]
        if (parts[1], field_name) not in {
            ("nodes", "os"),
            ("nodes", "architecture"),
            ("infrastructure", "count"),
        }:
            continue
        node_name = parts[2].replace("~1", "/").replace("~0", "~")
        # ``architecture`` is populated only when present so nodes without an
        # architecture constraint keep a byte-identical canonical projection.
        refs.setdefault(node_name, {"os": None, "count": None})[field_name] = _legacy_constraint_name(
            constraint.parameter
        )
    return refs


def _validate_declaration_identifier(
    identifier: object,
    *,
    section_name: str,
    allow_qualified: bool,
) -> None:
    if allow_qualified:
        local_name = QualifiedName.parse(identifier).parts[-1]
    else:
        local_name = require_portable_identifier(identifier, field_name=f"{section_name} declaration key")
    if section_name == "nodes" and len(local_name) > 35:
        raise ValueError("nodes declaration key must be at most 35 characters")


def _validate_section_declaration_keys(value: Mapping[object, object], *, allow_qualified: bool) -> None:
    for section_name in HASHMAP_SECTIONS:
        declarations = value.get(section_name)
        if not isinstance(declarations, Mapping):
            continue
        for identifier in declarations:
            _validate_declaration_identifier(
                identifier,
                section_name=section_name,
                allow_qualified=allow_qualified,
            )


def _forwarding_agent_identifier(agent: object) -> object:
    if isinstance(agent, RuntimeForwardingAgent):
        return agent.forwarding_agent_id
    if isinstance(agent, Mapping):
        return agent.get("forwarding_agent_id")
    return None


def _validate_forwarding_agent_identifiers(
    agents: object,
    *,
    allow_qualified: bool,
    field_name: str,
) -> None:
    if not isinstance(agents, (list, tuple)):
        return
    for agent in agents:
        identifier = _forwarding_agent_identifier(agent)
        if allow_qualified:
            QualifiedName.parse(identifier)
        else:
            require_portable_identifier(identifier, field_name=field_name)


def _node_runtime(node: object) -> object | None:
    if isinstance(node, Node):
        return node.runtime
    if isinstance(node, Mapping):
        return node.get("runtime")
    return None


def _runtime_forwarding_agents(runtime: object) -> object:
    if isinstance(runtime, Mapping):
        return runtime.get("forwarding_agents", ())
    return getattr(runtime, "forwarding_agents", ())


def _validate_runtime_forwarding_agent_identifiers(value: Mapping[object, object]) -> None:
    nodes = value.get("nodes")
    if not isinstance(nodes, Mapping):
        return
    for node in nodes.values():
        runtime = _node_runtime(node)
        if runtime is None:
            continue
        _validate_forwarding_agent_identifiers(
            _runtime_forwarding_agents(runtime),
            allow_qualified=False,
            field_name="runtime forwarding_agent_id",
        )


class ModuleDescriptor(SDLModel):
    """Published module metadata for SDL composition."""

    id: str
    version: str
    parameters: list[PortableIdentifier] = Field(default_factory=list)
    exports: dict[str, list[str]] = Field(default_factory=dict)
    description: str = ""

    @model_validator(mode="after")
    def validate_descriptor(self) -> "ModuleDescriptor":
        require_module_identifier(self.id)
        if len(self.parameters) != len(set(self.parameters)):
            raise ValueError("module.parameters must be unique")
        for section, names in self.exports.items():
            if len(names) != len(set(names)):
                raise ValueError(f"module.exports.{section} entries must be unique")
        return self


class ImportDecl(SDLModel):
    """A module import expanded before full semantic validation."""

    source: str = ""
    path: str = ""
    namespace: str = ""
    version: str = "*"
    parameters: dict[PortableIdentifier, object] = Field(default_factory=dict)
    digest: str = ""

    @model_validator(mode="after")
    def validate_source_fields(self) -> "ImportDecl":
        if not self.source and not self.path:
            raise ValueError("Import requires either 'source' or deprecated 'path'")
        if self.source and self.path:
            raise ValueError("Import may specify only one of 'source' or 'path'")
        if not self.namespace:
            raise ValueError("Import requires an explicit namespace")
        require_portable_identifier(self.namespace, field_name="namespace")
        return self

    @property
    def normalized_source(self) -> str:
        if self.source:
            return self.source
        return f"local:{self.path}"


class ScenarioContent(LegacyClassificationGuard):
    """Executable SDL content shared by the closed document-phase types."""

    legacy_classification_fields = ("vulnerabilities",)

    _allows_qualified_declaration_keys: ClassVar[bool] = False

    # --- Identity ---
    name: PortableIdentifier
    version: str = "*"
    description: str = ""

    # OCR-derived topology and exercise-narrative sections.
    nodes: dict[str, Node] = Field(default_factory=dict)
    infrastructure: dict[str, InfraNode] = Field(default_factory=dict)
    features: dict[str, Feature] = Field(default_factory=dict)
    conditions: dict[str, Condition] = Field(default_factory=dict)
    propositions: dict[str, Proposition] = Field(default_factory=dict)
    assertions: dict[str, Assertion] = Field(default_factory=dict)
    entities: dict[str, Entity] = Field(default_factory=dict)
    injects: dict[str, Inject] = Field(default_factory=dict)
    events: dict[str, Event] = Field(default_factory=dict)
    scripts: dict[str, Script] = Field(default_factory=dict)
    stories: dict[str, Story] = Field(default_factory=dict)

    # --- Extended sections ---
    content: dict[str, Content] = Field(default_factory=dict)
    generated_artifacts: dict[str, GeneratedArtifact] = Field(default_factory=dict)
    persistent_volumes: dict[str, PersistentVolume] = Field(default_factory=dict)
    accounts: dict[str, Account] = Field(default_factory=dict)
    identity_domains: dict[str, IdentityDomain] = Field(default_factory=dict)
    identity_forests: dict[str, IdentityForest] = Field(default_factory=dict)
    identity_facades: dict[str, IdentityFacade] = Field(default_factory=dict)
    deployment_tenants: dict[str, DeploymentTenant] = Field(default_factory=dict)
    deployment_cells: dict[str, DeploymentCell] = Field(default_factory=dict)
    relationships: dict[str, Relationship] = Field(default_factory=dict)
    forwarding_agents: list[RuntimeForwardingAgent] = Field(default_factory=list)
    agents: dict[str, Agent] = Field(default_factory=dict)
    action_contracts: dict[str, ParticipantActionContract] = Field(default_factory=dict)
    observation_boundaries: dict[str, ParticipantObservationBoundary] = Field(default_factory=dict)
    outcome_interpretation_rules: dict[str, OutcomeInterpretationRule] = Field(default_factory=dict)
    behavior_specifications: dict[str, ParticipantBehaviorSpecification] = Field(default_factory=dict)
    evidence_requirements: dict[str, EvidenceRequirement] = Field(default_factory=dict)
    time_domains: dict[str, TimeDomain] = Field(default_factory=dict)
    clocks: dict[str, Clock] = Field(default_factory=dict)
    time_domain_mappings: dict[str, TimeDomainMapping] = Field(default_factory=dict)
    time_progression_policies: dict[str, TimeProgressionPolicy] = Field(default_factory=dict)
    temporal_constraints: dict[str, TemporalConstraint] = Field(default_factory=dict)
    objectives: dict[str, Objective] = Field(default_factory=dict)
    workflows: dict[str, Workflow] = Field(default_factory=dict)
    _advisories: list[str] = PrivateAttr(default_factory=list)
    _source_diagnostics: tuple[SDLParseDiagnostic, ...] = PrivateAttr(default=())
    _semantic_validated: bool = PrivateAttr(default=False)
    _explicitness: dict[str, ExplicitnessRecord] = PrivateAttr(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _validate_declaration_keys(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        allow_qualified = cls._allows_qualified_declaration_keys
        _validate_section_declaration_keys(value, allow_qualified=allow_qualified)
        _validate_forwarding_agent_identifiers(
            value.get("forwarding_agents", ()),
            allow_qualified=allow_qualified,
            field_name="forwarding_agent_id",
        )
        _validate_runtime_forwarding_agent_identifiers(value)
        return value

    @property
    def advisories(self) -> list[str]:
        """Non-fatal SDL advisories gathered during semantic validation."""
        return list(self._advisories)

    def _set_advisories(self, advisories: list[str]) -> None:
        self._advisories = list(advisories)

    @property
    def source_diagnostics(self) -> tuple[SDLParseDiagnostic, ...]:
        """Non-fatal source migration diagnostics retained after parsing."""
        return self._source_diagnostics

    def _set_source_diagnostics(self, diagnostics: list[SDLParseDiagnostic]) -> None:
        self._source_diagnostics = tuple(diagnostics)

    @property
    def semantic_validated(self) -> bool:
        """Whether full semantic validation has already run on this scenario."""
        return self._semantic_validated

    def _set_semantic_validated(self, validated: bool) -> None:
        self._semantic_validated = bool(validated)

    @property
    def explicitness(self) -> dict[str, ExplicitnessRecord]:
        """SEM-218 explicitness records keyed by SDL model path."""
        return dict(self._explicitness)

    def _set_explicitness(self, explicitness: dict[str, ExplicitnessRecord]) -> None:
        self._explicitness = dict(explicitness)


class Scenario(ScenarioContent):
    """Normalized SDL authoring object.

    This model applies after ``sdl-yaml/v1`` source-profile checks, structural
    key canonicalization, shorthand expansion, enum normalization, and typed
    construction, but before module expansion and instantiation. Its JSON
    Schema does not validate YAML presentation details.
    """

    model_config = ConfigDict(
        title="SDL Normalized Authoring Object v1",
        json_schema_extra={
            "x-raes-document-phase": "normalized-authoring-object",
            "x-raes-source-profile": "sdl-yaml/v1",
            "x-raes-validates-raw-source": False,
        },
    )

    module: ModuleDescriptor | None = None
    imports: list[ImportDecl] = Field(default_factory=list)
    realization: RealizationDesignation | None = Field(
        default=None,
        json_schema_extra={"x-raes-realization-dimension": False},
    )
    variables: VariableDefinitions = Field(
        default_factory=dict,
        json_schema_extra={"additionalProperties": False},
    )
    variation_points: dict[str, VariationPoint] = Field(default_factory=dict)

    @property
    def module_variable_specs(self) -> dict[str, dict[str, object]]:
        return {}

    @property
    def module_node_variable_refs(self) -> dict[str, dict[str, str | None]]:
        return {}


class ExpandedScenario(ScenarioContent):
    """Internal authoring object after trusted import expansion."""

    _allows_qualified_declaration_keys: ClassVar[bool] = True

    model_config = ConfigDict(
        title="SDL Expanded Authoring Object v1",
        json_schema_extra={"x-raes-document-phase": "expanded-authoring-object"},
    )

    variables: dict[str, Variable] = Field(
        default_factory=dict,
        json_schema_extra={"additionalProperties": False},
    )
    variation_points: dict[str, VariationPoint] = Field(default_factory=dict)
    expansion_provenance: ExpansionProvenance = Field(default_factory=ExpansionProvenance)

    @property
    def module_variable_specs(self) -> dict[str, dict[str, object]]:
        """Compatibility projection of imported allowed-value constraints."""
        return _constraint_variable_specs(self.expansion_provenance.capability_constraints)

    @property
    def module_node_variable_refs(self) -> dict[str, dict[str, str | None]]:
        """Compatibility projection retained until compiler migration completes."""
        return _constraint_node_refs(self.expansion_provenance.capability_constraints)

    @property
    def module_namespaces(self) -> dict[str, str]:
        return {record.resolved_source: ".".join(record.namespace) for record in self.expansion_provenance.imports}


class InstantiatedScenario(ScenarioContent):
    """Scenario with all ``${var}`` references resolved to concrete values.

    Unlike the authoring-input contract, an instantiated scenario MUST NOT
    contain any unresolved ``${name}`` substitution token in any string value,
    whether a whole-string placeholder (``"${os}"``) or embedded
    (``"host-${index}"``). The invariant is enforced both by the model
    validator below and by the published ``instantiated-scenario-v1`` JSON
    Schema, which forbids the token in every string field. The schema is
    If a resolved variable value itself introduces a literal ``${name}``
    sequence, the single-pass substitution step does not interpret it as a
    second substitution request; final model admission still treats the result
    as non-concrete and rejects the public instantiation.
    """

    _allows_qualified_declaration_keys: ClassVar[bool] = True

    model_config = ConfigDict(
        title="SDL Instantiated Scenario v1",
        json_schema_extra={
            "x-raes-document-phase": "instantiated-scenario",
            "x-raes-authored-identity-profile": "raes-sdl-semantic/v1",
        },
    )

    instantiation_provenance: InstantiationProvenance = Field(
        json_schema_extra={"x-raes-realization-dimension": False},
    )

    @property
    def explicitness(self) -> dict[str, ExplicitnessRecord]:
        """Portable SEM-218 records keyed by SDL model path."""

        return {
            record.model_path: ExplicitnessRecord(
                path=record.model_path,
                classification=record.classification,
                provenance=record.provenance,
                reason=record.reason,
                variables=tuple(".".join(parameter) for parameter in record.parameters),
            )
            for record in self.instantiation_provenance.explicitness
        }

    @model_validator(mode="after")
    def _reject_unresolved_variable_references(self) -> "InstantiatedScenario":
        payload = self.model_dump(mode="json", by_alias=True)
        tokens = sorted(set(collect_variable_tokens(payload)))
        if tokens:
            joined = ", ".join(tokens)
            raise ValueError(f"InstantiatedScenario must not contain unresolved variable references: {joined}")
        binding_values = {binding.parameter: binding.value for binding in self.instantiation_provenance.bindings}
        for imported in self.instantiation_provenance.imports:
            for binding in imported.bindings:
                binding_values[(*imported.namespace, *binding.parameter)] = binding.value
        for constraint in self.instantiation_provenance.capability_constraints:
            try:
                concrete_value = resolve_json_pointer(payload, constraint.field_pointer)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Capability constraint field_pointer does not resolve: {constraint.field_pointer}"
                ) from exc
            if constraint.parameter not in binding_values:
                raise ValueError("Capability constraint references an unresolved parameter identity")
            if not _json_value_equal(concrete_value, binding_values[constraint.parameter]):
                raise ValueError("Capability constraint binding does not match the concrete field value")
        return self
