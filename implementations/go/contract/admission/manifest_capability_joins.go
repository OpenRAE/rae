package admission

func declaredManifestContracts(values any, kind string) bool {
	return unique(stringsOf(values)) && subset(stringsOf(values), set(jsonStrings(supportedManifestContracts(kind))))
}

func (e *Validator) manifestBindings(v any, allowed func(string) bool) error {
	if err := manifestConfigurationTargets(v); err != nil {
		return err
	}
	bindings := array(at(v, "concept_bindings"))
	if len(rowSet(bindings, "scope")) != len(bindings) {
		return invalid()
	}
	for _, binding := range bindings {
		scope := stringAt(binding, "scope")
		if !e.knownFamily(stringAt(binding, "family")) || !allowed(scope) || !manifestScopePresent(v, scope) {
			return invalid()
		}
	}
	return nil
}

func manifestConfigurationTargets(v any) error {
	claimed := map[string]bool{}
	for key, target := range object(at(v, "configuration_registry", "targets")) {
		if key != stringAt(target, "target_id") {
			return invalid()
		}
		if err := configurationTargetModel(target); err != nil {
			return err
		}
		for _, name := range append([]string{key}, stringsOf(at(target, "aliases"))...) {
			if claimed[name] {
				return invalid()
			}
			claimed[name] = true
		}
	}
	return nil
}

func configurationTargetModel(v any) error {
	kinds := stringsOf(at(v, "allowed_value_kinds"))
	if !fieldsUnique(v, "aliases", "allowed_value_kinds") || set(at(v, "aliases"))[stringAt(v, "target_id")] {
		return invalid()
	}
	control := at(v, "control_context")
	if control != nil && (stringAt(v, "value_type") != "string" || len(kinds) != 1 || kinds[0] != "literal") {
		return invalid()
	}
	secret := stringAt(v, "sensitivity") == sensitivitySecret
	if secret && (len(kinds) != 1 || kinds[0] != "secret-reference") {
		return invalid()
	}
	def := at(v, termDefault)
	if def == nil {
		return nil
	}
	if secret || !set(at(v, "allowed_value_kinds"))["literal"] || !scalarMatches(at(def, "value"), stringAt(v, "value_type")) {
		return invalid()
	}
	return require(control == nil || set(at(control, "references"))[text(at(def, "value"))])
}

func (e *Validator) processorManifest(v any) error {
	versions := at(v, "supported_contract_versions")
	if !declaredManifestContracts(versions, "processor") || at(v, "configuration_registry") != nil && !set(versions)[termExperimentBindingDescriptorsV1] {
		return invalid()
	}
	return e.manifestBindings(v, processorConceptScope)
}

func backendFamilyContracts(kind string) []string {
	switch kind {
	case termCleanup:
		return []string{termTrialCleanupPlanV1, termTrialCleanupReceiptV1}
	case "time":
		return []string{termTimeModelV1, termTimeRuntimeStateV1, termRealizedTimeModelV1, termRuntimeSnapshotV1, "experiment-run-v1"}
	case "operation_supervision":
		return []string{termBackendOperationRequestV1, termBackendOperationCapabilitiesV1, termBackendOperationControlV1, termBackendOperationResponseV1}
	default:
		return nil
	}
}

func backendManifestCoupling(v any) error {
	versions := set(at(v, "supported_contract_versions"))
	if !declaredManifestContracts(at(v, "supported_contract_versions"), kindBackend) || at(v, "configuration_registry") != nil && !versions[termExperimentBindingDescriptorsV1] {
		return invalid()
	}
	if (at(v, "realization_envelope") != nil) != versions[termRealizationEnvelopeV1] {
		return invalid()
	}
	if err := backendRequiredCapabilities(v, versions); err != nil {
		return err
	}

	return backendManifestOffers(v, versions)
}

func backendRequiredCapabilities(v any, versions map[string]bool) error {
	for _, kind := range []string{termCleanup, "time", "operation_supervision"} {
		if at(v, "capabilities", kind) != nil && !subset(backendFamilyContracts(kind), versions) {
			return invalid()
		}
	}
	if (versions[termTrialCleanupPlanV1] || versions[termTrialCleanupReceiptV1]) && at(v, "capabilities", termCleanup) == nil {
		return invalid()
	}
	if (versions[termTimeModelV1] || versions[termTimeRuntimeStateV1] || versions[termRealizedTimeModelV1]) && at(v, "capabilities", "time") == nil {
		return invalid()
	}
	if boolean(at(v, "capabilities", "time", "supports_coordinated_participant_reset")) && at(v, "capabilities", "participant_runtime") == nil {
		return invalid()
	}
	return nil
}

func backendManifestOffers(v any, versions map[string]bool) error {
	for _, offer := range array(at(v, "capabilities", "observation", "capture_offers")) {
		if !versions[stringAt(offer, "output_contract")] {
			return invalid()
		}
	}
	for _, claim := range array(at(v, "capabilities", "participant_runtime", "feature_support")) {
		feature := stringAt(claim, "feature")
		if participantEvidenceFeature(feature) && stringAt(claim, "support_level") != statusUnsupported && !subset(participantFeatureContracts(feature), versions) {
			return invalid()
		}
	}
	return nil
}

func participantProvenanceModel(v any) error {
	return require(len(rowSet(at(v, "participant_implementations"), "participant_address")) == len(array(at(v, "participant_implementations"))))
}
