package planning

import (
	"bytes"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

// Native compilation already admits the closed service binding, its ownership,
// targets, digests and readback references. This gate joins that typed intent to
// one selected target's profile, exact support and independent readback claims.
func (plan *executionPlan) serviceMaterializationDiagnostics() ([]diagnostic.Diagnostic, error) {
	result := []diagnostic.Diagnostic{}
	caps := fieldValue(fieldValue(plan.manifest.Capabilities).Provisioner)
	supported := map[string]bool{}
	for _, raw := range fieldValue(caps.SupportedServiceMaterializationProfiles) {
		canonical, err := canonjson.JCS(raw)
		if err != nil {
			return nil, invalidPlan()
		}
		supported[string(canonical)] = true
	}
	exact := serviceExactSupport(plan.manifest)
	readback := independentServiceReadback(plan.context.RealizationEnvelope)
	for _, operation := range plan.operations[termProvisioning] {
		if operation.Kind != termContentPlacement || operation.Action == termDelete {
			continue
		}
		service := plan.resources[operation.Address].facts.ServiceMaterialization
		if service == nil {
			continue
		}
		code, message, err := serviceMaterializationGap(service, supported, exact, readback)
		if err != nil {
			return nil, err
		}

		if code != "" {
			result = append(result, planDiagnostic(code, termProvisioning, operation.Address, message))
		}
	}
	return result, nil
}
func serviceMaterializationGap(service *processor.ServiceMaterialization, supported, exact map[string]bool, readback bool) (string, string, error) {
	if service.ProfileBinding != nil {
		return privateServiceProfileGap(service.ProfileBinding, supported)
	}
	term, requirement := "service-content-v1", "service-content-materialization"
	if service.InterfaceProfile == "service-search-index-schema" {
		term, requirement = "service-search-index-schema-v1", "service-search-index-schema-materialization"
	}
	raw, err := json.Marshal(term)
	if err != nil {
		return "", "", invalidPlan()
	}
	switch {
	case !supported[string(raw)]:
		return "provisioner.unsupported-service-materialization-profile", "Provisioner does not support service materialization profile '" + term + "'.", nil
	case !exact[requirement]:
		return "realization.unsupported-exact-requirement", "Backend does not declare exact realization support for service materialization requirement '" + requirement + "'.", nil
	case !readback:
		return "provisioner.service-materialization-readback-unsupported", "Backend realization envelope does not provide independent native readback for service materialization.", nil
	default:
		return "", "", nil
	}
}
func privateServiceProfileGap(profile *binding.DomainProfileBindingV1, supported map[string]bool) (string, string, error) {
	coordinate, err := json.Marshal(fieldValue(profile.Coordinate))
	if err != nil {
		return "", "", invalidPlan()
	}
	canonical, err := canonjson.JCS(coordinate)
	if err != nil {
		return "", "", invalidPlan()
	}
	if !supported[string(canonical)] {
		return "provisioner.unsupported-service-materialization-profile", "Provisioner does not support the selected service materialization profile.", nil
	}
	return "", "", nil
}

func independentServiceReadback(envelope *binding.RealizationEnvelopeV1) bool {
	if envelope == nil {
		return false
	}
	for _, concern := range fieldValue(envelope.Concerns) {
		raw, err := json.Marshal(fieldValue(concern.Concern))
		if err != nil {
			return false
		}
		if !bytes.Equal(raw, []byte(`"content-placement"`)) {
			continue
		}
		disposition := string(fieldValue(concern.Disposition))
		strength := string(fieldValue(concern.ObservationStrength))
		return disposition == "realized" && (strength == "daemon-observed" || strength == "guest-observed")
	}
	return false
}
func phaseDiagnostics(input []diagnostic.Diagnostic) []map[string]any {
	result := make([]map[string]any, len(input))
	for i, entry := range input {
		result[i] = map[string]any{"code": entry.Code, termDomain: entry.Domain, termAddress: entry.Address, "message": entry.Message, "severity": entry.Severity}
	}
	return result
}

func serviceExactSupport(manifest binding.BackendManifestV2) map[string]bool {
	exact := map[string]bool{}
	for _, support := range fieldValue(manifest.RealizationSupport) {
		if fieldValue(support.Domain) != "runtime-realization" {
			continue
		}
		for _, kind := range fieldValue(support.SupportedExactRequirementKinds) {
			exact[kind] = true
		}
	}
	return exact
}
