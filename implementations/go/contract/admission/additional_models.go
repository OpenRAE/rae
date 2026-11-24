package admission

func (e *Validator) additionalModel(name string, v any) (bool, error) {
	switch name {
	case "ScenarioCoordinateModel", "ModuleCoordinateModel", "TaskCoordinateModel", "RunCoordinateModel", "StudyCoordinateModel", "EvidenceSpecificationCoordinateModel", "ExternalConceptBindingsCoordinateModel":
		return true, comparisonCoordinate(v)
	case "OperationAdmissionContext":
		return true, require(fieldsUnique(v, "authorization_scope"))
	case "RandomStreamBoundedIntegerVectorCaseModel":
		return true, require(!numericGreater(at(v, "minimum"), at(v, "maximum")) && boolean(at(v, "expected_rejection_exhausted")) == (at(v, "outcome") == nil))
	case "BehavioralClaimBindingModel":
		return true, claimStrength(v)
	case "RealizationClosure":
		return true, require((text(defaultMember(v, "posture", termUndefined)) != termUndefined) == (at(v, "universe") != nil && at(v, "profile") != nil))
	case "recursive-realization-constraint-v1", "RealizationConstraintDocument":
		return true, require(len(rowSet(at(v, "scopes"), "field_pointer")) == len(array(at(v, "scopes"))))
	case "RealizationScope":
		return true, require(stringAt(v, "closure", "posture") != termUndefined)
	case "EnumDomain":
		return true, uniqueJSONValues(at(v, "values"))
	case "PlannedRealizationConstraintModel":
		return true, e.plannedSubstrate(v)
	case "RealizationConstraintDesignation":
		return true, e.substrateDomain(stringAt(v, "posture"), at(v, "domain"))
	case "provisioning-plan-v1", "ProvisioningPlanModel":
		return true, planModel(v, termProvisioning)
	case "orchestration-plan-v1", "OrchestrationPlanModel":
		return true, planModel(v, termOrchestration)
	case "evaluation-plan-v1", "EvaluationPlanModel":
		return true, planModel(v, termEvaluation)
	case "backend-realization-preparation-v1":
		return true, require(len(rowSet(at(v, "operations"), "address")) == len(array(at(v, "operations"))))
	case "backend-augmentation-scope-v1", "AugmentationPreparation":
		return true, augmentationPreparationModel(v)
	case "participant-context-view-v1", "ParticipantContextViewModel":
		return true, contextSourceBindings(v)
	case "participant-status-view-v1", "ParticipantStatusViewModel":
		return true, require(at(v, "episode_state") == nil || at(v, "episode_id") != nil)
	case termParticipantJointActionRecordV1, "ParticipantJointActionRecordModel":
		return true, jointActionModel(v)
	case "participant-outcome-report-v2", "ParticipantOutcomeReportV2Model":
		return true, localOutcomeReport(v)
	case "OutcomeInterpretationRule":
		return true, outcomeInterpretation(v)
	case "LocalOutcomeDefinition":
		return true, require(len(rowSet(at(v, "criteria"), "criterion_id")) == len(array(at(v, "criteria"))) && len(rowTupleSet(at(v, "criteria"), termSourceID, "effect_id")) == len(array(at(v, "criteria"))))
	case "OutcomeInterpretationSourceBinding":
		return true, outcomeSourceBinding(v)
	case "OutcomeInterpretationTargetBinding":
		return true, outcomeTargetBinding(v)
	case "ObservationSelector":
		return true, observationSelectorModel(v)
	case "observation-demand-v1":
		return true, require(len(rowSet(at(v, "rules"), "rule_id")) == len(array(at(v, "rules"))))
	case "RealizedBindingProvenanceModel":
		return true, require(stringAt(v, "descriptor", "target", "plane") == "scenario" || at(v, "configuration_digest") != nil)
	case "ReusableAssetFamilyTrustPolicyModel":
		return true, reusableFamilyPolicy(v)
	default:
		return false, nil
	}
}

func uniqueJSONValues(rows any) error {
	seen := map[string]bool{}
	for _, row := range array(rows) {
		key, err := jsonDigest(row)
		if err != nil || seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}
