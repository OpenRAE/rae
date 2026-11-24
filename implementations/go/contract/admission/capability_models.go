package admission

func (e *Validator) capabilityModel(name string, v any) (bool, error) {
	switch name {
	case "ParticipantResourceBudgetCapabilitiesModel":
		return true, resourceCapabilities(v)
	case "ParticipantRuntimeCapabilitiesModel":
		return true, e.runtimeCapabilities(v)
	case "ProcessorCapabilitiesV2Model":
		return true, require(declaredManifestContracts(at(v, "supported_sdl_versions"), "sdl"))
	case "ProcessorParticipantToolsModel":
		return true, processorTools(v)
	case "ProvisionerCapabilitiesModel":
		return true, e.provisionerCapability(v)
	case "OperatingSystemCompatibilityModel":
		return true, e.operatingSystemCapability(v)
	case "OrchestratorCapabilitiesModel":
		return true, e.orchestratorCapability(v)
	case "EvaluatorCapabilitiesModel":
		return true, e.evaluatorCapability(v)
	case "ObservationCapabilitiesModel":
		return true, e.observationCapability(v)
	case "CleanupCapabilitiesModel":
		return true, cleanupCapability(v)
	case "RecoveryObservationCapabilitiesModel":
		return true, require(fieldsUnique(v, "supported_operation_kinds") && !set(at(v, "supported_operation_kinds"))["indeterminate-resolution"])
	case "TimeCapabilitiesModel":
		return true, timeCapability(v)
	case "ParticipantInvocationToolActionCapabilitiesModel":
		return true, require(fieldsUnique(v, "semantic_versions") && !numericGreater(at(v, "max_concurrent_tool_actions_per_invocation"), at(v, "max_tool_actions_per_invocation")))
	case "ParticipantExecutionBindingModel":
		return true, require(fieldsUnique(v, "target_addresses", "constraint_refs", "evidence_refs", "temporal_contract_digests"))
	default:
		return false, nil
	}
}
