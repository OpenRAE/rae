package admission

// Shared names retain the owning contract vocabulary.
const (
	modelTrialInputRefs            = "AdmittedTrialPlanInputRefsModel"
	modelTrialApparatus            = "AdmittedApparatusBindingModel"
	modelTrialMixedApparatus       = "AdmittedMixedCompositionBindingModel"
	contractExperimentCapture      = "experiment-capture-spec-v1"
	contractExperimentStudy        = "experiment-study-v1"
	experimentTermArchival         = "archival"
	experimentTermEvaluationRun    = "evaluation-run"
	experimentTermInvalidated      = "invalidated"
	experimentTermMixedComposition = "mixed-composition"
	experimentTermSealed           = "sealed"
	experimentTermTimedOut         = "timed-out"
	fieldPlanEntryID               = "plan_entry_id"
	mediaApplicationJSON           = "application/json"
	modelAdmittedTrialEntry        = "AdmittedTrialEntryModel"
	modelAdmittedTrialPlan         = "AdmittedTrialPlanModel"
	modelExperimentRun             = "ExperimentRunModel"
	modelExperimentSpec            = "ExperimentSpecModel"
	modelExperimentStudy           = "ExperimentStudyModel"
)

const (
	fieldManifestVersion = "manifest_version"
	fieldPlanID          = "plan_id"
	termDeclaredReusable = "declared-reusable"
)

const (
	termBackendManifestV2Model                     = "BackendManifestV2Model"
	termBindingDescriptorRefsPath                  = "/binding_descriptor_refs/*"
	termConfigurationDigest                        = "configuration_digest"
	termConfigurationTargetDeclarationModel        = "ConfigurationTargetDeclarationModel"
	termDescriptionPath                            = "/description"
	termExperimentArtifactRefModel                 = "ExperimentArtifactRefModel"
	termExperimentConditionAssignmentModel         = "ExperimentConditionAssignmentModel"
	termExperimentEvidenceRequirementRelationModel = "ExperimentEvidenceRequirementRelationModel"
	termNamePath                                   = "/name"
	termParticipantConfigurationResultV1           = "participant-configuration-result-v1"
	termParticipantImplementationManifestModel     = "ParticipantImplementationManifestModel"
	termParticipantRuntimeCapabilitiesModel        = "ParticipantRuntimeCapabilitiesModel"
	termPolicyIDPath                               = "/policy_id"
	termProcessorManifestV2Model                   = "ProcessorManifestV2Model"
	termRefDigestPath                              = "/ref_digest"
	termRefIDPath                                  = "/ref_id"
	termReferenceIDPath                            = "/reference_id"
	termTargetIDPath                               = "/target_id"
	termValuePath                                  = "/value"
)

const (
	termCleanupObligationResultModel = "CleanupObligationResultModel"
	termPointRefPath                 = "/point_ref"
	termRefPathPath                  = "/ref_path"
)

const (
	termRefVersionPath = "/ref_version"
)

const (
	modelExperimentRunPlan      = "ExperimentRunPlanModel"
	experimentTermRandomization = "randomization"
)

const (
	codeExperimentYAML     = "invalid-yaml"
	codeExperimentContract = "contract-invalid"
	codeExperimentRoot     = "invalid-root"
	pathTrialEntries       = "/entries"
)
