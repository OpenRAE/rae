"""Public vocabulary used by external RAES contracts."""

from enum import Enum
from typing import Annotated

from pydantic import Field


class ProcessorFeature(str, Enum):
    """Processing features that a processor may support."""

    COMPILATION = "compilation"
    PLANNING = "planning"
    ORCHESTRATION_COORDINATION = "orchestration-coordination"
    EVALUATION_COORDINATION = "evaluation-coordination"
    WORKFLOW_SEMANTICS = "workflow-semantics"
    OBJECTIVE_WINDOW_CONSISTENCY = "objective-window-consistency"
    DEPENDENCY_ORDERING = "dependency-ordering"
    RUNTIME_CONTROL_PLANE = "runtime-control-plane"


class GeneratedArtifactKind(str, Enum):
    """Portable kinds of material a provisioner may generate."""

    CERTIFICATE_BUNDLE = "certificate_bundle"
    RENDERED_CONFIG = "rendered_config"
    SSH_KEY_BUNDLE = "ssh_key_bundle"
    RANDOM_VALUE = "random_value"


class GeneratedArtifactRegenerationScope(str, Enum):
    """When a ``random_value`` generated artifact is regenerated (issue #1276).

    Distinct from ``GeneratedArtifactLifecycle`` (change-driven reuse): scope
    governs *freshness*. ``per_run`` regenerates for each fresh authoritative run;
    ``per_instantiation`` regenerates for each distinct realized scenario instance;
    ``once`` binds a single generation to the backend-owned artifact-instance
    lifetime.
    """

    PER_RUN = "per_run"
    PER_INSTANTIATION = "per_instantiation"
    ONCE = "once"


class GeneratedArtifactDeliveryMode(str, Enum):
    """Portable ways a generated-artifact output is delivered to a consumer.

    ``mount`` is the read-only file projection declared directly on
    ``generated_artifacts[].consumers[]``. ``environment`` and ``env_file`` are
    node-owned runtime environment bindings authored on
    ``nodes.<node>.runtime.environment[]`` / ``environment_files[]`` whose
    generated-artifact consumer projection the compiler derives. A provisioner
    declares each mode it can realize separately so it cannot claim mount
    delivery while silently dropping environment or env-file injection.
    """

    MOUNT = "mount"
    ENVIRONMENT = "environment"
    ENV_FILE = "env_file"
    # A generated-artifact output rendered into a content placement's text at
    # backend materialization time (issue #1276). Authored on
    # ``content.<name>.text_from``; the compiler derives the consumer projection.
    CONTENT_TEXT = "content_text"


class WorkflowFeature(str, Enum):
    """Portable workflow control features that an orchestrator may support."""

    DECISION = "decision"
    SWITCH = "switch"
    RETRY = "retry"
    CALL = "call"
    PARALLEL_BARRIER = "parallel-barrier"
    FAILURE_TRANSITIONS = "failure-transitions"
    CANCELLATION = "cancellation"
    TIMEOUTS = "timeouts"
    COMPENSATION = "compensation"
    OBJECTIVE_STEPS = "objective-steps"
    SCAFFOLDED_STEPS = "scaffolded-steps"


class WorkflowStatePredicateFeature(str, Enum):
    """Portable workflow state-predicate features that an orchestrator may support."""

    OUTCOME_MATCHING = "outcome-matching"
    ATTEMPT_COUNTS = "attempt-counts"


class RealizationSupportMode(str, Enum):
    """How an apparatus can supply realizations for underspecified inputs."""

    EXACT_ONLY = "exact-only"
    CONSTRAINED = "constrained"
    OPEN_REALIZATION = "open-realization"


class ProcessResourceLimitKind(str, Enum):
    """Portable process-resource terms governed by the runtime contract."""

    OPEN_FILE_DESCRIPTORS = "open_file_descriptors"
    LOCKED_MEMORY_BYTES = "locked_memory_bytes"


class ProcessResourceLimitScope(str, Enum):
    """Process inheritance scope for a portable resource limit."""

    PROCESS = "process"
    SUBTREE = "subtree"


class ObservationStrength(str, Enum):
    """Strongest evidence a backend configuration emits for one concern."""

    NONE = "none"
    DRIVER_REPORTED = "driver-reported"
    DAEMON_OBSERVED = "daemon-observed"
    GUEST_OBSERVED = "guest-observed"


def observation_strength_satisfies(
    actual: ObservationStrength,
    required: ObservationStrength,
) -> bool:
    """Return whether an observation has the explicitly required source."""

    return actual is required


class RealizationVerificationScope(str, Enum):
    """Closed scope at which an inventory realization was corroborated."""

    PRESENCE = "presence"
    CONFIGURATION = "configuration"


def verification_scope_satisfies(
    actual: RealizationVerificationScope,
    required: RealizationVerificationScope,
) -> bool:
    """Return whether an observation covers the required inventory scope."""

    rank = {
        RealizationVerificationScope.PRESENCE: 0,
        RealizationVerificationScope.CONFIGURATION: 1,
    }
    return rank[actual] >= rank[required]


def observation_requirement_satisfied(
    *,
    actual_scope: RealizationVerificationScope,
    actual_source: ObservationStrength,
    required_scope: RealizationVerificationScope | None,
    required_source: ObservationStrength | None,
) -> bool:
    """Return whether one observation meets independent scope and source constraints."""

    source_satisfied = (
        observation_strength_satisfies(actual_source, required_source)
        if required_source is not None
        else actual_source in {ObservationStrength.DAEMON_OBSERVED, ObservationStrength.GUEST_OBSERVED}
    )
    return (required_scope is None or verification_scope_satisfies(actual_scope, required_scope)) and (source_satisfied)


class Closure(str, Enum):
    """Whether unspecified realizable dimensions under a scope are admitted."""

    OPEN_WORLD = "open-world"
    CLOSED_WORLD = "closed-world"


class ParticipantFeatureSupportLevel(str, Enum):
    """ADR-054 guarantee-strength scale for per-feature participant runtime support."""

    UNSUPPORTED = "unsupported"
    DISCLOSED_WEAK = "disclosed_weak"
    BOUNDED = "bounded"
    EXACT = "exact"


class ConceptProvenanceCategory(str, Enum):
    """How a concept family relates to its authority source."""

    ADOPTED = "adopted"
    ADAPTED = "adapted"
    NATIVE = "native"


class ExternalKnowledgeBindingEffect(str, Enum):
    """Portable SEM-217 effects a binding may claim about native RAES meaning."""

    ANNOTATES = "annotates"
    CONSTRAINS = "constrains"
    REFINES = "refines"
    ALIGNS = "aligns"


ConceptFamilyId = Annotated[
    str,
    Field(min_length=1, pattern=r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"),
]
"""Pattern-constrained concept family identifier matching the authoritative catalog key format."""
