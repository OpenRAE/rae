package processor

import (
	"encoding/json"
	"slices"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type manifestConceptBinding struct {
	Scope  string `json:"scope"`
	Family string `json:"family"`
}

type manifestFeatureSupport struct {
	Feature        string   `json:"feature"`
	SupportLevel   string   `json:"support_level"`
	ConstraintRefs []string `json:"constraint_refs"`
	LimitationRefs []string `json:"limitation_refs"`
	DisclosureRefs []string `json:"disclosure_refs"`
	EvidenceRefs   []string `json:"evidence_refs"`
}

type manifestParticipantTools struct {
	SemanticVersions          []string                 `json:"semantic_versions"`
	MaxBindingsPerProfile     *int                     `json:"max_bindings_per_profile"`
	MaxParticipantsPerBinding *int                     `json:"max_participants_per_binding"`
	FeatureSupport            []manifestFeatureSupport `json:"feature_support"`
}

// Manifest builds the reference processor declaration with an explicit version.
// Nil backends selects the established stub target; an empty list stays empty.
func Manifest(version string, compatibleBackends []string) (binding.ProcessorManifestV2, error) {
	invalid := func() (binding.ProcessorManifestV2, error) {
		return binding.ProcessorManifestV2{}, fault.New(fault.InvalidInput, "processor-manifest-input", nil)
	}
	if version == "" || !utf8.ValidString(version) || len(version) > 4096 || len(compatibleBackends) > 4096 {
		return invalid()
	}
	if compatibleBackends == nil {
		compatibleBackends = []string{"stub"}
	}
	for _, name := range compatibleBackends {
		if !utf8.ValidString(name) || len(name) > 4096 {
			return invalid()
		}
	}
	backends := slices.Clone(compatibleBackends)
	slices.Sort(backends)
	backends = slices.Compact(backends)
	if backends == nil {
		backends = []string{}
	}
	contracts := []string{"processor-manifest-v2", "provisioning-plan-v1", "orchestration-plan-v1", "evaluation-plan-v1", "workflow-cancellation-request-v1", "operation-receipt-v1", "operation-status-v1", "runtime-snapshot-v1"}
	features := []string{"compilation", "planning", "orchestration-coordination", "evaluation-coordination", "workflow-semantics", "objective-window-consistency", "dependency-ordering", "runtime-control-plane"}
	document := struct {
		SchemaVersion string `json:"schema_version"`
		Identity      struct {
			Name    string `json:"name"`
			Version string `json:"version"`
		} `json:"identity"`
		SupportedContractVersions []string `json:"supported_contract_versions"`
		Compatibility             struct {
			Backends []string `json:"backends"`
		} `json:"compatibility"`
		ConceptBindings []manifestConceptBinding `json:"concept_bindings"`
		Constraints     map[string]string        `json:"constraints"`
		Capabilities    struct {
			SupportedSDLVersions []string                 `json:"supported_sdl_versions"`
			SupportedFeatures    []string                 `json:"supported_features"`
			ParticipantTools     manifestParticipantTools `json:"participant_tools"`
		} `json:"capabilities"`
	}{SchemaVersion: "processor-manifest/v2", SupportedContractVersions: contracts, Constraints: map[string]string{}}
	document.Identity.Name = "raes-reference-processor"
	document.Identity.Version = version
	document.Compatibility.Backends = backends
	document.ConceptBindings = []manifestConceptBinding{{"capabilities.supported_sdl_versions", "scenarios"}, {"capabilities.supported_features", "apparatus-declarations"}}
	document.Capabilities.SupportedSDLVersions = []string{"sdl-authoring-input-v1"}
	document.Capabilities.SupportedFeatures = features
	document.Capabilities.ParticipantTools.SemanticVersions = []string{"participant-tool-profile/v1"}
	for _, feature := range []string{termToolAffordances, "scoped_tool_affordances"} {
		document.Capabilities.ParticipantTools.FeatureSupport = append(document.Capabilities.ParticipantTools.FeatureSupport, manifestFeatureSupport{Feature: feature, SupportLevel: termExact, ConstraintRefs: []string{}, LimitationRefs: []string{}, DisclosureRefs: []string{}, EvidenceRefs: []string{"tests:ACT-619", "tests:API-414"}})
	}
	raw, err := json.Marshal(document)
	if err != nil {
		return invalid()
	}
	validator, err := processorAdmissionOwner()
	if err != nil {
		return binding.ProcessorManifestV2{}, err
	}
	if err := validator.CheckPortable("processor-manifest-v2", raw, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}); err != nil {
		return binding.ProcessorManifestV2{}, err
	}
	var result binding.ProcessorManifestV2
	if err := json.Unmarshal(raw, &result); err != nil {
		return invalid()
	}
	return result, nil
}
