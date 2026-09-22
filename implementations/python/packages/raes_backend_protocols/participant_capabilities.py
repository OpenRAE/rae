"""Participant-runtime capability declarations and evidence requirements."""

from dataclasses import dataclass, field

from pydantic import TypeAdapter
from raes_contracts.addressing import require_compiled_address
from raes_contracts.contracts.participant_execution import ParticipantExecutionBindingModel
from raes_contracts.controlled_vocabularies import validate_controlled_vocabulary_scope_values
from raes_contracts.manifest_authority import (
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_POLICY_FEATURES,
    PARTICIPANT_RUNTIME_ROLE_SCOPE,
)
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

from .participant_resource_budgets import ParticipantResourceBudgetCapabilities

PARTICIPANT_EXECUTION_CONTROL_ACTIONS = frozenset({"start", "pause", "resume", "drain", "reset", "teardown"})


def _validate_unique_non_empty_strings(field_name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain empty strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must not contain duplicate values")


def _validate_participant_feature_support_term(feature: str) -> None:
    errors: list[str] = []
    for scope in (PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE, PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE):
        try:
            validate_controlled_vocabulary_scope_values(scope, (feature,))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        return
    raise ValueError(
        "ParticipantFeatureSupport.feature must be a governed participant behavior or interaction feature "
        f"term, or match the governed extension pattern; got {feature!r}; "
        f"validation details: {'; '.join(errors)}"
    )


def _participant_feature_support_level(
    value: ParticipantFeatureSupportLevel | str,
) -> ParticipantFeatureSupportLevel:
    try:
        if isinstance(value, ParticipantFeatureSupportLevel):
            return value
        return ParticipantFeatureSupportLevel(str(value))
    except ValueError as exc:
        raise ValueError("ParticipantFeatureSupport.support_level must be a valid support level") from exc


def _participant_feature_refs(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(values)
    _validate_unique_non_empty_strings(f"ParticipantFeatureSupport.{field_name}", normalized)
    return normalized


def _validate_participant_feature_evidence(
    *,
    feature: str,
    support_level: ParticipantFeatureSupportLevel,
    constraint_refs: tuple[str, ...],
    limitation_refs: tuple[str, ...],
    disclosure_refs: tuple[str, ...],
    evidence_refs: tuple[str, ...],
) -> None:
    if support_level != ParticipantFeatureSupportLevel.EXACT and not disclosure_refs:
        raise ValueError(
            "ParticipantFeatureSupport disclosure_refs must be non-empty when support_level is below exact"
        )
    if feature not in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES:
        return
    if support_level != ParticipantFeatureSupportLevel.EXACT and not limitation_refs:
        raise ValueError("ParticipantFeatureSupport limitation_refs must be non-empty for below-exact policy support")
    if support_level == ParticipantFeatureSupportLevel.BOUNDED and not constraint_refs:
        raise ValueError("ParticipantFeatureSupport constraint_refs must be non-empty for bounded policy support")
    if support_level != ParticipantFeatureSupportLevel.UNSUPPORTED and not evidence_refs:
        raise ValueError("ParticipantFeatureSupport evidence_refs must be non-empty for positive policy support")


@dataclass(frozen=True)
class ParticipantFeatureSupport:
    """API-407 per-feature participant runtime support declaration."""

    feature: str
    support_level: ParticipantFeatureSupportLevel | str
    constraint_refs: tuple[str, ...] = ()
    limitation_refs: tuple[str, ...] = ()
    disclosure_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.feature.strip():
            raise ValueError("ParticipantFeatureSupport.feature must be non-empty")
        _validate_participant_feature_support_term(self.feature)
        support_level = _participant_feature_support_level(self.support_level)
        constraint_refs = _participant_feature_refs("constraint_refs", self.constraint_refs)
        limitation_refs = _participant_feature_refs("limitation_refs", self.limitation_refs)
        disclosure_refs = _participant_feature_refs("disclosure_refs", self.disclosure_refs)
        evidence_refs = _participant_feature_refs("evidence_refs", self.evidence_refs)
        _validate_participant_feature_evidence(
            feature=self.feature,
            support_level=support_level,
            constraint_refs=constraint_refs,
            limitation_refs=limitation_refs,
            disclosure_refs=disclosure_refs,
            evidence_refs=evidence_refs,
        )
        object.__setattr__(self, "support_level", support_level)
        object.__setattr__(self, "constraint_refs", constraint_refs)
        object.__setattr__(self, "limitation_refs", limitation_refs)
        object.__setattr__(self, "disclosure_refs", disclosure_refs)
        object.__setattr__(self, "evidence_refs", evidence_refs)


@dataclass(frozen=True)
class ParticipantExecutionBinding:
    """Manifest claim for one exact action-to-target native binding."""

    binding_id: str
    action_contract_address: str
    target_addresses: tuple[str, ...]
    participant_implementation_ref: str
    constraint_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    max_action_attempts: int
    max_in_flight: int
    timeout_seconds: int
    max_retries: int
    temporal_contract_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "binding_id",
            "action_contract_address",
            "participant_implementation_ref",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"ParticipantExecutionBinding.{field_name} must be non-empty")
        for field_name in ("target_addresses", "constraint_refs", "evidence_refs"):
            values = tuple(getattr(self, field_name))
            if not values:
                raise ValueError(f"ParticipantExecutionBinding.{field_name} must not be empty")
            _validate_unique_non_empty_strings(
                f"ParticipantExecutionBinding.{field_name}",
                values,
            )
            object.__setattr__(self, field_name, values)
        require_compiled_address(
            self.action_contract_address,
            field_name="action_contract_address",
        )
        for target_address in self.target_addresses:
            require_compiled_address(
                target_address,
                field_name="target_addresses",
            )
        for field_name in (
            "max_action_attempts",
            "max_in_flight",
            "timeout_seconds",
        ):
            if getattr(self, field_name) < 1:
                raise ValueError(f"ParticipantExecutionBinding.{field_name} must be positive")
        if self.max_retries < 0:
            raise ValueError("ParticipantExecutionBinding.max_retries must be non-negative")
        digest_field = ParticipantExecutionBindingModel.model_fields["temporal_contract_digests"]
        digests = TypeAdapter(digest_field.rebuild_annotation()).validate_python(self.temporal_contract_digests)
        _validate_unique_non_empty_strings("ParticipantExecutionBinding.temporal_contract_digests", digests)
        object.__setattr__(self, "temporal_contract_digests", digests)


@dataclass(frozen=True)
class ParticipantRuntimeCapabilities:
    """Backend participant lifecycle, behavior, and execution support."""

    name: str
    supported_participant_roles: frozenset[str] = frozenset()
    supported_behavior_features: frozenset[str] = frozenset()
    supported_interaction_features: frozenset[str] = frozenset()
    feature_support: tuple[ParticipantFeatureSupport, ...] = ()
    supports_autonomous_execution: bool = False
    supported_autonomous_selection_strategies: frozenset[str] = frozenset()
    supported_autonomous_action_contracts: frozenset[str] = frozenset()
    supported_autonomous_observation_boundaries: frozenset[str] = frozenset()
    supported_autonomous_target_addresses: frozenset[str] = frozenset()
    supported_autonomous_policy_profiles: frozenset[str] = frozenset()
    supported_autonomous_activity_features: frozenset[str] = frozenset()
    supported_autonomous_random_stream_profiles: frozenset[str] = frozenset()
    max_autonomous_participants: int | None = None
    max_autonomous_action_attempts: int | None = None
    max_autonomous_in_flight: int | None = None
    max_autonomous_occurrences: int | None = None
    max_autonomous_retries_per_occurrence: int | None = None
    max_autonomous_burst_size: int | None = None
    execution_bindings: tuple[ParticipantExecutionBinding, ...] = ()
    supports_execution_control: bool = False
    supported_execution_control_actions: frozenset[str] = frozenset()
    supports_bounded_concurrency: bool = False
    max_execution_services: int | None = None
    max_concurrent_actions: int | None = None
    resource_budgets: ParticipantResourceBudgetCapabilities | None = None
    constraints: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("ParticipantRuntimeCapabilities.name must be non-empty")
        self._validate_required_vocabularies()
        feature_support = self._normalize_feature_support()
        self._validate_feature_support(feature_support)
        execution_bindings = tuple(
            binding if isinstance(binding, ParticipantExecutionBinding) else ParticipantExecutionBinding(**binding)
            for binding in self.execution_bindings
        )
        object.__setattr__(self, "execution_bindings", execution_bindings)
        self._validate_autonomous_execution()
        object.__setattr__(self, "feature_support", feature_support)

    def _validate_required_vocabularies(self) -> None:
        for field_name, values in (
            ("supported_participant_roles", self.supported_participant_roles),
            ("supported_behavior_features", self.supported_behavior_features),
            ("supported_interaction_features", self.supported_interaction_features),
        ):
            if any(not value.strip() for value in values):
                raise ValueError(f"ParticipantRuntimeCapabilities.{field_name} must not contain empty strings")
        validate_controlled_vocabulary_scope_values(
            PARTICIPANT_RUNTIME_ROLE_SCOPE,
            self.supported_participant_roles,
        )
        validate_controlled_vocabulary_scope_values(
            PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
            self.supported_behavior_features,
        )
        validate_controlled_vocabulary_scope_values(
            PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE,
            self.supported_interaction_features,
        )

    def _normalize_feature_support(self) -> tuple[ParticipantFeatureSupport, ...]:
        return tuple(
            entry if isinstance(entry, ParticipantFeatureSupport) else ParticipantFeatureSupport(**entry)
            for entry in self.feature_support
        )

    def _validate_feature_support(self, feature_support: tuple[ParticipantFeatureSupport, ...]) -> None:
        feature_names = tuple(entry.feature for entry in feature_support)
        _validate_unique_non_empty_strings("ParticipantRuntimeCapabilities.feature_support", feature_names)
        supported_features = self.supported_behavior_features | self.supported_interaction_features
        missing_policy_declarations = sorted(
            (supported_features & PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES) - set(feature_names)
        )
        if missing_policy_declarations:
            raise ValueError(
                "ParticipantRuntimeCapabilities supported participant policy features require explicit "
                f"feature_support declarations: {', '.join(missing_policy_declarations)}"
            )
        for entry in feature_support:
            if (
                entry.support_level == ParticipantFeatureSupportLevel.UNSUPPORTED
                and entry.feature in supported_features
            ):
                raise ValueError(
                    "ParticipantRuntimeCapabilities.feature_support cannot declare a supported feature unsupported"
                )
            if (
                entry.feature in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES
                and entry.support_level != ParticipantFeatureSupportLevel.UNSUPPORTED
                and entry.feature not in supported_features
            ):
                raise ValueError(
                    "ParticipantRuntimeCapabilities positive support for a participant policy feature "
                    "requires the feature in supported_behavior_features"
                )

    def _validate_autonomous_execution(self) -> None:
        declares_autonomous = "autonomous_execution" in self.supported_behavior_features
        if declares_autonomous != self.supports_autonomous_execution:
            raise ValueError("ParticipantRuntimeCapabilities autonomous_execution feature and support flag must agree")
        if self.supports_autonomous_execution:
            self._validate_enabled_autonomous_execution()
        elif self._has_autonomous_configuration():
            raise ValueError("autonomous execution limits require autonomous execution support")

    def _validate_enabled_autonomous_execution(self) -> None:
        if not self.supported_autonomous_selection_strategies:
            raise ValueError("autonomous execution requires supported selection strategies")
        unknown_strategies = sorted(self.supported_autonomous_selection_strategies - {"ordered_cycle", "weighted"})
        if unknown_strategies:
            raise ValueError("unsupported autonomous selection strategies: " + ", ".join(unknown_strategies))
        if not self.supported_autonomous_action_contracts:
            raise ValueError("autonomous execution requires exact supported action contracts")
        if not self.supported_autonomous_observation_boundaries:
            raise ValueError("autonomous execution requires exact supported observation boundaries")
        if not self.supported_autonomous_policy_profiles:
            raise ValueError("autonomous execution requires exact supported policy profiles")
        self._validate_activity_profiles()
        self._validate_autonomous_addresses()
        self._validate_execution_control()
        for label, value in self._autonomous_limits():
            minimum = 0 if label == "max_autonomous_retries_per_occurrence" else 1
            if value is None or value < minimum:
                raise ValueError(f"autonomous execution requires {label} >= {minimum}")

    def _validate_activity_profiles(self) -> None:
        if {
            "participant-autonomous-execution/v2",
            "participant-autonomous-execution/v3",
        }.intersection(self.supported_autonomous_policy_profiles):
            if not self.supported_autonomous_activity_features:
                raise ValueError("autonomous execution v2/v3 requires exact supported activity features")
            if not self.supported_autonomous_random_stream_profiles:
                raise ValueError("autonomous execution v2/v3 requires exact supported random-stream profiles")
        if (
            "participant-autonomous-execution/v3" in self.supported_autonomous_policy_profiles
            and self.resource_budgets is None
        ):
            raise ValueError("autonomous execution v3 requires participant resource-budget capabilities")

    def _validate_execution_control(self) -> None:
        self._validate_execution_control_actions()
        self._validate_execution_capacity()
        self._validate_execution_bindings()

    def _validate_execution_control_actions(self) -> None:
        if self.supports_execution_control != bool(self.supported_execution_control_actions):
            raise ValueError("execution control support flag and supported actions must agree")
        unknown_actions = self.supported_execution_control_actions - PARTICIPANT_EXECUTION_CONTROL_ACTIONS
        if unknown_actions:
            raise ValueError("unsupported execution control actions: " + ", ".join(sorted(unknown_actions)))

    def _validate_execution_capacity(self) -> None:
        if self.supports_execution_control and (self.max_execution_services is None or self.max_execution_services < 1):
            raise ValueError("execution control requires positive max_execution_services")
        if self.max_concurrent_actions is None or self.max_concurrent_actions < 1:
            raise ValueError("autonomous execution requires positive max_concurrent_actions")
        if self.supports_bounded_concurrency and self.max_concurrent_actions < 2:
            raise ValueError("bounded concurrency requires max_concurrent_actions of at least 2")

    def _validate_execution_bindings(self) -> None:
        if not self.execution_bindings:
            raise ValueError("autonomous execution requires relational execution_bindings")
        binding_ids = tuple(binding.binding_id for binding in self.execution_bindings)
        _validate_unique_non_empty_strings(
            "ParticipantRuntimeCapabilities.execution_bindings",
            binding_ids,
        )
        for binding in self.execution_bindings:
            if binding.action_contract_address not in self.supported_autonomous_action_contracts:
                raise ValueError("execution binding action is not declared supported")
            if not set(binding.target_addresses).issubset(self.supported_autonomous_target_addresses):
                raise ValueError("execution binding target is not declared supported")
            if binding.max_in_flight > self.max_concurrent_actions:
                raise ValueError("execution binding exceeds max_concurrent_actions")

    def _validate_autonomous_addresses(self) -> None:
        for field_name, addresses in (
            ("supported_autonomous_action_contracts", self.supported_autonomous_action_contracts),
            ("supported_autonomous_observation_boundaries", self.supported_autonomous_observation_boundaries),
            ("supported_autonomous_target_addresses", self.supported_autonomous_target_addresses),
        ):
            for address in addresses:
                require_compiled_address(address, field_name=field_name)

    def _autonomous_limits(self) -> tuple[tuple[str, int | None], ...]:
        return (
            ("max_autonomous_participants", self.max_autonomous_participants),
            ("max_autonomous_action_attempts", self.max_autonomous_action_attempts),
            ("max_autonomous_in_flight", self.max_autonomous_in_flight),
            ("max_autonomous_occurrences", self.max_autonomous_occurrences),
            ("max_autonomous_retries_per_occurrence", self.max_autonomous_retries_per_occurrence),
            ("max_autonomous_burst_size", self.max_autonomous_burst_size),
        )

    def _has_autonomous_configuration(self) -> bool:
        limits_configured = any(value is not None for _, value in self._autonomous_limits())
        return any(
            (
                self.supported_autonomous_selection_strategies,
                self.supported_autonomous_action_contracts,
                self.supported_autonomous_observation_boundaries,
                self.supported_autonomous_target_addresses,
                self.supported_autonomous_policy_profiles,
                self.supported_autonomous_activity_features,
                self.supported_autonomous_random_stream_profiles,
                self.execution_bindings,
                self.supports_execution_control,
                self.supported_execution_control_actions,
                self.supports_bounded_concurrency,
                self.max_execution_services is not None,
                self.max_concurrent_actions is not None,
                self.resource_budgets is not None,
                limits_configured,
            )
        )


__all__ = [
    "PARTICIPANT_EXECUTION_CONTROL_ACTIONS",
    "PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE",
    "PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS",
    "PARTICIPANT_RUNTIME_INTERACTION_FEATURE_SCOPE",
    "PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES",
    "PARTICIPANT_RUNTIME_POLICY_FEATURES",
    "PARTICIPANT_RUNTIME_ROLE_SCOPE",
    "ParticipantFeatureSupport",
    "ParticipantExecutionBinding",
    "ParticipantRuntimeCapabilities",
]
