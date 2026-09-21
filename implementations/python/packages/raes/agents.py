"""Agent models — role-neutral participants in the scenario.

Adapted from CybORG's Agents section. An agent has a role, optional
organizational affiliations, available actions, initial authenticated access (via
accounts), initial knowledge of the environment, and network
scope constraints.

The SDL specifies *what's available* to each agent, not *how*
the agent executes. Framework bindings (Gymnasium, PettingZoo)
are a deployment-layer concern.

The ``Agent`` model is the SDL-authoring surface for declarative
participant framing (ACT-601, ADR-020). Its declaration key is its identity.
An explicit role takes precedence over single-affiliation role inheritance; starting conditions
combine ``starting_accounts``/``initial_knowledge``/``starting_assertions``,
authority anchors point at declared SDL elements, and operating scope
combines ``allowed_subnets`` with the broader ``operating_scope`` list.
"""

from collections.abc import Mapping
from enum import Enum

from pydantic import Field, field_validator, model_validator
from raes_contracts.domain_profiles import DomainProfileBindingModel

from ._base import SDLModel, WholeFieldVariableReference, is_variable_ref, parse_enum_or_var
from ._identifiers import PortableIdentifier
from .entities import Entity, ExerciseRole
from .profile_selections import parse_profile_or_enum


class ParticipantInteractiveAccessChannel(str, Enum):
    """Portable classes of authored participant interactive access."""

    SSH = "ssh"
    RDP = "rdp"


class ParticipantInteractiveAccess(SDLModel):
    """One authored participant-to-compute-node interactive-access binding.

    This record carries portable intent only. It is not a host locator, port,
    credential, portal session, listener observation, or realization claim.
    """

    target_ref: str = Field(min_length=1)
    channel: ParticipantInteractiveAccessChannel | DomainProfileBindingModel | WholeFieldVariableReference
    account_ref: str | None = Field(default=None, min_length=1)

    @field_validator("channel", mode="before")
    @classmethod
    def parse_channel(cls, value: object) -> ParticipantInteractiveAccessChannel | str:
        return parse_profile_or_enum(
            value,
            ParticipantInteractiveAccessChannel,
            field_name="channel",
        )


class InitialKnowledge(SDLModel):
    """What an agent knows about the scenario at start time.

    Adapted from CybORG's INT (Initial Network Topology).
    Specifies which hosts, subnets, services, and accounts
    the agent has knowledge of before the scenario begins.
    """

    hosts: list[str] = Field(default_factory=list)
    subnets: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    accounts: list[str] = Field(default_factory=list)


class Agent(SDLModel):
    """A role-neutral participant in the scenario.

    Agents reference existing scenario elements:

    - ``affiliations`` links to entities without conferring identity or authority
    - ``role`` explicitly selects an exercise role, overriding inherited role
    - ``starting_accounts`` links to the accounts section
    - ``allowed_subnets`` links to infrastructure entries
    - ``initial_knowledge`` references nodes and infrastructure
    - ``starting_assertions`` links to precondition assertions, giving the
      authoring surface a declarative hook for participant-relevant starting
      state without equating a probe implementation with truth (ACT-601)
    - ``authority_anchors`` links to declared SDL elements (entities,
      relationships, content, etc.) that anchor what the participant is
      allowed or expected to do in scenario meaning (ACT-601, ADR-020)
    - ``operating_scope`` links to targetable named scenario elements
      (subnets, hosts, services, content) defining where the participant
      may act or observe (ACT-601, ADR-020)
    - ``observation_boundaries`` links to declared participant observation
      boundaries that define participant-specific projections of world and
      evidence state (SEM-208)
    - ``interactive_access`` declares the compute-node/channel pairs that may be offered
      to this participant, without inferring a listener, locator, credential,
      operating scope, action authority, or successful realization (DSL-117)

    Per ADR-073 the CybORG-inherited ``reward_calculator`` label was removed;
    it was an unbound, unvalidated string and graded reward lives in the
    experiment/evaluator plane (ADR-055/064/069).
    """

    affiliations: list[str] = Field(default_factory=list)
    role: ExerciseRole | WholeFieldVariableReference | None = None
    description: str = ""
    actions: list[str] = Field(default_factory=list)
    starting_accounts: list[str] = Field(default_factory=list)
    initial_knowledge: InitialKnowledge | None = None
    allowed_subnets: list[str] = Field(default_factory=list)
    starting_assertions: list[str] = Field(default_factory=list)
    authority_anchors: list[str] = Field(default_factory=list)
    operating_scope: list[str] = Field(default_factory=list)
    observation_boundaries: list[str] = Field(default_factory=list)
    interactive_access: dict[PortableIdentifier, ParticipantInteractiveAccess] = Field(
        default_factory=dict,
        json_schema_extra={"additionalProperties": False},
    )

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value: object) -> object:
        return parse_enum_or_var(value, ExerciseRole, field_name="role")

    def effective_role(self, entities: Mapping[str, Entity]) -> str | None:
        """Resolve explicit role, then exactly one affiliation; never pick a team."""
        role = self.role
        if role is None and len(self.affiliations) == 1:
            affiliation = self.affiliations[0]
            if is_variable_ref(affiliation):
                return affiliation
            role = getattr(entities.get(affiliation), "role", None)
        return str(getattr(role, "value", role)) if role is not None else None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_starting_conditions(cls, value: object) -> object:
        if isinstance(value, dict) and "entity" in value:
            raise ValueError(
                "agent.entity was replaced by affiliations; use migrate_participant_identity "
                "(docs/migration/participant-identity.md)"
            )
        if isinstance(value, dict) and "starting_conditions" in value:
            raise ValueError(
                "agent starting_conditions cannot state backend-neutral truth; "
                "reference precondition assertions via starting_assertions"
            )
        return value
