"""Semantic validation for SDL scenarios (package split of the former
validator.py). Public API is unchanged: import ``SemanticValidator``.
"""

from ._accounts import _AccountsMixin
from ._content_objectives import _ContentObjectivesMixin
from ._core import _ValidatorCore
from ._deployment_tenancy import _DeploymentTenancyMixin
from ._domain_topology import _DomainTopologyMixin
from ._enterprise_identity import _EnterpriseIdentityMixin
from ._evidence_requirements import _EvidenceRequirementsMixin
from ._mixed_control import _MixedControlMixin
from ._nodes_infra_network import _NodesInfraNetworkMixin
from ._participant_inject_deliveries import _ParticipantInjectDeliveriesMixin
from ._participant_relationships import _ParticipantRelationshipsMixin
from ._participant_tool_affordances import _ParticipantToolAffordancesMixin
from ._propositions import _PropositionsMixin
from ._relationships import _RelationshipsMixin
from ._relationships_proxy import _RelationshipsProxyMixin
from ._runtime_identity_data import _RuntimeIdentityDataMixin
from ._runtime_mail import _RuntimeMailMixin
from ._runtime_orchestration import _RuntimeOrchestrationMixin
from ._runtime_platform import _RuntimePlatformMixin
from ._runtime_process_limits import _RuntimeProcessLimitsMixin
from ._runtime_services import _RuntimeServicesMixin
from ._sections import _SectionsMixin
from ._service_materialization import _ServiceMaterializationMixin
from ._time_model import _TimeModelMixin
from ._variation import _VariationMixin
from ._workflows_analysis import _WorkflowAnalysisMixin
from ._workflows_verify import _WorkflowVerifyMixin

__all__ = ["SemanticValidator"]


class SemanticValidator(
    _NodesInfraNetworkMixin,
    _RuntimeServicesMixin,
    _RuntimeProcessLimitsMixin,
    _RuntimeIdentityDataMixin,
    _RuntimePlatformMixin,
    _RuntimeOrchestrationMixin,
    _RuntimeMailMixin,
    _DomainTopologyMixin,
    _EnterpriseIdentityMixin,
    _DeploymentTenancyMixin,
    _RelationshipsMixin,
    _RelationshipsProxyMixin,
    _MixedControlMixin,
    _ParticipantInjectDeliveriesMixin,
    _ParticipantRelationshipsMixin,
    _ParticipantToolAffordancesMixin,
    _ServiceMaterializationMixin,
    _AccountsMixin,
    _ContentObjectivesMixin,
    _PropositionsMixin,
    _EvidenceRequirementsMixin,
    _WorkflowAnalysisMixin,
    _WorkflowVerifyMixin,
    _VariationMixin,
    _TimeModelMixin,
    _SectionsMixin,
    _ValidatorCore,
):
    """Validates executable SDL content beyond structural Pydantic checks.

    Call ``validate()`` to run all passes. Raises ``SDLValidationError``
    with all collected errors if any pass fails.
    """
