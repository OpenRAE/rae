"""Portable typed domain-profile contracts and pure offline admission.

The public surface is collected here while its implementation stays split by
contract definition, exact resolution, inert schema validation, and binding
admission. Profile documents remain data: this module performs no discovery,
network access, handler loading, or backend invocation.
"""

from ._domain_profile_admission import (
    DomainProfileAdmissionReport,
    DomainProfileBindingAdmission,
    admit_domain_profile_bindings,
)
from ._domain_profile_contracts import (
    AdmittedDomainProfileDefinitionModel,
    DomainProfileAdmissionOutcome,
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingOwnerModel,
    DomainProfileBindingProvenanceModel,
    DomainProfileBindingUse,
    DomainProfileCoordinateModel,
    DomainProfileDefinitionDraftModel,
    DomainProfileDefinitionModel,
    DomainProfileDefinitionProvenanceModel,
    DomainProfileIdentityModel,
    DomainProfileLimitsModel,
    DomainProfileNamespaceAdmissionModel,
    DomainProfileOperation,
    DomainProfileResolutionContextModel,
    DomainProfileResolutionOutcome,
    DomainProfileSchemaModel,
    DomainProfileSemanticContractModel,
    DomainProfileSupportDeclarationModel,
    canonical_domain_profile_definition_digest,
    draft_domain_profile_definition,
    seal_domain_profile_definition,
)
from ._domain_profile_resolution import (
    DomainProfileDefinitionResolution,
    resolve_domain_profile_definition,
)
from ._domain_profile_validation import (
    SAFE_DOMAIN_PROFILE_SCHEMA_KEYWORDS,
    parse_domain_profile_binding,
)

__all__ = [
    "AdmittedDomainProfileDefinitionModel",
    "DomainProfileAdmissionOutcome",
    "DomainProfileAdmissionPolicyModel",
    "DomainProfileAdmissionReport",
    "DomainProfileBindingAdmission",
    "DomainProfileBindingBasis",
    "DomainProfileBindingModel",
    "DomainProfileBindingOwnerModel",
    "DomainProfileBindingProvenanceModel",
    "DomainProfileBindingUse",
    "DomainProfileCoordinateModel",
    "DomainProfileDefinitionDraftModel",
    "DomainProfileDefinitionModel",
    "DomainProfileDefinitionProvenanceModel",
    "DomainProfileDefinitionResolution",
    "DomainProfileIdentityModel",
    "DomainProfileLimitsModel",
    "DomainProfileNamespaceAdmissionModel",
    "DomainProfileOperation",
    "DomainProfileResolutionContextModel",
    "DomainProfileResolutionOutcome",
    "DomainProfileSchemaModel",
    "DomainProfileSemanticContractModel",
    "DomainProfileSupportDeclarationModel",
    "SAFE_DOMAIN_PROFILE_SCHEMA_KEYWORDS",
    "admit_domain_profile_bindings",
    "canonical_domain_profile_definition_digest",
    "draft_domain_profile_definition",
    "parse_domain_profile_binding",
    "resolve_domain_profile_definition",
    "seal_domain_profile_definition",
]
