"""Participant behavior contract models (SEM-208, SEM-209, SEM-210).

The legacy ``agents.*.actions`` list remains the authoring reference list.
These models provide the governed source of truth those names resolve to when
an SDL document declares explicit participant behavior semantics.

This package is a thin facade over cohesive subdomains:

* :mod:`._action_contracts` - action-argument domains, the interaction
  declaration, and the governed :class:`ParticipantActionContract`.
* :mod:`._view_boundaries` - view rules/transitions and the
  :class:`ParticipantObservationBoundary` projection.

The shared action vocabulary, including ``ParticipantInteractionClass``, is
owned by :mod:`raes_contracts.participant_action_semantics` (ADR-121). The
temporal names are re-exported from :mod:`raes.participant_temporal_semantics`.
"""

from ..participant_temporal_semantics import (
    ParticipantBackendTimingDisclosure,
    ParticipantTemporalContract,
    validate_action_contract_temporal_payload,
)
from ._action_contracts import (
    ExternalMappingLoss,
    ParticipantActionArgumentAuthoredValue,
    ParticipantActionArgumentCardinality,
    ParticipantActionArgumentDefinition,
    ParticipantActionArgumentNormalization,
    ParticipantActionArgumentOmission,
    ParticipantActionArgumentScalar,
    ParticipantActionArgumentValueType,
    ParticipantActionContract,
    ParticipantActionGranularity,
    ParticipantActionLifecycle,
    ParticipantInteractionDeclaration,
)
from ._view_boundaries import (
    ParticipantInformationBoundaryClass,
    ParticipantObservationBoundary,
    ParticipantViewDisposition,
    ParticipantViewHistoryEventType,
    ParticipantViewRule,
    ParticipantViewTransition,
    ParticipantViewTransitionKind,
)
