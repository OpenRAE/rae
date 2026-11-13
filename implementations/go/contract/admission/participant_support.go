package admission

import (
	"encoding/json"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// ParticipantFeatureSupportGaps checks evidence and strength against the shared
// manifest catalog. Gaps describe capability only; they grant no execution.
func ParticipantFeatureSupportGaps(v *Validator, manifest binding.BackendManifestV2, features []string, requiredLevel string) ([]string, error) {
	ranks := map[string]int{statusUnsupported: 0, termDisclosedWeak: 1, assuranceBounded: 2, "exact": 3}
	_, known := ranks[requiredLevel]
	if v == nil || !known {
		return nil, invalid()
	}
	budget := value.Runtime()
	if len(features) > budget.MaxMembers {
		return nil, invalid()
	}
	if !participantFeaturesWithin(features, budget) {
		return nil, invalid()
	}
	limits := ingress.Limits{MaxBytes: budget.MaxTotalScalarBytes, MaxDepth: 128}
	if err := CheckTransport(manifest, limits); err != nil {
		return nil, err
	}
	raw, err := json.Marshal(manifest)
	if err != nil {
		return nil, invalid()
	}
	if err := v.CheckPortable("backend-manifest-v2", raw, limits); err != nil {
		return nil, err
	}
	capabilities, _ := manifest.Capabilities.Value()
	component, _ := capabilities.ParticipantRuntime.Value()
	var capability any
	if len(component) > 0 && json.Unmarshal(component, &capability) != nil {
		return nil, invalid()
	}
	versions, _ := manifest.SupportedContractVersions.Value()
	contracts := set(jsonStrings(versions))
	required := slices.Clone(features)
	slices.Sort(required)
	required = slices.Compact(required)
	supported := set(at(capability, "supported_behavior_features"))
	for feature := range set(at(capability, "supported_interaction_features")) {
		supported[feature] = true
	}
	declarations := map[string]any{}
	for _, declaration := range array(at(capability, "feature_support")) {
		declarations[stringAt(declaration, "feature")] = declaration
	}
	gaps := []string{}
	for _, feature := range required {
		declaration, declared := declarations[feature]
		if gap := participantFeatureGap(capability, feature, declaration, declared, supported, contracts, requiredLevel, ranks); gap != "" {
			gaps = append(gaps, gap)
		}
	}
	return gaps, nil
}

func participantFeaturesWithin(features []string, budget value.Limits) bool {
	total := 0
	for _, feature := range features {
		if !utf8.ValidString(feature) || len(feature) > budget.MaxScalarBytes || len(feature) > budget.MaxTotalScalarBytes-total {
			return false
		}
		total += len(feature)
	}
	return true
}

func participantFeatureGap(capability any, feature string, declaration any, declared bool, supported, contracts map[string]bool, requiredLevel string, ranks map[string]int) string {
	prefix := "participant feature '" + feature + "' "
	switch {
	case capability == nil:
		return prefix + "requires participant runtime capabilities"
	case !declared:
		if supported[feature] && !participantEvidenceFeature(feature) {
			return ""
		}
		return prefix + "has no explicit support declaration"
	case stringAt(declaration, "support_level") == statusUnsupported:
		return prefix + "is explicitly unsupported"
	}
	missing := []string{}
	for _, contract := range participantFeatureContracts(feature) {
		if !contracts[contract] {
			missing = append(missing, contract)
		}
	}
	slices.Sort(missing)
	switch {
	case len(missing) > 0:
		return prefix + "is missing required contracts: " + strings.Join(missing, ", ")
	case participantEvidenceFeature(feature) && len(array(at(declaration, "evidence_refs"))) == 0:
		return prefix + "has no conformance evidence"
	case ranks[stringAt(declaration, "support_level")] < ranks[requiredLevel]:
		return prefix + "requires " + requiredLevel + " support; backend declares " + stringAt(declaration, "support_level")
	}
	return ""
}
