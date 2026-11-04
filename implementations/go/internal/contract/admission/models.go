package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// Supplemental model rules are explicit root-family checks. Published schema
// and invariant checks run first. These checks cover Python model conditions
// that have no independent x-raes-invariants annotation.
func (e *Validator) localModels(id string, root any) error {
	if known, err := e.domainProfileModel(id, root); known {
		return err
	}
	if known, err := e.resourceModel(id, root); known {
		return err
	}
	if known, err := vocabularySource(id, root); known {
		return err
	}
	switch id {
	case "participant-behavior-history-event-stream-v1":
		return behaviorLifecycles(root)
	case "sdl-lineage-ledger-v1":
		return lineageLedger(root)
	case termPropositionTruthResultV1:
		return propositionTruth(root)
	case termRuntimeSnapshotV1:
		return e.snapshotLocalModels(root)
	case "experiment-study-v1":
		return studyFactorDeclarations(root)
	case "semantic-profile-v1":
		return e.semanticProfile(root)
	case "scenario-satisfiability-evidence-v1":
		return e.satisfiabilityModel(root)
	case termProcessorManifestV2:
		return e.processorManifest(root)
	case "controlled-vocabularies-v1":
		return vocabularyCatalog(root)
	case termParticipantImplementationManifestV1:
		return e.participantManifest(root)
	case "participant-implementation-provenance-v1":
		return participantProvenanceModel(root)
	case "concept-families-v1":
		return conceptFamilyKeys(root)
	case "uco-alignment-v1":
		return e.ucoCatalog(root)
	case "reference-models-v1":
		return e.referenceModels(root)
	case termBackendManifestV2:
		return e.backendManifestModel(root)
	case termExperimentRunV1:
		return selectionDescriptorSet(array(at(root, "realized_selections")))
	case termBackendMaterializationAttestationV1:
		return require(len(stringAt(root, "sdl")) <= 4*1048576)
	case termMaterializedScenarioV1:
		return materializedLocal(root)
	case termBackendRuntimeDescendantsV1:
		return inventoryLocal(root)
	case termParticipantBoundaryFlowPolicyV1, termParticipantOwnerFlowPolicyV1:
		return e.flowProfileDocument(id, root)
	case termParticipantFlowControlRelationV1:
		return e.flowLocalInstances(id, root)
	case termParticipantControlEvaluationV2:
		value, err := e.defaulted(id, root)
		if err != nil {
			return err
		}
		return controlEvaluationV2(value)
	case termParticipantControlEvaluationV1:
		value, err := e.defaulted(id, root)
		if err != nil {
			return err
		}
		return controlEvaluationV1(value)
	case termParticipantExecutionBindingV1:
		return require(fieldsUnique(root, "target_addresses", "constraint_refs", fieldEvidenceRefs, "temporal_contract_digests"))
	case termParticipantExecutionControlV1:
		return require((stringAt(root, "action") == "drain") == (at(root, "timeout_seconds") != nil))
	case termParticipantExecutionServiceStateV1:
		return executionState(root)
	case termTrialCleanupReceiptV1:
		return cleanupReceiptLocal(root)
	case termTimeModelV1:
		return timeDeclaration(root)
	case termRealizedTimeModelV1:
		return e.runTimeModel(validation.Invocation{Instance: map[string]any{termRunID: at(root, termRunID), "realized_time_model": root}})
	case "materialization-archive-record-v1":
		return archiveRecordLocal(root)
	case termTimeRuntimeStateV1:
		return timeRuntime(root)
	case termParticipantInformationStateRecordV1:
		return informationLocal(root)
	case termParticipantControlOccurrenceV2:
		occurrence := at(root, "occurrence")
		if stringAt(occurrence, "disposition") == termRejected {
			return require(fieldsUnique(occurrence, "limitation_refs") && fieldsUnique(at(occurrence, "attempted"), "authority_basis_refs", "controlled_scope_refs"))
		}
		return controlOccurrenceLocal(validation.Invocation{Instance: root})
	case "participant-information-reconstruction-profile-v1":
		return require(fieldsUnique(root, "accepted_input_contracts", "accepted_order_semantics"))
	case termAssociatedArtifactManifestV1:
		return associatedLocal(root)
	case termParticipantControlContextAssetV1, termParticipantControlContextRecordV1, termParticipantControlContextChangeV1:
		return controlContextLocal(id, root)
	default:
		return nil
	}
}

// These are the portable entry point's actual contextual gates, distinct from
// the larger metadata set whose strength is "structural-context-required".
func portableContextRequired(id string) bool {
	switch id {
	case termParticipantControlContextAssetV1, termParticipantControlContextChangeV1, termParticipantControlContextRecordV1,
		termParticipantControlEvaluationV1, termParticipantControlEvaluationV2, termParticipantInformationStateRecordV1,
		termParticipantFlowControlRelationV1, termMixedParticipantCompositionProfileV1:
		return true
	default:
		return false
	}
}

func (e *Validator) checkModels(id string, data []byte, limits ingress.Limits) error {
	checkedRoot := false
	var normalized any
	return e.low.CheckInstances(id, data, limits, func(instance validation.SchemaInstance) error {
		if instance.Discriminator != "" {
			if _, present := object(instance.Value)[instance.Discriminator]; !present && !legacyServiceProfileDefault(instance) {
				return invalid()
			}
		}
		if !checkedRoot {
			checkedRoot = true
			if err := e.initialModel(id, instance.Root, data); err != nil {
				return err
			}
		}
		var err error
		instance, err = e.controlDefaultInstance(instance, data, limits, &normalized)
		if err != nil {
			return err
		}
		return e.instanceModel(instance)
	})
}

func (e *Validator) instanceModel(instance validation.SchemaInstance) error {
	if known, err := e.domainProfileModel(strings.TrimPrefix(instance.SchemaPointer, "#/$defs/"), instance.Value); known {
		return err
	}
	if known, err := e.resourceModel(strings.TrimPrefix(instance.SchemaPointer, "#/$defs/"), instance.Value); known {
		return err
	}
	if known, err := e.capabilityModel(strings.TrimPrefix(instance.SchemaPointer, "#/$defs/"), instance.Value); known {
		return err
	}
	if known, err := materializationModel(strings.TrimPrefix(instance.SchemaPointer, "#/$defs/"), instance.Value); known {
		return err
	}
	if known, err := e.controlModel(strings.TrimPrefix(instance.SchemaPointer, "#/$defs/"), instance.Value); known {
		return err
	}
	if known, err := flowModel(strings.TrimPrefix(instance.SchemaPointer, "#/$defs/"), instance.Value); known {
		return err
	}
	switch strings.TrimPrefix(instance.SchemaPointer, "#/$defs/") {
	case "ParticipantBehaviorHistoryEventModel":
		return behaviorLifecycle(instance.Value)
	case "PropositionProbeBindingModel":
		return require(fieldsUnique(instance.Value, "capability_refs"))
	case "PropositionTruthResultModel":
		return propositionTruth(instance.Value)
	case "LineageClaimModel":
		return lineageClaimDimensions(instance.Value)
	case "ConfigurationTargetDeclarationModel":
		return configurationTargetModel(instance.Value)
	case "SemanticProfileModel":
		return e.semanticProfile(instance.Value)
	case "SemanticProfilePhaseModel":
		return e.semanticProfilePhase(instance.Value)
	case "ScenarioSatisfiabilityEvidenceModel":
		return e.satisfiabilityModel(instance.Value)
	case "SourceArtifactIdentityModel":
		return constraintSource(instance.Value)
	case "NormalizedConstraintModel":
		return constraintGraph(instance.Value)
	case "ConstraintSymbolModel":
		_, err := constraintValues(at(instance.Value, "domain"), stringAt(instance.Value, "sort"))
		return err
	case "ConstraintClauseModel":
		_, err := constraintValues(at(instance.Value, "allowed_values"), "")
		return err
	case "UnsatisfiableCoreModel":
		return require(sortedUnique(stringsOf(at(instance.Value, "clause_ids"))))
	case "UnsupportedAnalysisModel":
		return require(sortedUnique(stringsOf(at(instance.Value, "reason_codes"))))

	case "ParticipantImplementationProvenanceModel":
		return participantProvenanceModel(instance.Value)
	case "ParticipantImplementationManifestModel":
		return e.participantManifest(instance.Value)
	case "ProcessorManifestV2Model":
		return e.processorManifest(instance.Value)
	case "BackendManifestV2Model":
		return e.backendManifestModel(instance.Value)
	case "ControlledVocabularyDefinitionModel":
		return e.vocabularyDefinition(instance.Value)
	case "ParticipantImplementationCompatibilityModel":
		return participantCompatibility(instance.Value)
	case "ParticipantImplementationCapabilitiesModel":
		return e.participantCapabilities(instance.Value)
	case "ParticipantImplementationSelectionModel":
		return e.participantSelection(instance.Value)
	case "ParticipantExposurePolicyModel":
		return e.participantExposure(instance.Value)
	case "ParticipantFeatureSupportModel":
		return e.participantFeatureDeclaration(instance.Value)
	case "ExperimentBindingDescriptorModel", "ExperimentFactorLevelBindingModel", "RealizedConfigurationValueModel":
		return bindingScalarType(instance.Value)
	case "AdmittedSelectionRecordModel":
		v := instance.Value
		if at(v, "treatment") == nil {
			return nil
		}
		return require(equal(at(v, "treatment", "target", "variation_point_id"), at(v, "variation_point_id")) && equal(at(v, "treatment", "outcome"), at(v, "outcome")))
	case "ExperimentEvidenceRequirementRelationModel":
		return evidenceRelationShape(instance.Value)
	case "DifficultyRunProvenanceModel":
		return difficultyProvenance(instance.Value)
	case "MaterializationArchiveRecord":
		return archiveRecordLocal(instance.Value)
	case "TimeModelDeclarationModel":
		return timeDeclaration(instance.Value)
	case "ExactRatioModel":
		return require(reducedRatio(instance.Value))
	case "RuntimeClockStateModel":
		return runtimeClock(instance.Value)
	case "TimeRuntimeStateModel":
		return timeRuntime(instance.Value)
	case "ControlEffectiveSupportModel":
		return controlEffectiveSupport(instance.Value)
	case "ParticipantControlSelectionModel", "ParticipantControlSelectionV2Model":
		return e.controlSelection(validation.Invocation{Instance: instance.Value})
	case "ParticipantDecisionSurfaceSequenceCutModel", "ParticipantDecisionSurfaceCausalCutModel":
		return decisionCut(instance.Value)
	default:
		return nil
	}
}

func bindingScalarType(v any) error {
	if stringAt(v, "value", termKind) == "secret-reference" {
		return require(stringAt(v, "value_type") != termNull)
	}
	return require(scalarMatches(at(v, "value", "value"), stringAt(v, "value_type")))
}

func (e *Validator) controlDefaultInstance(instance validation.SchemaInstance, data []byte, limits ingress.Limits, normalized *any) (validation.SchemaInstance, error) {
	name := strings.TrimPrefix(instance.SchemaPointer, "#/$defs/")
	if !controlNeedsDefaults(name) && !flowNeedsDefaults(instance) {
		return instance, nil
	}
	if *normalized == nil {
		var err error
		*normalized, err = e.low.Defaulted(instance.ContractID, data, limits)
		if err != nil {
			return instance, err
		}
	}
	value, present := pointerAt(*normalized, instance.Path)
	if !present {
		return instance, invalid()
	}
	instance.Value = value
	return instance, nil
}
func controlNeedsDefaults(name string) bool {
	return strings.HasPrefix(name, "Control") || name == termParticipantControlContextModel || name == termParticipantControlRequestModel || name == termParticipantControlRequestV2Model
}

func (e *Validator) initialModel(id string, root any, data []byte) error {
	if id == termBackendManifestV2 {
		if err := checkResourceProfiles(root, data); err != nil {
			return err
		}
	}
	return e.localModels(id, root)
}
