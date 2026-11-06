package admission

import (
	"encoding/json"
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func (e *Validator) flowAction(request FlowActionRequest) (any, error) {
	if err := e.flowActionBasics(request); err != nil {
		return nil, err
	}
	manifest, err := e.flowAdmittedDocument(termParticipantImplementationManifestV1, request.Manifest)
	if err != nil {
		return nil, err
	}
	selection, err := e.flowOwnerFragment(termExperimentRunV1, "ParticipantImplementationSelectionModel", request.ImplementationSelection)
	if err != nil {
		return nil, err
	}
	v := map[string]any{"participant_address": request.ParticipantAddress, "action_contract_address": request.ActionContractAddress, "action_instance_id": request.ActionInstanceID, "observation_boundary_address": request.ObservationBoundaryAddress, "implementation_manifest": manifest, "implementation_selection": selection}
	if request.Selection != nil {
		v["validated_selection"], err = flowSelectionDocument(*request.Selection)
		if err != nil {
			return nil, err
		}
		if stringAt(v, "validated_selection", "action_contract_address") != request.ActionContractAddress {
			return nil, invalid()
		}
	}
	if len(request.ActionResult) > 0 {
		v["action_result"], err = e.flowOwnerFragment(termRuntimeSnapshotV1, "ParticipantActionResultModel", request.ActionResult)
		if err != nil {
			return nil, err
		}
	}
	v["temporal_contexts"], err = e.flowOwnerFragments("ParticipantTemporalRuntimeContextModel", request.TemporalContexts)
	if err != nil {
		return nil, err
	}
	v["temporal_evidence"], err = e.flowOwnerFragments("ParticipantTemporalEvidenceModel", request.TemporalEvidence)
	if err != nil {
		return nil, err
	}
	if err = flowActionCompatibility(v); err != nil {
		return nil, err
	}
	if err = flowActionExposure(v, request); err != nil {
		return nil, err
	}
	return v, flowActionTemporal(v)
}

func flowActionCompatibility(v any) error {
	manifest, selection := at(v, "implementation_manifest"), at(v, "implementation_selection")
	if !equal(at(selection, "participant_address"), at(v, "participant_address")) || !equal(at(manifest, termIdentity), at(selection, "implementation_identity")) || !subset(stringsOf(at(selection, "participant_contract_versions")), set(at(manifest, "capabilities", "supported_participant_contracts"))) || !set(at(manifest, "capabilities", "supported_decision_surface_modes"))[stringAt(selection, "selected_decision_surface_mode")] || !subset(stringsOf(at(selection, "exposure_policy", "exposure_policy_kinds")), set(at(manifest, "capabilities", "exposure_policy_kinds"))) {
		return invalid()
	}
	result := at(v, "action_result")
	if result != nil && !matchingFields(result, v, "participant_address", "action_instance_id", "action_contract_address") {
		return invalid()
	}
	return nil
}

func flowActionExposure(v any, request FlowActionRequest) error {
	policy, result := at(v, "implementation_selection", "exposure_policy"), at(v, "action_result")
	evidence := set(jsonStrings(request.EvidenceRefs))
	maps.Copy(evidence, set(at(result, "evidence_refs")))
	for _, field := range []string{termPreconditions, termEffects, "temporal_evidence"} {
		for _, record := range array(at(result, field)) {
			maps.Copy(evidence, set(at(record, "evidence_refs")))
		}
	}
	for _, proof := range array(at(v, "temporal_evidence")) {
		maps.Copy(evidence, set(at(proof, "evidence_refs")))
	}
	emitted := set(jsonStrings(request.VisibleRefs))
	maps.Copy(emitted, set(jsonStrings(request.DisclosedRefs)))
	maps.Copy(emitted, evidence)
	for _, ref := range stringsOf(at(policy, "withheld_refs")) {
		if emitted[ref] {
			return invalid()
		}
	}
	allowed := set(at(policy, "disclosed_refs"))
	maps.Copy(allowed, set(at(policy, "visibility_scope_refs")))
	return require(subset(request.VisibleRefs, allowed) && subset(request.DisclosedRefs, set(at(policy, "disclosed_refs"))) && subsetSet(evidence, set(jsonStrings(request.ObservationBoundaryEvidenceRefs))))
}

func flowActionTemporal(v any) error {
	carriers := array(at(v, "temporal_contexts"))
	if len(rowSet(carriers, "temporal_contract_id")) != len(carriers) {
		return invalid()
	}
	contexts := []any{}
	points := rowSet(carriers, "observation_point")
	for _, carrier := range carriers {
		if at(carrier, "shared_time") != nil {
			contexts = append(contexts, at(carrier, "shared_time"))
		}
	}
	result := at(v, "action_result")
	if result != nil && len(points) > 0 && !points[stringAt(result, "observation_point")] {
		return invalid()
	}
	for _, proofs := range [][]any{array(at(v, "temporal_evidence")), array(at(result, "temporal_evidence"))} {
		if err := temporalEvidenceScope(contexts, proofs, stringAt(v, "observation_boundary_address")); err != nil {
			return err
		}
	}
	return nil
}

func (e *Validator) flowActionExecution(request FlowActionRequest) error {
	if (request.ExecutionScopeRef != "") != (request.ExecutionGeneration != nil) {
		return invalid()
	}
	if request.ExecutionGeneration != nil {
		n, ok := number(*request.ExecutionGeneration)
		if !ok || !n.IsInt() || n.Sign() < 0 || len(request.TargetAddresses) == 0 {
			return invalid()
		}
	}
	if len(request.ResourceRequirements) > 4096 {
		return invalid()
	}
	seen := map[string]bool{}
	for _, requirement := range request.ResourceRequirements {
		if seen[requirement.BudgetStateRef] {
			return invalid()
		}
		seen[requirement.BudgetStateRef] = true
		if err := e.flowMeasurementRequirement(requirement); err != nil {
			return err
		}
	}
	return nil
}

func (e *Validator) flowMeasurementRequirement(v FlowResourceRequirement) error {
	reserved, ok := number(v.Reserved)
	if v.BudgetStateRef == "" || v.Unit == "" || v.MeterProfileRef == "" || !ok || !reserved.IsInt() || reserved.Sign() < 0 || numericGreater(v.Reserved, json.Number("1000000000000000000")) {
		return invalid()
	}
	wrapped, err := json.Marshal(map[string]json.RawMessage{termKind: v.ResourceKind})
	if err != nil {
		return invalid()
	}
	parsed, err := ingress.Parse(wrapped, ingress.Limits{MaxBytes: 1048576, MaxDepth: 16}, ingress.Object)
	if err != nil {
		return err
	}
	if object(at(parsed, termKind)) != nil {
		_, err = e.flowOwnerFragment(termParticipantResourceBudgetPolicyV1, "DomainProfileCoordinateModel", v.ResourceKind)
		return err
	}
	unit := resourceUnit(stringAt(parsed, termKind))
	return require(unit != "" && v.Unit == unit)
}

func (e *Validator) flowActionBasics(request FlowActionRequest) error {
	if request.ParticipantAddress == "" || request.ActionInstanceID == "" || !strings.HasPrefix(request.ActionContractAddress, "participant.action-contract.") || !strings.HasPrefix(request.ObservationBoundaryAddress, "participant.observation-boundary.") {
		return invalid()
	}
	for _, refs := range [][]string{request.EvidenceRefs, request.VisibleRefs, request.DisclosedRefs, request.ObservationBoundaryEvidenceRefs, request.TargetAddresses} {
		if !flowUniqueReferences(refs) {
			return invalid()
		}
	}
	if err := e.flowActionExecution(request); err != nil {
		return err
	}
	return nil
}
